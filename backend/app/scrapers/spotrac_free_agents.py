"""Scrape Spotrac's free-agent listing for the upcoming 2026 offseason.

Spotrac groups FAs by type (UFA, RFA, Player Option, Team Option, Two-Way).
We extract: name, prior_team, fa_type, age, position, prior_salary, years_of_service.
"""
from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path

from bs4 import BeautifulSoup

from app.scrapers.http_client import get


@dataclass
class FreeAgent:
    name: str
    prior_team: str | None
    fa_type: str             # UFA | RFA | PO | TO | TWO_WAY
    position: str | None
    age: int | None
    prior_salary: int | None
    years_of_service: int | None


def _money(s: str | None) -> int | None:
    if not s:
        return None
    s = s.replace("$", "").replace(",", "").strip()
    if not s or s in ("-", "--"):
        return None
    try:
        return int(float(s))
    except ValueError:
        return None


FA_TYPE_MAP = {
    "unrestricted": "UFA",
    "restricted": "RFA",
    "player option": "PO",
    "team option": "TO",
    "two-way": "TWO_WAY",
    "ufa": "UFA",
    "rfa": "RFA",
    "po": "PO",
    "to": "TO",
}


def parse_free_agents() -> list[FreeAgent]:
    html = get("https://www.spotrac.com/nba/free-agents")
    soup = BeautifulSoup(html, "lxml")
    fas: list[FreeAgent] = []

    # Spotrac structures FAs in tables grouped by type, or in a single sortable table.
    # We look for any <table> with player-row structure.
    tables = soup.find_all("table")
    for table in tables:
        headers = [th.get_text(strip=True).lower() for th in table.find_all("th")]
        if not headers or "player" not in " ".join(headers):
            continue
        # Identify columns by header text
        col = {h: i for i, h in enumerate(headers)}
        body = table.find("tbody")
        if not body:
            continue
        for row in body.find_all("tr"):
            cells = row.find_all(["td", "th"])
            if not cells:
                continue
            texts = [c.get_text(" ", strip=True) for c in cells]
            # heuristic: first cell is usually player name
            name = texts[0]
            if not name or name.isdigit():
                continue
            # detect FA type by row class or a dedicated column
            row_class = " ".join(row.get("class") or []).lower()
            ftype = None
            for k, v in FA_TYPE_MAP.items():
                if k in row_class:
                    ftype = v
                    break
            # otherwise look for a 'type' column
            if not ftype:
                for h, i in col.items():
                    if "type" in h and i < len(texts):
                        for k, v in FA_TYPE_MAP.items():
                            if k in texts[i].lower():
                                ftype = v
                                break
                        break
            if not ftype:
                ftype = "UFA"  # default — most common

            prior_team = None
            age = None
            pos = None
            prior_salary = None
            yos = None
            for h, i in col.items():
                if i >= len(texts):
                    continue
                t = texts[i]
                if h in ("team", "previous team", "prior team"):
                    prior_team = t
                elif h == "age":
                    age = int(t) if t.isdigit() else None
                elif h in ("pos", "position"):
                    pos = t
                elif "salary" in h or "value" in h:
                    prior_salary = _money(t)
                elif "yrs" in h or "years" in h or "exp" in h:
                    yos = int(re.search(r"\d+", t).group()) if re.search(r"\d+", t) else None

            fas.append(FreeAgent(
                name=name, prior_team=prior_team, fa_type=ftype,
                position=pos, age=age, prior_salary=prior_salary,
                years_of_service=yos,
            ))
    return fas


def main():
    fas = parse_free_agents()
    out_path = Path(__file__).resolve().parents[2] / "data" / "raw" / "free_agents_2026.json"
    out_path.write_text(json.dumps([asdict(fa) for fa in fas], indent=2))
    print(f"Parsed {len(fas)} free agents -> {out_path}")
    by_type: dict[str, int] = {}
    for fa in fas:
        by_type[fa.fa_type] = by_type.get(fa.fa_type, 0) + 1
    print("By type:", by_type)


if __name__ == "__main__":
    main()
