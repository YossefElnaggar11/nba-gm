"""Veteran contract extensions.

Simplified model: extending a player adds years onto their current contract,
starting the season AFTER their current last guaranteed season. CBA rules:
  - Max 4 added years (3 + current option year for some cases)
  - Y1 of extension can be up to 140% of last salary (for non-Designated)
  - 8% raises with Bird rights
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.cba.constants import CAP_HISTORY, MAX_LENGTH_EXTENSION, RAISE_PCT_BIRD
from app.cba.rules import max_salary
from app.db.schema import (
    Contract, ContractSeason, OptionType, Player, Transaction, TransactionType,
)

router = APIRouter(prefix="/api/extensions", tags=["extensions"])


def get_db():
    from app.main import SessionLocal
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


class ExtensionIn(BaseModel):
    player_id: int
    salary_year1: int   # first NEW year salary
    years: int = 2      # number of added years
    raise_pct: float | None = None
    apply: bool = False


@router.post("")
def extend(req: ExtensionIn, db: Session = Depends(get_db)):
    player = db.get(Player, req.player_id)
    if not player:
        raise HTTPException(404, "Player not found")
    if player.is_free_agent or not player.team_tricode:
        raise HTTPException(400, f"{player.name} is a free agent — use the signing endpoint instead.")

    contract = next((c for c in player.contracts if c.is_active), None)
    if not contract:
        raise HTTPException(400, f"{player.name} has no active contract to extend")

    last_season = max(s.season for s in contract.seasons)
    # Next season after current last
    cap_keys = list(CAP_HISTORY.keys())
    try:
        last_idx = cap_keys.index(last_season)
    except ValueError:
        raise HTTPException(400, f"Unknown last season {last_season}")
    new_start_idx = last_idx + 1
    new_seasons = cap_keys[new_start_idx : new_start_idx + req.years]
    if len(new_seasons) < req.years:
        raise HTTPException(400, f"Cap projections only cover through {cap_keys[-1]}")

    violations = []
    if req.years > MAX_LENGTH_EXTENSION:
        violations.append({
            "code": "EXTENSION_TOO_LONG", "severity": "BLOCKER",
            "message": f"{req.years} years exceeds max extension length {MAX_LENGTH_EXTENSION}",
        })

    last_salary = next(s.salary for s in contract.seasons if s.season == last_season)
    max_extension_y1 = max(int(last_salary * 1.4), max_salary(player.years_of_service, new_seasons[0]))
    if req.salary_year1 > max_extension_y1:
        violations.append({
            "code": "EXTENSION_EXCEEDS_MAX", "severity": "BLOCKER",
            "message": f"${req.salary_year1:,} exceeds max extension Y1 ${max_extension_y1:,}",
        })

    if not req.apply or violations:
        return {
            "valid": not violations,
            "violations": violations,
            "applied": False,
            "preview_seasons": [
                {"season": s, "salary": int(req.salary_year1 * (1 + (req.raise_pct or RAISE_PCT_BIRD)) ** i)}
                for i, s in enumerate(new_seasons)
            ],
        }

    raise_pct = req.raise_pct if req.raise_pct is not None else RAISE_PCT_BIRD
    sal = req.salary_year1
    for s in new_seasons:
        db.add(ContractSeason(
            contract_id=contract.id, season=s, salary=sal,
            option_type=OptionType.NONE, guaranteed=True,
        ))
        sal = int(sal * (1 + raise_pct))

    db.add(Transaction(
        type=TransactionType.EXTEND,
        payload={
            "player_id": player.id, "team": contract.team_tricode,
            "years": req.years, "y1": req.salary_year1, "raise_pct": raise_pct,
        },
        description=f"{player.name} extends with {contract.team_tricode}: {req.years}yr starting {new_seasons[0]} at ${req.salary_year1:,}",
        is_user_action=True,
    ))
    db.commit()
    return {"valid": True, "violations": [], "applied": True, "contract_id": contract.id}
