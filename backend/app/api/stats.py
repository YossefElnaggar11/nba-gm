"""Per-player season stats endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.schema import Player, PlayerSeasonStats

router = APIRouter(prefix="/api/stats", tags=["stats"])


def get_db():
    from app.main import SessionLocal
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.get("/team/{tricode}/{season}")
def team_season_stats(tricode: str, season: str, db: Session = Depends(get_db)):
    tricode = tricode.upper()
    rows = (
        db.query(PlayerSeasonStats, Player.name, Player.age, Player.overall, Player.position)
        .join(Player, Player.id == PlayerSeasonStats.player_id)
        .filter(
            PlayerSeasonStats.team_tricode == tricode,
            PlayerSeasonStats.season == season,
        )
        .all()
    )
    if not rows:
        return {"team": tricode, "season": season, "players": [], "note": f"No simulated stats for {season} yet — run /sim first."}
    players = []
    for stats, name, age, overall, pos in rows:
        players.append({
            "player_id": stats.player_id,
            "name": name,
            "age": age,
            "position": pos,
            "overall": overall,
            "games_played": stats.games_played,
            "games_started": stats.games_started,
            "mpg": stats.mpg,
            "ppg": stats.ppg,
            "rpg": stats.rpg,
            "apg": stats.apg,
            "spg": stats.spg,
            "bpg": stats.bpg,
            "fg_pct": stats.fg_pct,
            "three_pct": stats.three_pct,
            "ft_pct": stats.ft_pct,
            "is_injured": stats.is_injured,
        })
    players.sort(key=lambda p: -p["ppg"])
    return {"team": tricode, "season": season, "players": players}
