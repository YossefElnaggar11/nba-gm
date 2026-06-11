"""Fair market value model for free agents — v2 (calibrated to real NBA contracts).

Calibration sources (2024-25 / 2025-26 contracts):
  - Max contracts (95+): LeBron $52M, Jokic $55M, Embiid $54M, Brunson $63M (extension)
  - All-NBA (90-94): Jaylen Brown $57M (supermax), Tatum $54M (supermax), AD $43M, KAT $50M, Maxey $40M
  - Borderline All-Star (85-89): Bam Adebayo $40M (ext), Pascal Siakam $46M, OG Anunoby $35M
  - Quality starter (80-84): Hartenstein $29M (3yr/$87M), Jusuf Nurkic $20M
  - Solid role (75-79): Caruso $9M, Naji Marshall $9M, Royce O'Neale $9M
  - Bench (70-74): old DeRozan $24M (age 35 discount), Brook Lopez $13M (age)
  - Min vets: Joe Ingles $3M, Garrett Temple $3M

Position scarcity premium: centers are scarce, primary ball-handlers premium.

Used in Full GM Mode to reject lowball offers.
"""
from __future__ import annotations

from app.cba.constants import EXCEPTIONS_2026_27, cap_for


# Calibrated to 2024-25 NBA contracts — cap-relative pct by OVR tier
# Mid-tier (75-82) bumped to match reality: starters get $15-25M, quality role $10-15M
_OVR_TO_CAP_PCT = [
    (95, 0.35),   # Max contracts ($55-58M)
    (92, 0.31),   # All-NBA 1st/2nd ($48-51M)
    (90, 0.27),   # Borderline All-NBA ($42-45M)
    (88, 0.24),   # All-Star ($37-40M)
    (86, 0.21),   # Solid All-Star ($32-35M)
    (84, 0.19),   # Borderline All-Star ($30-32M, Bam tier)
    (82, 0.17),   # Top starter ($26-28M)
    (80, 0.15),   # Quality starter ($23-25M, Hartenstein tier)
    (78, 0.12),   # Mid starter ($19-21M)
    (76, 0.097),  # Borderline starter ($15-17M)
    (74, 0.075),  # Quality role player ($12-14M)
    (72, 0.055),  # Role player ($8-10M)
    (70, 0.038),  # Bench rotation ($5-7M)
    (67, 0.026),  # Deep bench ($3.5-4.5M)
    (64, 0.017),  # 12th-15th man ($2.5-3M)
]


def _base_pct_from_ovr(ovr: int) -> float:
    for threshold, pct in _OVR_TO_CAP_PCT:
        if ovr >= threshold:
            return pct
    return 0.012


def expected_market_value(overall: int | None, age: int | None, season: str = "2026-27", position: str | None = None) -> int:
    """Annual salary the player would command on the open market (Y1).

    Calibrated to 2024-25 NBA reality. Position-scarcity-aware.
    """
    if overall is None:
        return EXCEPTIONS_2026_27.minimum_2yr_vet
    cap = cap_for(season).salary_cap
    base = int(_base_pct_from_ovr(overall) * cap)

    # Position scarcity premium — quality bigs and primary ball-handlers go for more
    if position == "C":
        base = int(base * 1.18)
    elif position == "PG":
        base = int(base * 1.08)
    elif position == "PF":
        base = int(base * 1.05)

    # Age curve — steeper for declining vets. Players over 35 in lower OVR tiers
    # (i.e. role-player tier) typically take minimum contracts in real NBA.
    if age is not None:
        if age >= 38:
            base = int(base * 0.30)
        elif age >= 36:
            base = int(base * 0.45)
        elif age >= 34:
            base = int(base * 0.62)
        elif age >= 32:
            base = int(base * 0.80)
        elif age >= 30:
            base = int(base * 0.92)
        elif age <= 22:
            base = int(base * 1.10)
        elif age <= 24:
            base = int(base * 1.05)

        # Cap on aging non-stars: if age >= 35 and OVR < 84, cap at $8M
        # (this is what reality looks like — Westbrook, DeRozan-style old vets
        # don't get $14M deals)
        if age >= 35 and (overall or 0) < 84:
            base = min(base, 8_000_000)
        # If age >= 37 and OVR < 88, even tighter cap (Lopez, Lowry tier)
        if age >= 37 and (overall or 0) < 88:
            base = min(base, 5_000_000)

    return max(base, EXCEPTIONS_2026_27.minimum_2yr_vet)


def acceptance_floor(market: int) -> int:
    """Below this $/year, the player rejects the offer. Allows some negotiation room."""
    return int(market * 0.78)
