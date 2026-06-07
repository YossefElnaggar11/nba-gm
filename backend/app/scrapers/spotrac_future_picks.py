"""Scrape Spotrac's future draft picks page (years 2027-2032).

Spotrac shows each team's future pick obligations and rights, including
protections. Format is typically:
   Team | Year | Round | Pick (originally <Team>) | Protection text

We extract every pick (received and owed) and the protection text verbatim
plus a coarse machine-readable structure.
"""
from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path

from bs4 import BeautifulSoup

from app.scrapers.http_client import get


@dataclass
class FuturePick:
    year: int
    round: int
    owner: str           # tricode of current owner
    original: str        # tricode of originating team
    via: str | None      # if traded through intermediaries
    protection_raw: str | None
    protection_summary: str | None    # short machine-friendly tag
    is_swap: bool
    swap_with: str | None
    source: str


TEAM_NAME_TO_TRICODE = {
    "Atlanta Hawks": "ATL", "Boston Celtics": "BOS", "Brooklyn Nets": "BKN",
    "Charlotte Hornets": "CHA", "Chicago Bulls": "CHI", "Cleveland Cavaliers": "CLE",
    "Dallas Mavericks": "DAL", "Denver Nuggets": "DEN", "Detroit Pistons": "DET",
    "Golden State Warriors": "GSW", "Houston Rockets": "HOU", "Indiana Pacers": "IND",
    "LA Clippers": "LAC", "Los Angeles Clippers": "LAC",
    "Los Angeles Lakers": "LAL", "LA Lakers": "LAL",
    "Memphis Grizzlies": "MEM", "Miami Heat": "MIA", "Milwaukee Bucks": "MIL",
    "Minnesota Timberwolves": "MIN", "New Orleans Pelicans": "NOP",
    "New York Knicks": "NYK", "Oklahoma City Thunder": "OKC", "Orlando Magic": "ORL",
    "Philadelphia 76ers": "PHI", "Phoenix Suns": "PHX", "Portland Trail Blazers": "POR",
    "Sacramento Kings": "SAC", "San Antonio Spurs": "SAS", "Toronto Raptors": "TOR",
    "Utah Jazz": "UTA", "Washington Wizards": "WAS",
}


def _to_tricode(name: str) -> str | None:
    name = name.strip()
    if name in TEAM_NAME_TO_TRICODE:
        return TEAM_NAME_TO_TRICODE[name]
    # tricode already?
    if name.upper() in {t for t in TEAM_NAME_TO_TRICODE.values()}:
        return name.upper()
    return None


def _classify_protection(text: str | None) -> str | None:
    if not text:
        return None
    t = text.lower()
    if "unprotected" in t:
        return "UNPROTECTED"
    if "top-" in t or "top " in t:
        m = re.search(r"top[- ](\d+)", t)
        if m:
            return f"TOP_{m.group(1)}_PROTECTED"
    if "lottery" in t:
        return "LOTTERY_PROTECTED"
    if "swap" in t:
        return "SWAP"
    return "OTHER"


def parse_future_picks() -> list[FuturePick]:
    """Parse Spotrac's /nba/draft/future page (which lists all future picks)."""
    html = get("https://www.spotrac.com/nba/draft/future")
    soup = BeautifulSoup(html, "lxml")
    out: list[FuturePick] = []

    # Spotrac's page is a single mega-table or nested per-team. We look for any
    # table where rows look like draft pick entries.
    tables = soup.find_all("table")
    for table in tables:
        headers = [th.get_text(" ", strip=True).lower() for th in table.find_all("th")]
        if not headers:
            continue
        # heuristic — needs columns for year/round/owner/from
        if not any("year" in h for h in headers):
            continue
        body = table.find("tbody")
        if not body:
            continue
        col = {h: i for i, h in enumerate(headers)}
        for row in body.find_all("tr"):
            cells = [c.get_text(" ", strip=True) for c in row.find_all(["td", "th"])]
            if not cells:
                continue

            def col_val(*keys):
                for k in keys:
                    for h, i in col.items():
                        if k in h and i < len(cells):
                            return cells[i]
                return None

            year_s = col_val("year")
            round_s = col_val("round", "rd")
            owner_s = col_val("team", "owner", "to")
            from_s = col_val("from", "via", "original")
            protection_s = col_val("protection", "notes", "details", "type")

            if not year_s or not year_s.isdigit():
                continue
            year = int(year_s)
            if year < 2027 or year > 2032:
                continue
            round_num = 1 if round_s and "1" in round_s else (2 if round_s and "2" in round_s else 1)
            owner = _to_tricode(owner_s) if owner_s else None
            original = _to_tricode(from_s) if from_s else owner
            if not owner or not original:
                continue
            is_swap = bool(protection_s and "swap" in protection_s.lower())
            out.append(FuturePick(
                year=year, round=round_num, owner=owner, original=original,
                via=None,
                protection_raw=protection_s,
                protection_summary=_classify_protection(protection_s),
                is_swap=is_swap, swap_with=None,
                source="spotrac",
            ))
    return out


def main():
    print("Scraping Spotrac future picks 2027-2032...")
    picks = parse_future_picks()
    out_path = Path(__file__).resolve().parents[2] / "data" / "raw" / "future_picks_2027_2032.json"
    out_path.write_text(json.dumps([asdict(p) for p in picks], indent=2))
    by_year: dict[int, int] = {}
    for p in picks:
        by_year[p.year] = by_year.get(p.year, 0) + 1
    print(f"Parsed {len(picks)} future picks -> {out_path}")
    for y in sorted(by_year):
        print(f"  {y}: {by_year[y]}")


if __name__ == "__main__":
    main()
