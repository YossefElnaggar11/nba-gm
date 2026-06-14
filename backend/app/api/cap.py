from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from datetime import date

from app.cba.constants import CAP_HISTORY, EXCEPTIONS_2026_27
from app.db.schema import CapHold, Contract, ContractSeason, Player, Team, TradeException

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
        select(ContractSeason, Contract, Player)
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
    for cs, contract, p in rows:
        salary_total += cs.salary
        breakdown.append({
            "player_id": p.id,
            "name": p.name,
            "age": p.age,
            "overall": p.overall,
            "position": p.position,
            "salary": cs.salary,
            "option_type": cs.option_type.value if hasattr(cs.option_type, "value") else cs.option_type,
            "guaranteed": cs.guaranteed,
            "is_two_way": contract.is_two_way,
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


@router.get("/team/{tricode}/exceptions")
def team_exceptions(tricode: str, season: str = "2026-27", db: Session = Depends(get_db)):
    """All signing/trade tools currently available to this team:
      - cap space (or "over cap")
      - MLE variant they can use (room MLE if room, taxpayer MLE if over apron, else non-tax MLE)
      - BAE (if under first apron and not used recently)
      - Minimum exception (always available)
      - Bird-eligible own FAs (list)
      - Live Traded Player Exceptions (TPEs)
    """
    tricode = tricode.upper()
    if season not in CAP_HISTORY:
        raise HTTPException(400, f"Unknown season {season}")

    # Pull cap status for context
    from app.cba.rules import compute_team_finances
    fin = compute_team_finances(db, tricode, season)
    exc = EXCEPTIONS_2026_27   # values are 2026-27 estimates; treat as ballpark

    # MLE selection rules from 2023 CBA:
    #   - if team is below the salary cap: gets the Room MLE only (smaller)
    #   - if above cap but below first apron: non-tax MLE
    #   - if above first apron but below second: taxpayer MLE
    #   - if above second apron: NONE (no MLE allowed)
    if not fin.is_over_cap:
        mle_label = "Room MLE"
        mle_amount = exc.room_mle
        mle_available = True
        mle_note = "Available because you're under the cap."
    elif fin.is_above_second_apron:
        mle_label = "MLE (blocked)"
        mle_amount = 0
        mle_available = False
        mle_note = "Above the 2nd apron — no MLE is available."
    elif fin.is_above_first_apron:
        mle_label = "Taxpayer MLE"
        mle_amount = exc.taxpayer_mle
        mle_available = True
        mle_note = "Above 1st apron — only the taxpayer MLE."
    else:
        mle_label = "Non-Tax MLE"
        mle_amount = exc.non_taxpayer_mle
        mle_available = True
        mle_note = "Standard MLE. Using the full amount hard-caps you at the 1st apron."

    # BAE: under cap teams don't have it; over second apron blocked; available otherwise
    bae_available = fin.is_over_cap and not fin.is_above_second_apron
    bae_note = (
        "Available — small exception for a 1- or 2-year deal."
        if bae_available
        else ("Blocked above the 2nd apron." if fin.is_above_second_apron else "Not available — you're under the cap.")
    )

    # Bird-eligible own FAs (any non-renounced cap hold whose player is still FA)
    bird_rows = (
        db.query(CapHold, Player)
        .join(Player, Player.id == CapHold.player_id)
        .filter(
            CapHold.team_tricode == tricode,
            CapHold.season == season,
            CapHold.renounced == False,
            Player.is_free_agent == True,
        )
        .all()
    )
    bird_eligible = [
        {
            "player_id": p.id, "name": p.name, "age": p.age,
            "overall": p.overall, "position": p.position,
            "hold_amount": h.amount,
        }
        for h, p in bird_rows
    ]

    # Live trade exceptions (TPEs) for this team
    today = date.today()
    tpe_rows = (
        db.query(TradeException)
        .filter(
            TradeException.team_tricode == tricode,
            TradeException.used_up == False,
            TradeException.expires_date >= today,
            TradeException.remaining > 0,
        )
        .order_by(TradeException.expires_date)
        .all()
    )
    tpes = [
        {
            "id": t.id,
            "amount_total": t.amount,
            "remaining": t.remaining,
            "expires": t.expires_date.isoformat(),
            "source": t.source_player_name,
        }
        for t in tpe_rows
    ]

    return {
        "team": tricode,
        "season": season,
        "is_over_cap": fin.is_over_cap,
        "is_above_tax": fin.is_taxpayer,
        "is_above_first_apron": fin.is_above_first_apron,
        "is_above_second_apron": fin.is_above_second_apron,
        "cap_space": fin.cap_space,
        "mle": {
            "label": mle_label,
            "amount": mle_amount,
            "available": mle_available,
            "note": mle_note,
        },
        "bae": {
            "label": "Bi-Annual Exception",
            "amount": exc.bi_annual if bae_available else 0,
            "available": bae_available,
            "note": bae_note,
        },
        "minimum": {
            "label": "Minimum Exception",
            "amount": exc.minimum_2yr_vet,
            "available": True,
            "note": "Always available. Salary depends on the player's years of service.",
        },
        "bird_eligible": bird_eligible,
        "trade_exceptions": tpes,
    }
