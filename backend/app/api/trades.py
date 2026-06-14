"""Trade API: propose, validate, and apply trades with full CBA enforcement."""
from __future__ import annotations

from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.cba.rules import (
    Severity, TradeLeg, TradeProposal, Violation,
    compute_team_finances, validate_trade,
)
from app.db.schema import (
    Contract, ContractSeason, DraftPick, Player, TradeException, Transaction, TransactionType,
)

router = APIRouter(prefix="/api/trades", tags=["trades"])


def get_db():
    from app.main import SessionLocal
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------


class TradeLegIn(BaseModel):
    team: str
    outgoing_player_ids: list[int] = Field(default_factory=list)
    outgoing_pick_ids: list[int] = Field(default_factory=list)
    outgoing_cash: int = 0
    outgoing_trade_exception_used: int = 0


class TradeProposalIn(BaseModel):
    legs: list[TradeLegIn]
    season: str = "2026-27"
    apply: bool = False           # if False, just validate
    description: str | None = None
    career_mode: bool = False     # if True, AI on the other teams must accept
    user_team: str | None = None  # which team in legs is the user (for career mode)
    # Per-asset routing. Keys: "player:<id>" or "pick:<id>". Values: destination tricode.
    # Required for 3+ team trades; optional for 2-team (defaults to the other team).
    destinations: dict[str, str] = {}


class ViolationOut(BaseModel):
    code: str
    severity: str
    message: str
    team: str | None = None


class TradeResponse(BaseModel):
    valid: bool
    violations: list[ViolationOut]
    applied: bool
    transaction_id: int | None = None
    summary: dict
    ai_evaluations: list[dict] | None = None  # career mode only


def _violation_to_out(v: Violation) -> ViolationOut:
    return ViolationOut(code=v.code, severity=v.severity.value, message=v.message, team=v.team)


def _summarize(db: Session, proposal: TradeProposal) -> dict:
    """Produce a human-readable summary of the trade and each team's cap impact."""
    legs_out = []
    for leg in proposal.legs:
        out_players = []
        out_salary = 0
        for pid in leg.outgoing_player_ids:
            p = db.get(Player, pid)
            if not p:
                continue
            cs = (
                db.query(ContractSeason)
                .join(Contract, Contract.id == ContractSeason.contract_id)
                .filter(
                    Contract.player_id == p.id, Contract.is_active == True,
                    ContractSeason.season == proposal.season,
                )
                .one_or_none()
            )
            sal = cs.salary if cs else 0
            out_salary += sal
            out_players.append({"id": p.id, "name": p.name, "salary": sal})
        out_picks = []
        for pkid in leg.outgoing_pick_ids:
            pk = db.get(DraftPick, pkid)
            if pk:
                out_picks.append({
                    "id": pk.id, "year": pk.season_year, "round": pk.round,
                    "original": pk.original_team_tricode,
                    "is_swap": pk.is_swap,
                    "protection": pk.protection_text,
                })
        fin_before = compute_team_finances(db, leg.team, proposal.season)
        legs_out.append({
            "team": leg.team,
            "outgoing_players": out_players,
            "outgoing_picks": out_picks,
            "outgoing_salary": out_salary,
            "cap_before": fin_before.total_salary,
            "tax_before": fin_before.is_taxpayer,
            "first_apron_before": fin_before.is_above_first_apron,
        })
    return {"legs": legs_out, "season": proposal.season}


# ---------------------------------------------------------------------------
# Apply trade (move assets, write transaction)
# ---------------------------------------------------------------------------


