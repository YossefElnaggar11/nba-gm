"""Scrape NBA standings for past seasons to calibrate the sim engine.

Output: data/raw/historical_standings.json keyed by season -> list of team
win counts. Used to validate that our sim's win distribution matches reality.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from statistics import mean, stdev

from bs4 import BeautifulSoup

from app.scrapers.http_client import get


def scrape_season(season_end_year: int) -> list[dict]:
    """e.g. season_end_year=2025 fetches the 2024-25 standings."""
    url = f"https://www.basketball-reference.com/leagues/NBA_{season_end_year}_standings.html"
    html = get(url)
    soup = BeautifulSoup(html, "lxml")
    out: list[dict] = []
    for table_id in ("confs_standings_E", "confs_standings_W"):
        table = soup.find("table", id=table_id)
        if not table:
            continue
        tbody = table.find("tbody")
        for row in tbody.find_all("tr"):
            name_th = row.find("th", {"data-stat": "team_name"}) or row.find("th", {"data-stat": "team"})
            wins_td = row.find("td", {"data-stat": "wins"}) or row.find("td", {"data-stat": "win"})
            losses_td = row.find("td", {"data-stat": "losses"}) or row.find("td", {"data-stat": "loss"})
            if not name_th or not wins_td:
                continue
            name = name_th.get_text(strip=True).rstrip("*")
            wins = int(wins_td.get_text(strip=True))
            losses = int(losses_td.get_text(strip=True)) if losses_td else 82 - wins
            out.append({"team": name, "wins": wins, "losses": losses,
                        "conf": "East" if table_id.endswith("_E") else "West"})
    return out


def main():
    out_path = Path(__file__).resolve().parents[2] / "data" / "raw" / "historical_standings.json"
    data: dict[str, list[dict]] = {}
    print("Scraping historical NBA standings...")
    for year in (2021, 2022, 2023, 2024, 2025):
        try:
            rows = scrape_season(year)
            label = f"{year-1}-{str(year)[-2:]}"
            data[label] = rows
            wins = [r["wins"] for r in rows]
            if wins:
                under_500 = sum(1 for w in wins if w < 41)
                seventy_plus = sum(1 for w in wins if w >= 70)
                print(f"  {label}: {len(rows)} teams · wins {min(wins)}-{max(wins)} "
                      f"(mean {mean(wins):.1f}, std {stdev(wins):.1f}) · "
                      f"{under_500} under .500 · {seventy_plus} with 70+ wins")
        except Exception as e:
            print(f"  {year}: ERROR {e}")
    out_path.write_text(json.dumps(data, indent=2))
    print(f"\nWrote -> {out_path}")

    # Aggregate stats
    all_wins = [w for s in data.values() for w in (r["wins"] for r in s)]
    print(f"\nAcross {len(data)} seasons ({len(all_wins)} team-seasons):")
    print(f"  Win range: {min(all_wins)}-{max(all_wins)}")
    print(f"  Mean: {mean(all_wins):.1f}, std: {stdev(all_wins):.1f}")
    print(f"  70+ wins: {sum(1 for w in all_wins if w >= 70)} ({100*sum(1 for w in all_wins if w >= 70)/len(all_wins):.1f}%)")
    print(f"  65+ wins: {sum(1 for w in all_wins if w >= 65)} ({100*sum(1 for w in all_wins if w >= 65)/len(all_wins):.1f}%)")
    print(f"  60+ wins: {sum(1 for w in all_wins if w >= 60)} ({100*sum(1 for w in all_wins if w >= 60)/len(all_wins):.1f}%)")
    print(f"  Under 25 wins: {sum(1 for w in all_wins if w < 25)} ({100*sum(1 for w in all_wins if w < 25)/len(all_wins):.1f}%)")


if __name__ == "__main__":
    main()
