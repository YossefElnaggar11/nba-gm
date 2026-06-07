"""Year rollover: advance from one season to the next.

Effects:
  - Contracts with no remaining seasons >= next_season -> deactivated, players -> UFA
  - Player age +1, years_of_service +1 (for non-FAs)
  - Prospect lookups update implicitly (next year's prospects already loaded)
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.schema import Contract, ContractSeason, Player

router = APIRouter(prefix="/api/rollover", tags=["rollover"])


def get_db():
    from app.main import SessionLocal
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


class RolloverIn(BaseModel):
    from_season: str = "2026-27"
    to_season: str = "2027-28"


def _develop_player(p: Player) -> tuple[int, int]:
    """Apply yearly aging curve. Returns (ovr_delta, potential_delta)."""
    if not p.overall:
        return (0, 0)
    age = p.age or 27
    pot = p.potential or p.overall
    import random
    ovr_delta = 0
    if age <= 21:
        ovr_delta = random.randint(2, 4)
    elif age <= 23:
        ovr_delta = random.randint(1, 3)
    elif age <= 25:
        ovr_delta = random.randint(0, 2)
    elif age <= 27:
        ovr_delta = random.randint(-1, 1)
    elif age <= 29:
        ovr_delta = random.randint(-1, 1)
    elif age <= 31:
        ovr_delta = random.randint(-2, 0)
    elif age <= 33:
        ovr_delta = random.randint(-3, -1)
    else:
        ovr_delta = random.randint(-4, -2)
    # Cap at potential
    new_ovr = min(p.overall + ovr_delta, pot + 3)
    new_ovr = max(50, new_ovr)
    return new_ovr - p.overall, 0


@router.post("")
def rollover(req: RolloverIn, db: Session = Depends(get_db)):
    contracts_dropped = 0
    new_fas = 0
    players_aged = 0
    developed = 0
    biggest_gains = []
    biggest_drops = []
    for c in db.query(Contract).filter(Contract.is_active == True).all():
        remaining = [s for s in c.seasons if s.season >= req.to_season]
        if not remaining:
            c.is_active = False
            player = db.get(Player, c.player_id)
            if player and player.team_tricode is not None:
                player.team_tricode = None
                player.is_free_agent = True
                player.fa_type = "UFA"
                new_fas += 1
            contracts_dropped += 1

    for p in db.query(Player).all():
        if p.age:
            p.age += 1
            players_aged += 1
        if not p.is_free_agent:
            p.years_of_service = (p.years_of_service or 0) + 1
        # Player development / decline
        ovr_d, _ = _develop_player(p)
        if ovr_d != 0:
            p.overall = (p.overall or 60) + ovr_d
            developed += 1
            if ovr_d > 0:
                biggest_gains.append({"name": p.name, "delta": ovr_d, "new_ovr": p.overall, "age": p.age})
            else:
                biggest_drops.append({"name": p.name, "delta": ovr_d, "new_ovr": p.overall, "age": p.age})

    biggest_gains.sort(key=lambda x: -x["delta"])
    biggest_drops.sort(key=lambda x: x["delta"])

    db.commit()
    return {
        "ok": True,
        "from_season": req.from_season,
        "to_season": req.to_season,
        "contracts_dropped": contracts_dropped,
        "new_free_agents": new_fas,
        "players_aged": players_aged,
        "players_developed_or_declined": developed,
        "top_risers": biggest_gains[:5],
        "top_decliners": biggest_drops[:5],
    }