def _apply_trade(db: Session, proposal: TradeProposal) -> int:
    """Move players and picks per the explicit routing in the proposal, and
    create Traded Player Exceptions (TPEs) for any team that took back less
    salary than it sent out."""
    from app.cba.rules import _player_salary_in_season

    # Track per-team net salary change (positive = took on more $, negative = saved $)
    sent_by_team: dict[str, int] = {leg.team: 0 for leg in proposal.legs}
    received_by_team: dict[str, int] = {leg.team: 0 for leg in proposal.legs}

    for leg in proposal.legs:
        for pid in leg.outgoing_player_ids:
            dest = proposal.destination("player", pid, leg.team)
            sal = _player_salary_in_season(db, pid, proposal.season)
            sent_by_team[leg.team] = sent_by_team.get(leg.team, 0) + sal
            received_by_team[dest] = received_by_team.get(dest, 0) + sal
            p = db.get(Player, pid)
            p.team_tricode = dest
            p.bird_years_with_team = 0
            for c in p.contracts:
                if c.is_active:
                    c.team_tricode = dest
        for pkid in leg.outgoing_pick_ids:
            dest = proposal.destination("pick", pkid, leg.team)
            pk = db.get(DraftPick, pkid)
            pk.owner_tricode = dest

    # Generate a TPE for any team whose outgoing salary > incoming salary.
    # NBA reality: TPE = (outgoing - incoming) salary, expires 1 year from creation.
    for team, sent in sent_by_team.items():
        received = received_by_team.get(team, 0)
        diff = sent - received
        if diff > 0 and len(proposal.legs) >= 2:
            today = date.today()
            # Pull a representative player name for the notes
            src_name = None
            leg = next((l for l in proposal.legs if l.team == team), None)
            if leg and leg.outgoing_player_ids:
                first_p = db.get(Player, leg.outgoing_player_ids[0])
                if first_p:
                    src_name = first_p.name
            db.add(TradeException(
                team_tricode=team,
                amount=diff,
                remaining=diff,
                created_date=today,
                expires_date=date(today.year + 1, today.month, today.day),
                season_created=proposal.season,
                source_player_name=src_name,
                used_up=False,
                notes=f"Generated from trade (net outgoing ${diff:,})",
            ))

    teams_str = " <-> ".join(leg.team for leg in proposal.legs)
    tx = Transaction(
        type=TransactionType.TRADE,
        payload={
            "season": proposal.season,
            "legs": [
                {
                    "team": leg.team,
                    "outgoing_player_ids": leg.outgoing_player_ids,
                    "outgoing_pick_ids": leg.outgoing_pick_ids,
                    "outgoing_cash": leg.outgoing_cash,
                }
                for leg in proposal.legs
            ],
            "destinations": proposal.destinations,
        },
        description=f"Trade: {teams_str}",
        is_user_action=True,
    )
    db.add(tx)
    db.flush()
    db.commit()
    return tx.id


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------


@router.post("", response_model=TradeResponse)
def propose_trade(req: TradeProposalIn, db: Session = Depends(get_db)) -> TradeResponse:
    from app.cba.ai_trade import evaluate_for_team

    proposal = TradeProposal(
        legs=[
            TradeLeg(
                team=l.team.upper(),
                outgoing_player_ids=l.outgoing_player_ids,
                outgoing_pick_ids=l.outgoing_pick_ids,
                outgoing_cash=l.outgoing_cash,
                outgoing_trade_exception_used=l.outgoing_trade_exception_used,
            )
            for l in req.legs
        ],
        season=req.season,
        destinations={k: v.upper() for k, v in (req.destinations or {}).items()},
    )
    violations = validate_trade(db, proposal)
    summary = _summarize(db, proposal)
    blockers = [v for v in violations if v.severity == Severity.BLOCKER]
    valid = not blockers

    # Career-mode AI evaluation on non-user legs
    ai_evals = None
    ai_rejects = False
    if req.career_mode:
        ai_evals = []
        user_team = (req.user_team or "").upper()
        for leg in proposal.legs:
            if leg.team == user_team:
                continue
            ev = evaluate_for_team(db, proposal, leg.team)
            ai_evals.append({
                "team": leg.team,
                "accepts": ev.accepts,
                "incoming_value": round(ev.incoming_value, 1),
                "outgoing_value": round(ev.outgoing_value, 1),
                "explanation": ev.explanation,
            })
            if not ev.accepts:
                ai_rejects = True

    txid: int | None = None
    applied = False
    if req.apply:
        if not valid:
            return TradeResponse(
                valid=False,
                violations=[_violation_to_out(v) for v in violations],
                applied=False, transaction_id=None,
                summary=summary, ai_evaluations=ai_evals,
            )
        if req.career_mode and ai_rejects:
            return TradeResponse(
                valid=True,
                violations=[_violation_to_out(v) for v in violations],
                applied=False, transaction_id=None,
                summary=summary, ai_evaluations=ai_evals,
            )
        txid = _apply_trade(db, proposal)
        applied = True
    return TradeResponse(
        valid=valid,
        violations=[_violation_to_out(v) for v in violations],
        applied=applied,
        transaction_id=txid,
        summary=summary,
        ai_evaluations=ai_evals,
    )
