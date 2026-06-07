"""Scrape Basketball-Reference team contracts pages.

For each of 30 teams, BBR publishes a page like /contracts/LAL.html with a
table of every player under contract, their salary per year (current +5),
and indicators for player options, team options, and non-guaranteed money.

We extract:
  - player_name, bbr_id, age_today
  - per-year salary dollars (csk attribute is the integer value)
  - option_type: NONE | PLAYER | TEAM
  - guaranteed: bool (False if italics — non-guaranteed)
  - team_total_guaranteed
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from bs4 import BeautifulSoup

from app.data.teams import TEAMS
from app.scrapers.http_client import get

YEAR_STATS = ["y1", "y2", "y3", "y4", "y5", "y6"]
SEASONS = ["2025-26", "2026-27", "2027-28", "2028-29", "2029-30", "2030-31"]


@dataclass
class SeasonSalary:
    season: str          # e.g. "2026-27"
    salary: int          # dollars
    option: str          # "NONE" | "PLAYER" | "TEAM"
    guaranteed: bool


@dataclass
class PlayerContract:
    bbr_id: str
    name: str
    team_tricode: str
    age: int | None
    seasons: list[SeasonSalary]
    total_guaranteed: int


def _parse_salary(td) -> tuple[int, str, bool]:
    """Return (salary_int, option_type, guaranteed)."""
    if not td:
        return 0, "NONE", True
    classes = td.get("class") or []
    if "iz" in classes:
        return 0, "NONE", True
    csk = td.get("csk")
    salary = int(csk) if csk and csk.isdigit() else 0
    if salary == 0:
        return 0, "NONE", True
    option = "NONE"
    if "salary-pl" in classes:
        option = "PLAYER"
    elif "salary-tm" in classes:
        option = "TEAM"
    # italic <i> or <em> wrapper -> non-guaranteed
    guaranteed = not (td.find("i") or td.find("em"))
    return salary, option, guaranteed


def scrape_team(tricode: str, bbr_code: str) -> list[PlayerContract]:
    url = f"https://www.basketball-reference.com/contracts/{bbr_code}.html"
    html = get(url)
    soup = BeautifulSoup(html, "lxml")
    table = soup.find("table", id="contracts")
    if not table:
        return []
    out: list[PlayerContract] = []
    tbody = table.find("tbody")
    for row in tbody.find_all("tr"):
        name_th = row.find("th", {"data-stat": "player"})
        if not name_th:
            continue
        name = name_th.get_text(strip=True)
        if not name:
            continue
        bbr_id = name_th.get("csk") or name_th.find("a", href=True)["href"].split("/")[-1].replace(".html", "") if name_th.find("a", href=True) else ""
        age_td = row.find("td", {"data-stat": "age_today"})
        age = int(age_td.get_text(strip=True)) if age_td and age_td.get_text(strip=True).isdigit() else None
        gtd_td = row.find("td", {"data-stat": "remain_gtd"})
        gtd_csk = gtd_td.get("csk") if gtd_td else None
        total_gtd = int(gtd_csk) if gtd_csk and gtd_csk.isdigit() else 0
        seasons: list[SeasonSalary] = []
        for ystat, season in zip(YEAR_STATS, SEASONS):
            td = row.find("td", {"data-stat": ystat})
            salary, opt, gtd = _parse_salary(td)
            if salary > 0:
                seasons.append(SeasonSalary(season=season, salary=salary, option=opt, guaranteed=gtd))
        out.append(PlayerContract(
            bbr_id=bbr_id, name=name, team_tricode=tricode, age=age,
            seasons=seasons, total_guaranteed=total_gtd,
        ))
    return out


def scrape_all() -> dict[str, list[PlayerContract]]:
    result: dict[str, list[PlayerContract]] = {}
    for team in TEAMS:
        try:
            contracts = scrape_team(team.tricode, team.bbr_code)
            result[team.tricode] = contracts
            print(f"  {team.tricode}: {len(contracts)} players")
        except Exception as exc:
            print(f"  {team.tricode}: ERROR {exc}")
            result[team.tricode] = []
    return result


def main():
    print("Scraping BBR contracts for all 30 teams...")
    all_contracts = scrape_all()
    out_path = Path(__file__).resolve().parents[2] / "data" / "raw" / "contracts_2026_offseason.json"
    serialised = {
        tricode: [
            {**asdict(pc), "seasons": [asdict(s) for s in pc.seasons]}
            for pc in pcs
        ]
        for tricode, pcs in all_contracts.items()
    }
    out_path.write_text(json.dumps(serialised, indent=2))
    total_players = sum(len(pcs) for pcs in all_contracts.values())
    print(f"\nWrote {total_players} player contracts across {len(all_contracts)} teams -> {out_path}")


if __name__ == "__main__":
    main()
