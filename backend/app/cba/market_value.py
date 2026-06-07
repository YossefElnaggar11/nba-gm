"""Fair market value model for free agents.

Used in Full GM Mode to reject lowball offers (you can't sign Jokic to the min).
In 2026 Offseason Mode the check is skipped — anything legal under the CBA goes through.
"""
from __future__ import annotations

from app.cba.constants import EXCEPTIONS_2026_27, cap_for


def expected_market_value(overall: int | None, age: int | None, season: str = "2026-27") -> int:
    """Annual salary the player would command on the open market (year-1).

    Calibrated to 2026-27 cap ($165M):
      OVR 95+: ~$57M (max for 10+ yr)
      OVR 90:  ~$50M
      OVR 85:  ~$35M
      OVR 80:  ~$22M (above MLE)
      OVR 75:  ~$13M (MLE level)
      OVR 70:  ~$6M (BAE)
      OVR 65:  ~$3M
      OVR <65: minimum
    """
    if overall is None:
        return EXCEPTIONS_2026_27.minimum_2yr_vet
    cap = cap_for(season).salary_cap
    cap_scale = cap / 165_000_000

    if overall >= 95:
        base = int(0.34 * cap)
    elif overall >= 92:
        base = int(0.30 * cap)
    elif overall >= 88:
        base = int(0.22 * cap)
    elif overall >= 85:
        base = int(0.16 * cap)
    elif overall >= 82:
        base = int(0.11 * cap)
    elif overall >= 79:
        base = int(0.075 * cap)
    elif overall >= 75:
        base = int(0.048 * cap)
    elif overall >= 70:
        base = int(0.025 * cap)
    elif overall >= 65:
        base = int(0.012 * cap)
    else:
        base = int(2_500_000 * cap_scale)

    if age is not None:
        if age >= 36:
            base = int(base * 0.45)
        elif age >= 34:
            base = int(base * 0.65)
        elif age >= 32:
            base = int(base * 0.82)
        elif age >= 30:
            base = int(base * 0.93)
        elif age <= 23:
            base = int(base * 1.08)

    return max(base, EXCEPTIONS_2026_27.minimum_2yr_vet)


def acceptance_floor(market: int) -> int:
    """Below this $/year, the player rejects the offer. Allows some negotiation room."""
    return int(market * 0.75)
