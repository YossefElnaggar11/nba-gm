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
                # Cap hold = ~1.5x prior salary for vets, 2.5x for young (simplified)
                yos = player.years_of_service or 0
                hold_amount = max(int(salary_str * (2.5 if yos <= 2 else 1.5)), 5_000_000) if salary_str > 3_000_000 else salary_str
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
