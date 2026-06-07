"""Free agent signing endpoint with full CBA validation."""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.cba.constants import (
    CAP_HISTORY, RAISE_PCT_BIRD, RAISE_PCT_NON_BIRD,
)
from app.cba.market_value import acceptance_floor, expected_market_value
from app.cba.rules import (
    Severity, SigningProposal, validate_signing,
)
from app.db.schema import (
    Contract, ContractSeason, OptionType, Player, Transaction, TransactionType,
)

router = APIRouter(prefix="/api/signings", tags=["signings"])


def get_db():
    from app.main import SessionLocal
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


class SigningIn(BaseModel):
    player_id: int
    team: str
    first_season: str = "2026-27"
    salary_year1: int
    years: int = 1
    raise_pct: float | None = None    # if None, infer from `using`
    using: str = "BIRD"                # BIRD | NON_BIRD | MLE_NON_TAX | MLE_TAX | MLE_ROOM | BAE | MIN | MAX_BIRD | MAX_NON_BIRD
    no_trade_clause: bool = False
    apply: bool = False
    career_mode: bool = False         # if True, FA rejects lowball offers


class SigningResponse(BaseModel):
    valid: bool
    violations: list[dict]
    applied: bool
    contract_id: int | None = None
    player_accepts: bool = True
    market_value: int | None = None
    explanation: str | None = None


def _build_season_salaries(first_season: str, salary_year1: int, years: int, raise_pct: float) -> list[tuple[str, int]]:
    """Generate (season, salary) pairs for the contract length."""
    cap_keys = list(CAP_HISTORY.keys())
    try:
        start_idx = cap_keys.index(first_season)
    except ValueError:
        raise HTTPException(400, f"Unknown season {first_season}")
    seasons = cap_keys[start_idx:start_idx + years]
    if len(seasons) < years:
        raise HTTPException(400, f"Cannot extend {years} years from {first_season}: cap projections missing")
    pairs = []
    sal = salary_year1
    for s in seasons:
        pairs.append((s, sal))
        sal = int(sal * (1 + raise_pct))
    return pairs


@router.post("", response_model=SigningResponse)
def sign_player(req: SigningIn, db: Session = Depends(get_db)) -> SigningResponse:
    player = db.get(Player, req.player_id)
    if not player:
        raise HTTPException(404, "Player not found")
    if not player.is_free_agent:
        raise HTTPException(400, f"{player.name} is not a free agent")

    proposal = SigningProposal(
        player_id=req.player_id,
        team=req.team.upper(),
        season=req.first_season,
        salary_year1=req.salary_year1,
        years=req.years,
        raise_pct=req.raise_pct,
        using=req.using,
    )
    violations = validate_signing(db, proposal)
    blockers = [v for v in violations if v.severity == Severity.BLOCKER]
    valid = not blockers

    contract_id: int | None = None
    applied = False

    # Market value check (Full GM Mode only)
    market = expected_market_value(player.overall, player.age, req.first_season)
    floor = acceptance_floor(market)
    player_accepts = True
    explanation = None
    if req.career_mode and req.salary_year1 < floor:
        player_accepts = False
        explanation = (
            f"{player.name} (OVR {player.overall or '?'}, age {player.age or '?'}) is demanding "
            f"about ${market:,}/yr on the open market. Won't accept ${req.salary_year1:,} "
            f"(below ${floor:,} floor)."
        )

    # NB: even if apply=True, if invalid/rejected we return 200 with applied=False
    # so the frontend can render the violations / explanation. (FastAPI's HTTPException
    # wraps the body in {detail: ...} which the typed client can't read cleanly.)
    if req.apply and not valid:
        return SigningResponse(
            valid=False,
            violations=[v.__dict__ for v in violations],
            applied=False,
            contract_id=None,
            player_accepts=player_accepts,
            market_value=market,
            explanation=explanation or "Signing is illegal under the CBA. See violations.",
        )
    if req.apply and not player_accepts:
        return SigningResponse(
            valid=valid,
            violations=[v.__dict__ for v in violations],
            applied=False,
            contract_id=None,
            player_accepts=False,
            market_value=market,
            explanation=explanation,
        )

    # Apply the signing
    if req.apply:
        raise_pct = req.raise_pct
        if raise_pct is None:
            raise_pct = RAISE_PCT_BIRD if req.using in ("BIRD", "MAX_BIRD") else RAISE_PCT_NON_BIRD
        season_pairs = _build_season_salaries(req.first_season, req.salary_year1, req.years, raise_pct)
        contract = Contract(
            player_id=player.id,
            team_tricode=req.team.upper(),
            signed_date=date.today(),
            signed_using=req.using,
            is_active=True,
            no_trade_clause=req.no_trade_clause,
        )
        db.add(contract)
        db.flush()
        for season, salary in season_pairs:
            db.add(ContractSeason(
                contract_id=contract.id, season=season, salary=salary,
                option_type=OptionType.NONE, guaranteed=True,
            ))
        # Update player
        player.team_tricode = req.team.upper()
        player.is_free_agent = False
        player.fa_type = None
        player.bird_years_with_team = 1
        # Record transaction
        db.add(Transaction(
            type=TransactionType.SIGN_FA,
            payload={
                "player_id": player.id,
                "team": req.team.upper(),
                "using": req.using,
                "years": req.years,
                "salary_year1": req.salary_year1,
                "raise_pct": raise_pct,
            },
            description=f"{player.name} signs with {req.team.upper()}: {req.years}yr ${req.salary_year1:,} ({req.using})",
            is_user_action=True,
        ))
        db.commit()
        contract_id = contract.id
        applied = True

    return SigningResponse(
        valid=valid,
        violations=[v.__dict__ for v in violations],
        applied=applied,
        contract_id=contract_id,
        player_accepts=player_accepts,
        market_value=market,
        explanation=explanation,
    )
