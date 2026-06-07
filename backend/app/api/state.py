"""Game state endpoint — what season is currently being played/built."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.schema import Season

router = APIRouter(prefix="/api/state", tags=["state"])


def get_db():
    from app.main import SessionLocal
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# Scope: per user spec, the game covers 2026-27 and 2027-28 seasons
SEASONS_ORDER = ["2026-27", "2027-28"]


@router.get("")
def game_state(db: Session = Depends(get_db)):
    """Return current offseason/season state.

    Logic: the "current" season is the first one in our scope that hasn't
    been simulated yet. The draft year is the start year of the current season.
    """
    simmed = {s.season for s in db.query(Season).filter(Season.simulated == True).all()}
    current_season = next((s for s in SEASONS_ORDER if s not in simmed), SEASONS_ORDER[-1])
    current_draft_year = int(current_season.split("-")[0])
    all_simmed = [s for s in SEASONS_ORDER if s in simmed]
    return {
        "current_season": current_season,
        "current_draft_year": current_draft_year,
        "simmed_seasons": all_simmed,
        "scope_done": len(all_simmed) >= len(SEASONS_ORDER),
    }
