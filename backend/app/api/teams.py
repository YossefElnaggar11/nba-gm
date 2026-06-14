from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.data.teams import logo_url
from app.db.schema import Player, Contract, ContractSeason, Team

router = APIRouter(prefix="/api/teams", tags=["teams"])


def get_db():
    from app.main import SessionLocal
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.get("")
def list_teams(db: Session = Depends(get_db)):
    teams = db.query(Team).order_by(Team.conference, Team.division, Team.tricode).all()
    return [
        {
            "tricode": t.tricode,
            "full_name": t.full_name,
            "conference": t.conference,
            "division": t.division,
            "primary_color": t.primary_color,
            "secondary_color": t.secondary_color,
            "logo_url": logo_url(t.tricode),
        }
        for t in teams
    ]


@router.get("/{tricode}")
def get_team(tricode: str, db: Session = Depends(get_db)):
    team = db.get(Team, tricode.upper())
    if not team:
        raise HTTPException(404, f"Team {tricode} not found")
    return {
        "tricode": team.tricode,
        "full_name": team.full_name,
        "conference": team.conference,
        "division": team.division,
        "primary_color": team.primary_color,
        "secondary_color": team.secondary_color,
        "logo_url": logo_url(team.tricode),
    }


@router.get("/{tricode}/roster")
def get_roster(tricode: str, db: Session = Depends(get_db)):
    tricode = tricode.upper()
    team = db.get(Team, tricode)
    if not team:
        raise HTTPException(404, f"Team {tricode} not found")
    players = (
        db.query(Player)
        .filter(Player.team_tricode == tricode, Player.is_free_agent == False)
        .order_by(Player.name)
        .all()
    )
    result = []
    for p in players:
        active_contract = next((c for c in p.contracts if c.is_active), None)
        contract_payload = None
        if active_contract:
            contract_payload = {
                "id": active_contract.id,
                "signed_using": active_contract.signed_using,
                "seasons": [
                    {
                        "season": s.season,
                        "salary": s.salary,
                        "option_type": s.option_type.value if hasattr(s.option_type, "value") else s.option_type,
                        "guaranteed": s.guaranteed,
                    }
                    for s in active_contract.seasons
                ],
            }
        result.append({
            "id": p.id,
            "name": p.name,
            "age": p.age,
            "position": p.position,
            "overall": p.overall,
            "potential": p.potential,
            "years_of_service": p.years_of_service,
            "contract": contract_payload,
            # 2025-26 baseline stats (from BBR scrape) — used for "last season" display
            "last_season_stats": {
                "ppg": p.baseline_ppg or 0,
                "rpg": p.baseline_rpg or 0,
                "apg": p.baseline_apg or 0,
                "spg": p.baseline_spg or 0,
                "bpg": p.baseline_bpg or 0,
                "mpg": p.baseline_mpg or 0,
            } if p.baseline_mpg else None,
        })
    return {"team": tricode, "players": result, "count": len(result)}


@router.get("/{tricode}/own-free-agents")
def get_own_free_agents(tricode: str, db: Session = Depends(get_db)):
    """Players the team has Bird rights to (cap hold on the team's books).
    Uses the current game season (the offseason the user is in)."""
    from app.api.state import SEASONS_ORDER
    from app.cba.constants import min_salary
    from app.cba.market_value import expected_market_value
    from app.db.schema import CapHold, Season
    tricode = tricode.upper()
    # Current season = first non-simmed in scope
    simmed = {s.season for s in db.query(Season).filter(Season.simulated == True).all()}
    current_season = next((s for s in SEASONS_ORDER if s not in simmed), SEASONS_ORDER[-1])
    rows = (
        db.query(CapHold, Player)
        .join(Player, Player.id == CapHold.player_id)
        .filter(
            CapHold.team_tricode == tricode,
            CapHold.season == current_season,
            CapHold.renounced == False,
            Player.is_free_agent == True,
        )
        .order_by(CapHold.amount.desc())
        .all()
    )
    out = []
    for hold, p in rows:
        market = expected_market_value(p.overall, p.age, current_season, p.position)
        out.append({
            "hold_id": hold.id,
            "player_id": p.id,
            "name": p.name,
            "age": p.age,
            "position": p.position,
            "overall": p.overall,
            "years_of_service": p.years_of_service,
            "fa_type": p.fa_type or "UFA",
            "hold_amount": hold.amount,
            "market_value": market,
            "min_salary": min_salary(p.years_of_service or 0, current_season),
            "bird_eligible": True,
        })
    return {"team": tricode, "season": current_season, "own_fas": out}
