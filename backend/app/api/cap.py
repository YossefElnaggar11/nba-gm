from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.cba.constants import CAP_HISTORY, EXCEPTIONS_2026_27
from app.db.schema import CapHold, Contract, ContractSeason, Player, Team

router = APIRouter(prefix="/api/cap", tags=["cap"])


def get_db():
    from app.main import SessionLocal
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.get("/levels")
def cap_levels():
    return {
        season: {
            "salary_cap": c.salary_cap,
            "minimum_team_salary": c.minimum_team_salary,
            "luxury_tax": c.luxury_tax,
            "first_apron": c.first_apron,
            "second_apron": c.second_apron,
            "projected": c.projected,
        }
        for season, c in CAP_HISTORY.items()
    }


@router.get("/exceptions/2026-27")
def exceptions_2026_27():
    e = EXCEPTIONS_2026_27
    return {
        "season": e.season,
        "non_taxpayer_mle": e.non_taxpayer_mle,
        "taxpayer_mle": e.taxpayer_mle,
        "room_mle": e.room_mle,
        "bi_annual": e.bi_annual,
        "minimum_2yr_vet": e.minimum_2yr_vet,
    }


@router.get("/team/{tricode}")
def team_cap_sheet(tricode: str, season: str = "2026-27", db: Session = Depends(get_db)):
    tricode = tricode.upper()
    if season not in CAP_HISTORY:
        raise HTTPException(400, f"Unknown season {season}")
    team = db.get(Team, tricode)
    if not team:
        raise HTTPException(404, f"Team {tricode} not found")
    # All contract-seasons for this team's players for the given season
    q = (
        select(ContractSeason, Player.name, Player.age, Player.id)
        .join(Contract, Contract.id == ContractSeason.contract_id)
        .join(Player, Player.id == Contract.player_id)
        .where(
            Contract.team_tricode == tricode,
            Contract.is_active == True,
            ContractSeason.season == season,
        )
        .order_by(ContractSeason.salary.desc())
    )
    rows = db.execute(q).all()
    breakdown = []
    salary_total = 0
    for cs, pname, page, pid in rows:
        salary_total += cs.salary
        breakdown.append({
            "player_id": pid,
            "name": pname,
            "age": page,
            "salary": cs.salary,
            "option_type": cs.option_type.value if hasattr(cs.option_type, "value") else cs.option_type,
            "guaranteed": cs.guaranteed,
        })
    # Cap holds for own FAs (Bird-rights placeholder)
    hold_rows = (
        db.query(CapHold, Player.name, Player.age)
        .join(Player, Player.id == CapHold.player_id)
        .filter(
            CapHold.team_tricode == tricode,
            CapHold.season == season,
            CapHold.renounced == False,
        )
        .order_by(CapHold.amount.desc())
        .all()
    )
    holds = []
    holds_total = 0
    for h, pname, page in hold_rows:
        # If the player has signed elsewhere or been re-signed, skip the hold
        p = db.get(Player, h.player_id)
        if p and (not p.is_free_agent and p.team_tricode != tricode):
            continue
        if p and not p.is_free_agent and p.team_tricode == tricode:
            # Already re-signed by us — hold is replaced by actual contract; skip
            continue
        holds_total += h.amount
        holds.append({
            "hold_id": h.id, "player_id": h.player_id, "name": pname, "age": page,
            "amount": h.amount, "notes": h.notes,
        })
    total = salary_total + holds_total
    cap = CAP_HISTORY[season]
    return {
        "team": tricode,
        "season": season,
        "cap_levels": {
            "salary_cap": cap.salary_cap,
            "luxury_tax": cap.luxury_tax,
            "first_apron": cap.first_apron,
            "second_apron": cap.second_apron,
        },
        "salary_total": salary_total,
        "cap_holds_total": holds_total,
        "total_salary": total,
        "cap_space": cap.salary_cap - total,
        "over_tax": total > cap.luxury_tax,
        "over_first_apron": total > cap.first_apron,
        "over_second_apron": total > cap.second_apron,
        "players": breakdown,
        "cap_holds": holds,
    }
