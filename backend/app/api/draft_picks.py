"""Draft phase: list prospects, make a pick, AI auto-pick."""
from __future__ import annotations

import random
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.cba.constants import ROOKIE_SCALE_2026_27_120PCT
from app.db.schema import (
    Contract, ContractSeason, DraftPick, OptionType, PickStatus, Player, Prospect,
    Transaction, TransactionType,
)

router = APIRouter(prefix="/api/draft-picks", tags=["draft-picks"])


def get_db():
    from app.main import SessionLocal
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.get("/prospects/{year}")
def list_prospects(year: int, available_only: bool = True, db: Session = Depends(get_db)):
    q = db.query(Prospect).filter(Prospect.draft_year == year)
    if available_only:
        q = q.filter(Prospect.drafted_to_team.is_(None))
    return [
        {
            "id": p.id,
            "rank": p.rank,
            "name": p.name,
            "position": p.position,
            "college": p.college,
            "age": p.age,
            "overall": p.overall,
            "potential": p.potential,
            "drafted_to": p.drafted_to_team,
            "drafted_at_pick": p.drafted_at_pick,
        }
        for p in q.order_by(Prospect.rank).all()
    ]


@router.get("/next-pick/{year}")
def next_pick(year: int, db: Session = Depends(get_db)):
    """Find the next un-drafted pick in the given year."""
    pick = (
        db.query(DraftPick)
        .filter(
            DraftPick.season_year == year,
            DraftPick.status == PickStatus.OWNED,
            DraftPick.pick_number.isnot(None),
        )
        .order_by(DraftPick.round, DraftPick.pick_number)
        .first()
    )
    if not pick:
        return {"done": True}
    return {
        "done": False,
        "pick_id": pick.id,
        "pick_number": pick.pick_number,
        "round": pick.round,
        "owner": pick.owner_tricode,
        "original": pick.original_team_tricode,
    }


class DraftPickIn(BaseModel):
    pick_id: int
    prospect_id: int


def _create_rookie_contract(db: Session, prospect: Prospect, team: str, pick_number: int) -> Player:
    """Generate a Player + rookie-scale Contract for a drafted prospect."""
    player = Player(
        name=prospect.name,
        age=prospect.age,
        position=prospect.position,
        years_of_service=0,
        team_tricode=team,
        overall=prospect.overall,
        potential=prospect.potential,
        is_free_agent=False,
        bird_years_with_team=0,
    )
    db.add(player)
    db.flush()

    if prospect.draft_year == 2026 and 1 <= pick_number <= 30:
        y1 = ROOKIE_SCALE_2026_27_120PCT.get(pick_number, 1_400_000)
        # Rookie scale: 4-year (2 guaranteed + 2 team options)
        contract = Contract(
            player_id=player.id, team_tricode=team,
            signed_date=date(2026, 7, 1),
            signed_using="ROOKIE_SCALE",
            is_active=True,
        )
        db.add(contract)
        db.flush()
        # 4-year rookie scale with ~5% raises; years 3 and 4 are team options
        seasons = ["2026-27", "2027-28", "2028-29", "2029-30"]
        for i, season in enumerate(seasons):
            sal = int(y1 * (1 + 0.05 * i))
            db.add(ContractSeason(
                contract_id=contract.id, season=season, salary=sal,
                option_type=OptionType.TEAM if i >= 2 else OptionType.NONE,
                guaranteed=(i < 2),
            ))
    else:
        # 2nd-rounder — minimum 2-year deal, non-guaranteed
        contract = Contract(
            player_id=player.id, team_tricode=team,
            signed_date=date(2026, 7, 1),
            signed_using="MIN",
            is_active=True,
        )
        db.add(contract)
        db.flush()
        for i, season in enumerate(["2026-27", "2027-28"]):
            db.add(ContractSeason(
                contract_id=contract.id, season=season, salary=1_286_000 + i * 100_000,
                option_type=OptionType.NONE, guaranteed=(i == 0),
            ))
    return player


@router.post("/pick")
def make_pick(req: DraftPickIn, db: Session = Depends(get_db)):
    pick = db.get(DraftPick, req.pick_id)
    if not pick:
        raise HTTPException(404, "Pick not found")
    if pick.status != PickStatus.OWNED:
        raise HTTPException(400, f"Pick already {pick.status}")
    prospect = db.get(Prospect, req.prospect_id)
    if not prospect:
        raise HTTPException(404, "Prospect not found")
    if prospect.drafted_to_team:
        raise HTTPException(400, f"{prospect.name} already drafted by {prospect.drafted_to_team}")

    # Mark conveyed
    pick.status = PickStatus.CONVEYED
    prospect.drafted_to_team = pick.owner_tricode
    prospect.drafted_at_pick = pick.pick_number

    # Create the new player + rookie contract
    player = _create_rookie_contract(db, prospect, pick.owner_tricode, pick.pick_number or 60)
    prospect.created_player_id = player.id

    db.add(Transaction(
        type=TransactionType.DRAFT_PICK,
        payload={
            "pick_id": pick.id,
            "pick_number": pick.pick_number,
            "round": pick.round,
            "team": pick.owner_tricode,
            "prospect_id": prospect.id,
            "player_id": player.id,
        },
        description=f"{pick.owner_tricode} selects {prospect.name} ({prospect.college}) with pick #{pick.pick_number}",
        is_user_action=False,
    ))
    db.commit()
    return {
        "ok": True,
        "team": pick.owner_tricode,
        "pick_number": pick.pick_number,
        "round": pick.round,
        "player": {"id": player.id, "name": player.name, "position": player.position, "overall": player.overall},
    }


@router.post("/auto-pick")
def auto_pick(year: int = 2026, db: Session = Depends(get_db)):
    """AI picks the best-available prospect for the next pick. Used to auto-sim
    non-user teams during the draft."""
    pick = (
        db.query(DraftPick)
        .filter(
            DraftPick.season_year == year,
            DraftPick.status == PickStatus.OWNED,
            DraftPick.pick_number.isnot(None),
        )
        .order_by(DraftPick.round, DraftPick.pick_number)
        .first()
    )
    if not pick:
        return {"done": True}
    # Best available by rank
    prospect = (
        db.query(Prospect)
        .filter(Prospect.draft_year == year, Prospect.drafted_to_team.is_(None))
        .order_by(Prospect.rank)
        .first()
    )
    if not prospect:
        return {"done": True, "reason": "no prospects left"}
    # Small randomness — top pick gets occasionally swapped for #2/#3
    candidates = (
        db.query(Prospect)
        .filter(Prospect.draft_year == year, Prospect.drafted_to_team.is_(None))
        .order_by(Prospect.rank)
        .limit(3)
        .all()
    )
    weights = [0.75, 0.18, 0.07][:len(candidates)]
    chosen = random.choices(candidates, weights=weights, k=1)[0]
    return make_pick(DraftPickIn(pick_id=pick.id, prospect_id=chosen.id), db=db)


@router.post("/auto-sim-until")
def auto_sim_until(year: int = 2026, until_team: str | None = None, db: Session = Depends(get_db)):
    """Auto-pick every pick until reaching `until_team` (the user's team) or end of draft.
    Returns the picks that were made."""
    picks_made = []
    safety = 0
    while True:
        safety += 1
        if safety > 70:
            break
        nxt = next_pick(year, db)
        if nxt.get("done"):
            break
        if until_team and nxt["owner"] == until_team.upper():
            break
        result = auto_pick(year, db)
        if result.get("done"):
            break
        picks_made.append(result)
    return {"picks_made": len(picks_made), "next": next_pick(year, db)}
