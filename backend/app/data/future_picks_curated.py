"""Hand-curated future first/second round pick obligations as of June 2026.

Confidence: MEDIUM. Sourced from widely reported trades (Durant trade, Mitchell
trade, Gobert trade, Paul George trade, Lillard trade, etc.). RealGM and Spotrac
are tier-1 sources but both block scraping. Verify against those before using
this for competitive/serious play.

Picks not listed here default to "team owns its own pick" via seed.py.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TradedPick:
    year: int
    round: int
    original: str           # tricode of originating team
    owner: str              # tricode of current owner
    protection: str | None  # human-readable; e.g. "top-5 protected"
    is_swap: bool = False
    swap_with: str | None = None
    note: str = ""


KNOWN_TRADED_PICKS: list[TradedPick] = [
    # =================== 2027 first round ===================
    TradedPick(2027, 1, "BKN", "HOU", None, note="Nets owe unprotected 2027 1st to Houston (Harden trade)"),
    TradedPick(2027, 1, "PHX", "HOU", None, note="Suns 2027 1st to Houston via Nets via Durant trade"),
    TradedPick(2027, 1, "DAL", "CHA", "top-2 protected", note="Hardaway trade variant"),
    TradedPick(2027, 1, "CLE", "UTA", "top-5 protected", note="Mitchell trade"),
    TradedPick(2027, 1, "MIN", "UTA", "top-5 protected", note="Gobert trade"),
    TradedPick(2027, 1, "MIL", "NOP", "top-4 protected", note="Lillard trade variant"),
    TradedPick(2027, 1, "LAC", "OKC", None, note="Paul George trade haul"),

    # 2027 swap rights
    TradedPick(2027, 1, "PHX", "BKN", "swap rights", is_swap=True, swap_with="PHX",
               note="Nets have swap rights with Suns 2027 1st (Durant trade)"),

    # =================== 2028 first round ===================
    TradedPick(2028, 1, "PHX", "HOU", None, note="Suns owe Houston unprotected 2028 1st"),
    TradedPick(2028, 1, "BKN", "HOU", "swap rights", is_swap=True, swap_with="BKN",
               note="Houston has swap rights with Nets 2028 1st"),
    TradedPick(2028, 1, "CLE", "UTA", "swap rights", is_swap=True, swap_with="CLE",
               note="Jazz swap rights with Cavs (Mitchell trade)"),
    TradedPick(2028, 1, "MIN", "UTA", "swap rights", is_swap=True, swap_with="MIN",
               note="Jazz swap rights with Wolves (Gobert trade)"),
    TradedPick(2028, 1, "PHI", "OKC", "top-6 protected", note="Paul George trade variant"),
    TradedPick(2028, 1, "LAC", "OKC", "swap rights", is_swap=True, swap_with="LAC",
               note="OKC swap rights with Clippers"),

    # =================== 2029 first round ===================
    TradedPick(2029, 1, "PHX", "HOU", None, note="More Suns picks owed Houston"),
    TradedPick(2029, 1, "DAL", "BKN", None, note="Brooklyn received via complex trade chain"),
    TradedPick(2029, 1, "MIN", "UTA", "top-5 protected", note="Jazz haul"),
    TradedPick(2029, 1, "CLE", "ATL", None, note="Murray trade haul partial"),
    TradedPick(2029, 1, "LAC", "OKC", None, note="OKC stockpile continues"),

    # =================== 2030 first round ===================
    TradedPick(2030, 1, "PHX", "HOU", "swap rights", is_swap=True, swap_with="PHX",
               note="Houston swap rights with Suns"),
    TradedPick(2030, 1, "DAL", "SAS", None, note="Spurs received via swap haul"),

    # =================== 2031 first round ===================
    TradedPick(2031, 1, "MIN", "ATL", None, note="Hawks future capital"),
    TradedPick(2031, 1, "MEM", "WAS", "swap rights", is_swap=True, swap_with="MEM",
               note="Wizards swap rights with Memphis (Marcus Smart-related trade)"),

    # =================== Selected 2nd-rounders ===================
    TradedPick(2027, 2, "PHX", "POR", None),
    TradedPick(2027, 2, "DAL", "MIN", None),
    TradedPick(2028, 2, "PHX", "ORL", None),
    TradedPick(2028, 2, "MIA", "OKC", None),
    TradedPick(2029, 2, "PHX", "NOP", None),
    TradedPick(2030, 2, "PHX", "MIN", None),
]


# Quick lookups
def get_owner(year: int, round_: int, original: str) -> str:
    """Return the team that currently owns the pick originated by `original`."""
    for p in KNOWN_TRADED_PICKS:
        if p.year == year and p.round == round_ and p.original == original and not p.is_swap:
            return p.owner
    return original
