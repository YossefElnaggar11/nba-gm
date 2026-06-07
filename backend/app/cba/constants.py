"""NBA CBA financial constants and rules.

Sourced from:
  - 2023 CBA (effective Jul 1, 2023 through Jun 30, 2030; opt-outs after 28-29)
  - NBA official 2026-27 cap announcement (May 2026)
  - Bobby Marks / ESPN projections

The 2023 CBA is the operative document for the 2026-27 season — references
to "2018-19 CBA" in conversation are out of date; we are using the current
2023 CBA which introduced the two-apron system.
"""
from __future__ import annotations

from dataclasses import dataclass


# ---------------------------------------------------------------------------
# Cap & apron levels per season (in dollars)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CapLevels:
    season: str
    salary_cap: int
    minimum_team_salary: int  # 90% of cap
    luxury_tax: int
    first_apron: int
    second_apron: int
    projected: bool = False


CAP_HISTORY: dict[str, CapLevels] = {
    "2024-25": CapLevels("2024-25", 140_588_000, 126_529_200, 170_814_000, 178_132_000, 188_931_000),
    "2025-26": CapLevels("2025-26", 154_647_000, 139_182_300, 187_895_000, 195_945_000, 207_824_000),
    "2026-27": CapLevels("2026-27", 165_000_000, 149_000_000, 201_000_000, 209_000_000, 222_000_000),
    # Forward projections at 7% growth (current trend, subject to CBA 10% max)
    "2027-28": CapLevels("2027-28", 176_550_000, 158_895_000, 215_070_000, 223_630_000, 237_540_000, projected=True),
    "2028-29": CapLevels("2028-29", 188_908_500, 170_017_650, 230_124_900, 239_284_100, 254_167_800, projected=True),
    "2029-30": CapLevels("2029-30", 202_132_095, 181_918_886, 246_233_643, 256_034_007, 271_959_546, projected=True),
}


def cap_for(season: str) -> CapLevels:
    return CAP_HISTORY[season]


# ---------------------------------------------------------------------------
# Max contract percentages (Article II of CBA)
# ---------------------------------------------------------------------------

MAX_PCT_0_6_YRS = 0.25       # players with 0-6 years of service
MAX_PCT_7_9_YRS = 0.30       # 7-9 years
MAX_PCT_10_PLUS_YRS = 0.35   # 10+ years

# Supermax (Designated Veteran Extension) requires 7-9 years AND
# All-NBA in prior season OR DPOY OR MVP in prior year (or 2 of last 3)
SUPERMAX_PCT = 0.35

# Rookie Designated Player (5th-year max) - same tiers
# Rose Rule: 5th-year max for 25% guys can rise to 30% if criteria met

# Annual raise % over starting salary
RAISE_PCT_BIRD = 0.08                  # 8% for Bird rights re-signings
RAISE_PCT_NON_BIRD = 0.05              # 5% for everyone else
RAISE_PCT_EXTEND_AND_TRADE = 0.05      # 5% for E&T

# Contract length limits
MAX_LENGTH_BIRD = 5                    # 5 years for own player (Bird)
MAX_LENGTH_OUTSIDE = 4                 # 4 years signing elsewhere
MAX_LENGTH_EXTENSION = 4               # 4 years for veteran extensions (added years)
MAX_LENGTH_VET_EXTEND_FROM_SIGN_BY = 4
MAX_LENGTH_ROOKIE_EXTENSION = 5


# ---------------------------------------------------------------------------
# Exceptions (2026-27 estimates)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ExceptionAmounts:
    season: str
    non_taxpayer_mle: int
    taxpayer_mle: int
    room_mle: int
    bi_annual: int
    minimum_2yr_vet: int


EXCEPTIONS_2026_27 = ExceptionAmounts(
    season="2026-27",
    non_taxpayer_mle=14_100_000,
    taxpayer_mle=5_700_000,
    room_mle=8_700_000,
    bi_annual=5_125_000,
    minimum_2yr_vet=2_500_000,
)


