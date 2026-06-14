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


# Calibrated to 2024-25 NBA contracts — cap-relative pct by OVR tier.
# Real-life reference comps:
#   95+ supermax: Jokic $55M, Embiid $54M, SGA-tier
#   92: KAT $50M, Brunson, Maxey
#   90: AD $43M, Bam $40M
#   88: Hartenstein $28M (high), Porzingis ~$30M, Tobias Harris $30M
#   86: Anunoby $35M, Naz Reid range
#   84: Bridges $25M, RJ Barrett $25M
#   82: Caruso $9M (low usage), Aaron Gordon $22M, P.J. Washington $19M
#   80: Sochan/borderline starter ~$16M
#   78: Daniel Gafford $13M, Walker Kessler $4.9M (rookie)
#   76: Ivica Zubac $19M (anchor), bench wings ~$8-11M
#   72-74: role players $5-8M
#   <70: minimums
_OVR_TO_CAP_PCT = [
    (95, 0.35),    # Supermax/max ($55M+)
    (92, 0.31),    # All-NBA ($48-51M)
    (90, 0.27),    # Borderline All-NBA ($42-44M)
    (88, 0.22),    # Star ($33-35M, AD/KAT tier)
    (86, 0.19),    # All-Star ($28-30M)
    (84, 0.165),   # Borderline All-Star ($25-27M, Bam tier)
    (82, 0.135),   # Top starter ($20-22M)
    (80, 0.110),   # Quality starter ($16-18M)
    (78, 0.088),   # Mid starter ($13-14M)
    (76, 0.068),   # Borderline starter ($10-11M)
    (74, 0.048),   # Quality role player ($7-8M)
    (72, 0.033),   # Role player ($4.5-5.5M)
    (70, 0.022),   # Bench rotation ($3-4M)
    (67, 0.016),   # Deep bench ($2.2-2.8M)
    (64, 0.012),   # 12th-15th man (~$2M)
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

    # Position scarcity premium — primary ball-handlers and elite bigs go for more.
    # The C bonus only applies to top-tier bigs; mid/low Cs (rim runners) don't get it.
    if position == "C" and overall >= 84:
        base = int(base * 1.10)        # only elite Cs (Bam, Sabonis, Jokic, KAT)
    elif position == "PG":
        base = int(base * 1.06)
    elif position == "PF" and overall >= 84:
        base = int(base * 1.04)

    # Age curve. Decline is steeper for non-stars; legacy stars (OVR 88+) still
    # command real money in their late 30s (LeBron, Steph, KD pattern).
    if age is not None:
        ovr = overall or 0
        if age >= 38:
            if ovr >= 92: factor = 0.75      # Steph/LeBron tier
            elif ovr >= 88: factor = 0.55    # Borderline All-Star vet
            elif ovr >= 82: factor = 0.40    # Quality vet
            else: factor = 0.25              # Minimum vet
        elif age >= 36:
            if ovr >= 92: factor = 0.88
            elif ovr >= 88: factor = 0.72
            elif ovr >= 82: factor = 0.55
            else: factor = 0.42
        elif age >= 34:
            if ovr >= 92: factor = 0.96
            elif ovr >= 88: factor = 0.85
            elif ovr >= 82: factor = 0.72
            else: factor = 0.62
        elif age >= 32:
            factor = 0.95 if ovr >= 88 else 0.85
        elif age >= 30:
            factor = 0.95
        elif age <= 22:
            factor = 1.10
        elif age <= 24:
            factor = 1.05
        else:
            factor = 1.0
        base = int(base * factor)

        # Hard caps on aging non-stars (Westbrook/DeRozan tier — never gets >$8M)
        if age >= 35 and ovr < 82:
            base = min(base, 8_000_000)
        if age >= 37 and ovr < 85:
            base = min(base, 5_000_000)

    return max(base, EXCEPTIONS_2026_27.minimum_2yr_vet)


def acceptance_floor(market: int) -> int:
    """Below this $/year, the player rejects the offer. Allows some negotiation room."""
    return int(market * 0.78)
