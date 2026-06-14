from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.cba.market_value import expected_market_value
from app.db.schema import CapHold, Player

router = APIRouter(prefix="/api/free-agents", tags=["free-agents"])


def get_db():
    from app.main import SessionLocal
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.get("")
def list_free_agents(fa_type: str | None = None, db: Session = Depends(get_db)):
    from app.api.state import SEASONS_ORDER
    from app.cba.constants import min_salary
    from app.db.schema import Season
    # Use the current offseason as the basis for market value / min salary / cap hold lookup
    simmed = {s.season for s in db.query(Season).filter(Season.simulated == True).all()}
    current_season = next((s for s in SEASONS_ORDER if s not in simmed), SEASONS_ORDER[-1])

    q = db.query(Player).filter(Player.is_free_agent == True)
    if fa_type:
        q = q.filter(Player.fa_type == fa_type.upper())
    fas = q.order_by(Player.overall.desc().nullslast()).all()
    holds_by_player = {
        h.player_id: h.team_tricode
        for h in db.query(CapHold).filter(CapHold.season == current_season, CapHold.renounced == False).all()
    }
    out = []
    for p in fas:
        mv = expected_market_value(p.overall, p.age, current_season, p.position)
        floor_min = min_salary(p.years_of_service or 0, current_season)
        out.append({
            "id": p.id,
            "name": p.name,
            "age": p.age,
            "position": p.position,
            "overall": p.overall,
            "potential": p.potential,
            "years_of_service": p.years_of_service,
            "fa_type": p.fa_type,
            "prior_team": holds_by_player.get(p.id) or p.team_tricode,
            "market_value": mv,
            "min_salary_for_yos": floor_min,
            "season": current_season,
        })
    return out
