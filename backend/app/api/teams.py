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
        })
    return {"team": tricode, "players": result, "count": len(result)}
