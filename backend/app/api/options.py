"""Option processing: pick up or decline player options, team options, ETOs.

When declined: the player becomes a free agent (UFA), and the contract season
for that year is dropped.
When picked up: the option becomes a guaranteed season.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.schema import (
    Contract, ContractSeason, OptionType, Player, Transaction, TransactionType,
)

router = APIRouter(prefix="/api/options", tags=["options"])


def get_db():
    from app.main import SessionLocal
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.get("/pending")
def list_pending_options(season: str = "2026-27", team: str | None = None, db: Session = Depends(get_db)):
    """Return all undecided player/team options for the given season."""
    q = (
        db.query(ContractSeason, Contract, Player)
        .join(Contract, Contract.id == ContractSeason.contract_id)
        .join(Player, Player.id == Contract.player_id)
        .filter(
            ContractSeason.season == season,
            ContractSeason.option_type.in_([OptionType.PLAYER, OptionType.TEAM, OptionType.EARLY_TERMINATION]),
            ContractSeason.decision_made == False,
            Contract.is_active == True,
        )
    )
    if team:
        q = q.filter(Contract.team_tricode == team.upper())
    out = []
    for cs, c, p in q.order_by(ContractSeason.salary.desc()).all():
        out.append({
            "contract_season_id": cs.id,
            "player_id": p.id,
            "player_name": p.name,
            "team": c.team_tricode,
            "season": cs.season,
            "salary": cs.salary,
            "option_type": cs.option_type.value if hasattr(cs.option_type, "value") else cs.option_type,
            "decided_by": "PLAYER" if cs.option_type == OptionType.PLAYER else "TEAM",
        })
    return out


class OptionDecisionIn(BaseModel):
    contract_season_id: int
    pick_up: bool   # True = exercise option; False = decline (player becomes FA / option dropped)
    # If declining AND immediately intending to re-sign: keeps the cap hold (Bird rights)
    # but does NOT yet sign — user must follow up with a signing. This is the
    # "decline-and-re-sign" path. If False (default), player goes straight to FA pool.
    intent_to_resign: bool = False


@router.post("/decide")
def decide_option(req: OptionDecisionIn, db: Session = Depends(get_db)):
    from app.db.schema import CapHold
    cs = db.get(ContractSeason, req.contract_season_id)
    if not cs:
        raise HTTPException(404, "Option not found")
    if cs.decision_made:
        raise HTTPException(400, "Option already decided")
    contract = db.get(Contract, cs.contract_id)
    player = db.get(Player, contract.player_id)
    season_str = cs.season
    salary_str = cs.salary
    team_before = contract.team_tricode
    original_option_type = cs.option_type.value if hasattr(cs.option_type, "value") else cs.option_type

    if req.pick_up:
        cs.option_type = OptionType.NONE
        cs.guaranteed = True
        cs.decision_made = True
        action = "EXERCISED"
    else:
        # Delete this season AND any later seasons via SQL (avoids session sync issues)
        db.query(ContractSeason).filter(
            ContractSeason.contract_id == contract.id,
            ContractSeason.season >= cs.season,
        ).delete(synchronize_session=False)
        db.flush()
        # Refresh contract.seasons relationship by re-querying
        remaining = db.query(ContractSeason).filter(
            ContractSeason.contract_id == contract.id
        ).count()
        if remaining == 0:
            contract.is_active = False
            player.team_tricode = None
            player.is_free_agent = True
            if not player.fa_type:
                player.fa_type = "UFA"
            # Always add a cap hold on the former team — they retain Bird rights
            # until they renounce or the hold gets replaced by a new contract.
            existing_hold = db.query(CapHold).filter(
                CapHold.player_id == player.id,
                CapHold.season == "2026-27",
                CapHold.renounced == False,
            ).first()
            if not existing_hold:
                # Cap hold formula: CBA says ~150% of last salary for vets, but we
                # cap at 135% of expected market value to prevent the hold from
                # being wildly above what the player is actually worth.
                from app.cba.market_value import expected_market_value
                yos = player.years_of_service or 0
                cba_raw = max(int(salary_str * (2.5 if yos <= 2 else 1.5)), 5_000_000) if salary_str > 3_000_000 else salary_str
                market = expected_market_value(player.overall, player.age, "2026-27", player.position)
                hold_amount = min(cba_raw, int(market * 1.35))
                # Floor at 50% of last salary (prevents tiny holds for stars after a low-salary year)
                hold_amount = max(hold_amount, int(salary_str * 0.5))
                db.add(CapHold(
                    player_id=player.id,
                    team_tricode=team_before,
                    season="2026-27",
                    amount=hold_amount,
                    renounced=False,
                    notes=f"Hold from declined option (${salary_str:,})",
                ))
        action = "DECLINED"

    db.add(Transaction(
        type=TransactionType.PICK_OPTION,
        payload={
            "contract_season_id": req.contract_season_id,
            "player_id": player.id,
            "season": season_str,
            "action": action,
            "pick_up": req.pick_up,
            "intent_to_resign": req.intent_to_resign,
            "original_option_type": original_option_type,
            "former_team": team_before,
            "salary": salary_str,
        },
        description=f"{action} option: {player.name} ({season_str}) ${salary_str:,}",
        is_user_action=True,
    ))
    db.commit()
    return {
        "ok": True,
        "action": action,
        "player": player.name,
        "player_id": player.id,
        "former_team": team_before,
        "is_free_agent": player.is_free_agent,
        "intent_to_resign": req.intent_to_resign,
    }


class OptionUndoIn(BaseModel):
    contract_season_id: int


@router.post("/undo")
def undo_option(req: OptionUndoIn, db: Session = Depends(get_db)):
    """Undo the most recent decision for this contract-season."""
    from app.db.schema import CapHold

    # Find the most recent NOT-YET-UNDONE option transaction for this cs_id
    txs = (
        db.query(Transaction)
        .filter(Transaction.type == TransactionType.PICK_OPTION)
        .order_by(Transaction.occurred_at.desc())
        .all()
    )
    target_tx = None
    for t in txs:
        payload = t.payload or {}
        if payload.get("contract_season_id") != req.contract_season_id:
            continue
        if payload.get("action") not in ("EXERCISED", "DECLINED"):
            continue
        if payload.get("undone"):
            continue
        target_tx = t
        break

    if not target_tx:
        return {"ok": False, "error": "No undoable decision found for this option"}

    payload = target_tx.payload or {}
    action = payload.get("action")
    player_id = payload.get("player_id")
    season_str = payload.get("season")
    original_opt = payload.get("original_option_type", "TEAM")
    former_team = payload.get("former_team")
    salary = int(payload.get("salary") or 0)
    player = db.get(Player, player_id) if player_id else None
    if not player:
        return {"ok": False, "error": "Player record missing"}

    if action == "EXERCISED":
        # Reverse the pick-up: restore PO/TO state
        cs = db.get(ContractSeason, req.contract_season_id)
        if not cs:
            return {"ok": False, "error": "Contract season missing"}
        cs.option_type = OptionType(original_opt) if original_opt in ("PLAYER", "TEAM", "EARLY_TERMINATION") else OptionType.TEAM
        cs.decision_made = False
        cs.guaranteed = False
    elif action == "DECLINED":
        # Reverse the decline: recreate the dropped ContractSeason, reactivate contract, remove cap hold
        contract = (
            db.query(Contract)
            .filter(Contract.player_id == player.id)
            .order_by(Contract.id.desc())
            .first()
        )
        if not contract:
            return {"ok": False, "error": "Contract record missing"}
        contract.is_active = True
        if salary > 0 and season_str:
            db.add(ContractSeason(
                contract_id=contract.id, season=season_str, salary=salary,
                option_type=OptionType(original_opt) if original_opt in ("PLAYER", "TEAM", "EARLY_TERMINATION") else OptionType.TEAM,
                guaranteed=False, decision_made=False,
            ))
        player.team_tricode = former_team or contract.team_tricode
        player.is_free_agent = False
        player.fa_type = None
        # Drop the cap hold that was added when we declined
        hold = (
            db.query(CapHold)
            .filter(CapHold.player_id == player.id, CapHold.season == "2026-27", CapHold.renounced == False)
            .order_by(CapHold.id.desc())
            .first()
        )
        if hold:
            db.delete(hold)

    # Mark the original tx as undone so we don't double-undo
    target_tx.payload = {**payload, "undone": True}
    db.add(Transaction(
        type=TransactionType.PICK_OPTION,
        payload={"undo_of": target_tx.id, "contract_season_id": req.contract_season_id, "player_id": player.id, "action": f"UNDO_{action}"},
        description=f"UNDO {action.lower()}: {player.name} option decision reverted",
        is_user_action=True,
    ))
    db.commit()
    return {"ok": True, "action": f"REVERTED_{action}", "player": player.name}


@router.get("/summary")
def options_summary(season: str = "2026-27", db: Session = Depends(get_db)):
    """High-level counts for option processing UI."""
    q = (
        db.query(ContractSeason, Contract)
        .join(Contract, Contract.id == ContractSeason.contract_id)
        .filter(
            ContractSeason.season == season,
            ContractSeason.option_type.in_([OptionType.PLAYER, OptionType.TEAM, OptionType.EARLY_TERMINATION]),
            Contract.is_active == True,
        )
    )
    pending = 0
    decided = 0
    for cs, _ in q.all():
        if cs.decision_made:
            decided += 1
        else:
            pending += 1
    return {"season": season, "pending": pending, "decided": decided, "total": pending + decided}
