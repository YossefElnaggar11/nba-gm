"""Auto-resign unsigned own-FAs at sim time.

NBA reality: if a player is an unrestricted free agent and his prior team has
Bird rights (cap hold), the prior team can re-sign him at market value over
the cap. In our sim, we don't ask the AI to make these decisions in the
offseason — instead, at sim time, we automatically re-sign any unsigned
cap-hold player to his prior team at the player's fair market value.

The user's team is not exempt: if they explicitly want a player gone, they
should *renounce* the cap hold before simming. Otherwise the player comes back
at market value (with Bird-rights raises, no CBA cap penalty).
"""
from __future__ import annotations

from datetime import date

from sqlalchemy.orm import Session

from app.cba.constants import CAP_HISTORY, RAISE_PCT_BIRD, min_salary
from app.cba.market_value import expected_market_value
from app.db.schema import (
    CapHold, Contract, ContractSeason, OptionType, Player, Transaction, TransactionType,
)


def auto_resign_unsigned_fas(db: Session, season: str) -> dict:
    """For each non-renounced cap hold whose player is still a FA at the start
    of `season`, sign the player back to that team at market value using Bird
    rights (a Bird-rights signing is automatically CBA-legal regardless of cap).

    Contract length:
      - age >= 35: 1 year
      - age < 30: 3 years
      - else: 2 years
    """
    holds = (
        db.query(CapHold)
        .filter(CapHold.renounced == False, CapHold.season == season)
        .all()
    )
    cap_keys = list(CAP_HISTORY.keys())

    signed: list[dict] = []
    skipped: list[dict] = []

    for hold in holds:
        player = db.get(Player, hold.player_id)
        if not player or not player.is_free_agent:
            continue
        try:
            start_idx = cap_keys.index(season)
        except ValueError:
            skipped.append({"player": player.name, "reason": "season out of cap range"})
            continue

        # Determine pay + length
        market = expected_market_value(player.overall, player.age, season, player.position)
        floor = min_salary(player.years_of_service or 0, season)
        salary_y1 = max(market, floor)
        age = player.age or 27
        years = 1 if age >= 35 else (3 if age < 30 else 2)
        # Don't extend past the cap projections we have data for
        years = min(years, len(cap_keys) - start_idx)

        contract = Contract(
            player_id=player.id,
            team_tricode=hold.team_tricode,
            signed_date=date.today(),
            signed_using="BIRD",
            is_active=True,
        )
        db.add(contract)
        db.flush()
        sal = salary_y1
        for s in cap_keys[start_idx:start_idx + years]:
            db.add(ContractSeason(
                contract_id=contract.id, season=s, salary=sal,
                option_type=OptionType.NONE, guaranteed=True,
            ))
            sal = int(sal * (1 + RAISE_PCT_BIRD))
        # Update player to be active again
        player.team_tricode = hold.team_tricode
        player.is_free_agent = False
        player.fa_type = None
        player.bird_years_with_team = (player.bird_years_with_team or 0) + 1
        # The cap hold is superseded by the new contract; mark it renounced so
        # the cap sheet picks up the new contract salary instead of double-counting.
        hold.renounced = True

        db.add(Transaction(
            type=TransactionType.SIGN_FA,
            payload={
                "player_id": player.id,
                "team": hold.team_tricode,
                "using": "BIRD",
                "years": years,
                "salary_year1": salary_y1,
                "auto": True,
            },
            description=f"{player.name} re-signs with {hold.team_tricode}: {years}yr ${salary_y1:,} (BIRD, auto)",
            is_user_action=False,
        ))
        signed.append({"player": player.name, "team": hold.team_tricode, "years": years, "salary_y1": salary_y1})

    db.commit()
    return {"season": season, "signed_count": len(signed), "signed": signed, "skipped": skipped}