# ---------------------------------------------------------------------------
# Trade salary matching rules (2023 CBA, four tiers)
# ---------------------------------------------------------------------------
# Below tax: 200% of outgoing + $250k
# Between tax and 1st apron: 125% + $100k (classic "taxpayer" rule)
# Between 1st and 2nd apron: 110% + $100k (NEW under 2023 CBA)
# Above 2nd apron: 100% (no aggregation; cannot take back more than outgoing)
# Teams under cap: absorb up to cap space without matching


@dataclass(frozen=True)
class TradeMatchRule:
    label: str
    multiplier: float
    plus_dollars: int


TRADE_MATCH_BELOW_TAX = TradeMatchRule("below-tax", 2.00, 250_000)
TRADE_MATCH_TAXPAYER = TradeMatchRule("taxpayer", 1.25, 100_000)
TRADE_MATCH_FIRST_APRON = TradeMatchRule("first-apron", 1.10, 100_000)
TRADE_MATCH_SECOND_APRON = TradeMatchRule("second-apron-hard-capped", 1.00, 0)

# Legacy alias (kept for any imports referencing old name)
TRADE_MATCH_NON_TAXPAYER = TRADE_MATCH_BELOW_TAX

# Second apron restrictions:
#   - Cannot aggregate salaries in a trade
#   - Cannot take back more than 100% of outgoing salary
#   - Cannot use trade exceptions generated in prior season
#   - Cannot use the taxpayer MLE
#   - Frozen first-round pick 7 years out
#   - Cannot sign buyout players whose pre-buyout salary was > non-tax MLE

# First apron restrictions (in addition to luxury tax penalties):
#   - Hard cap at first apron if you use BAE, sign-and-trade as receiver,
#     use full non-tax MLE, or acquire player via S&T
#   - Cannot use trade exceptions from prior season


# ---------------------------------------------------------------------------
# Stepien rule (Article VII Section 7)
# ---------------------------------------------------------------------------
# A team cannot trade away first-round picks in consecutive future drafts.
# i.e., you must always have a 1st-rounder available in either year N or year N+1
# for any future N.


# ---------------------------------------------------------------------------
# Rookie scale (per round 1 pick slot) - 2026-27 starts
# Source: derived from CBA Exhibit B; 120% standard offer
# ---------------------------------------------------------------------------

ROOKIE_SCALE_2026_27_120PCT: dict[int, int] = {
    1: 13_300_000, 2: 11_900_000, 3: 10_700_000, 4: 9_650_000, 5: 8_700_000,
    6: 7_840_000, 7: 7_070_000, 8: 6_370_000, 9: 5_740_000, 10: 5_170_000,
    11: 4_660_000, 12: 4_200_000, 13: 3_780_000, 14: 3_530_000, 15: 3_310_000,
    16: 3_100_000, 17: 2_930_000, 18: 2_810_000, 19: 2_700_000, 20: 2_610_000,
    21: 2_520_000, 22: 2_440_000, 23: 2_370_000, 24: 2_300_000, 25: 2_230_000,
    26: 2_170_000, 27: 2_110_000, 28: 2_060_000, 29: 2_010_000, 30: 1_960_000,
}
# NB: these are projections. Final NBA-published values may differ ~2%.


# ---------------------------------------------------------------------------
# Minimum salary scale by years of service (2026-27 estimates)
# ---------------------------------------------------------------------------

MIN_SALARY_2026_27_BY_YOS: dict[int, int] = {
    0: 1_286_000,   # 0 years (rookie minimum)
    1: 2_070_000,
    2: 2_320_000,
    3: 2_405_000,
    4: 2_490_000,
    5: 2_700_000,
    6: 2_910_000,
    7: 3_120_000,
    8: 3_330_000,
    9: 3_355_000,
    10: 3_850_000,  # 10+ years
}


def min_salary(years_of_service: int, season: str = "2026-27") -> int:
    yos = min(years_of_service, 10)
    if season == "2026-27":
        return MIN_SALARY_2026_27_BY_YOS[yos]
    # Crude: scale with cap growth from 26-27 baseline
    factor = cap_for(season).salary_cap / cap_for("2026-27").salary_cap
    return int(MIN_SALARY_2026_27_BY_YOS[yos] * factor)
