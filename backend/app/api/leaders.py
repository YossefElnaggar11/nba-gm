"""League leaders endpoint — top scorers/rebounders/assists per season."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.schema import Player, PlayerSeasonStats

router = APIRouter(prefix="/api/leaders", tags=["leaders"])


def get_db():
    from app.main import SessionLocal
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.get("/{season}")
def leaders(season: str, db: Session = Depends(get_db)):
    rows = (
        db.query(PlayerSeasonStats, Player.name)
        .join(Player, Player.id == PlayerSeasonStats.player_id)
        .filter(PlayerSeasonStats.season == season)
        .filter(PlayerSeasonStats.games_played >= 40)
        .all()
    )
    if not rows:
        return {"season": season, "ppg": [], "rpg": [], "apg": [], "spg": [], "bpg": []}

    def topN(key: str, n: int = 10):
        sorted_rows = sorted(rows, key=lambda r: -getattr(r[0], key))
        return [
            {"name": r[1], "team": r[0].team_tricode, "value": getattr(r[0], key), "gp": r[0].games_played}
            for r in sorted_rows[:n]
        ]

    return {
        "season": season,
        "ppg": topN("ppg"),
        "rpg": topN("rpg"),
        "apg": topN("apg"),
        "spg": topN("spg"),
        "bpg": topN("bpg"),
    }
