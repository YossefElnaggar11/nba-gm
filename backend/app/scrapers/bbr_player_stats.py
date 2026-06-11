"""Scrape BBR league-wide per-game stats for the 2025-26 season and derive
per-player ratings + potential. Output JSON keyed by bbr_id.

Rating formula (rough Hollinger-style game score, scaled to a 50-99 band):
  composite_per_g = PTS + 0.5*TRB + 0.7*AST + 1.0*STL + 0.8*BLK - 0.6*TOV
  playing_time_mult = min(1.0, MP / 25)
  overall = clamp(50, 95, 55 + composite * 1.2 * playing_time_mult)

Potential ≈ overall, with a young-player bump:
  potential = overall + max(0, 27 - age) * 0.6   (capped at 99)
"""
from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path

from bs4 import BeautifulSoup

from app.scrapers.http_client import get


@dataclass
class PlayerRating:
    bbr_id: str
    name: str
    team: str
    age: int | None
    games: int
    mpg: float
    overall: int
    potential: int
    composite: float
    ppg: float = 0.0
    rpg: float = 0.0
    apg: float = 0.0
    spg: float = 0.0
    bpg: float = 0.0
    fg_pct: float = 0.0
    three_pct: float = 0.0
    ft_pct: float = 0.0
    position: str | None = None


def _f(td) -> float | None:
    if not td:
        return None
    s = td.get_text(strip=True)
    if not s or s == "":
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _extract_bbr_id(name_th) -> str:
    a = name_th.find("a", href=True)
    if a:
        href = a["href"]
        m = re.search(r"/players/[a-z]/([a-z]+\d+)\.html", href)
        if m:
            return m.group(1)
    csk = name_th.get("csk")
    return csk or ""


def compute_rating(pts: float, trb: float, ast: float, stl: float, blk: float, tov: float, mpg: float, position: str | None = None) -> tuple[int, float]:
    # Position-aware composite — REDUCED bonuses so PGs/Cs don't dominate the leaderboard.
    if position == "C":
        composite = pts + 0.55 * trb + 0.4 * ast + 0.8 * stl + 1.0 * blk - 0.6 * tov
    elif position == "PF":
        composite = pts + 0.55 * trb + 0.5 * ast + 0.9 * stl + 0.8 * blk - 0.6 * tov
    elif position == "PG":
        composite = pts + 0.4 * trb + 0.7 * ast + 1.0 * stl + 0.5 * blk - 0.7 * tov
    else:  # SG, SF, or unknown
        composite = pts + 0.5 * trb + 0.65 * ast + 0.9 * stl + 0.7 * blk - 0.6 * tov

    mult = min(1.0, mpg / 26.0)
    raw = 55 + composite * 1.05 * mult

    # Minutes-played floor — keep but lower so role players who played heavy
    # minutes don't auto-rate as starters.
    if mpg >= 33:
        raw = max(raw, 76)   # bona fide starter
    elif mpg >= 29:
        raw = max(raw, 72)   # high-minute starter
    elif mpg >= 25:
        raw = max(raw, 68)   # rotation player

    # Lower ceiling to 96 — only true generational talents top 95.
    return max(50, min(96, int(round(raw)))), composite


def scrape_ratings() -> list[PlayerRating]:
    html = get("https://www.basketball-reference.com/leagues/NBA_2026_per_game.html")
    soup = BeautifulSoup(html, "lxml")
    table = soup.find("table", id="per_game_stats")
    if not table:
        return []
    out: list[PlayerRating] = []
    # Some players are listed multiple times (traded mid-season). The summary
    # row has team='2TM' or '3TM'. Prefer those if present.
    by_id: dict[str, PlayerRating] = {}
    for row in table.find("tbody").find_all("tr"):
        name_cell = row.find(["th", "td"], {"data-stat": "name_display"})
        if not name_cell:
            continue
        bbr_id = _extract_bbr_id(name_cell)
        if not bbr_id:
            continue
        name = name_cell.get_text(strip=True)
        team = (row.find("td", {"data-stat": "team_name_abbr"}) or row.find("td", {"data-stat": "team_id"}))
        team_str = team.get_text(strip=True) if team else ""
        games = _f(row.find("td", {"data-stat": "games"})) or 0
        if games < 5:
            continue
        mpg = _f(row.find("td", {"data-stat": "mp_per_g"})) or 0
        pts = _f(row.find("td", {"data-stat": "pts_per_g"})) or 0
        trb = _f(row.find("td", {"data-stat": "trb_per_g"})) or 0
        ast = _f(row.find("td", {"data-stat": "ast_per_g"})) or 0
        stl = _f(row.find("td", {"data-stat": "stl_per_g"})) or 0
        blk = _f(row.find("td", {"data-stat": "blk_per_g"})) or 0
        tov = _f(row.find("td", {"data-stat": "tov_per_g"})) or 0
        age = _f(row.find("td", {"data-stat": "age"}))
        pos = (row.find("td", {"data-stat": "pos"}).get_text(strip=True) if row.find("td", {"data-stat": "pos"}) else None)
        if pos and "-" in pos:
            pos = pos.split("-")[0]
        ovr, composite = compute_rating(pts, trb, ast, stl, blk, tov, mpg, pos)
        age_int = int(age) if age else None
        potential = ovr + (max(0, 27 - age_int) * 0.6 if age_int else 0)
        potential_int = min(99, int(round(potential)))
        rating = PlayerRating(
            bbr_id=bbr_id, name=name, team=team_str, age=age_int,
            games=int(games), mpg=mpg, overall=ovr, potential=potential_int,
            composite=round(composite, 1),
            ppg=pts, rpg=trb, apg=ast, spg=stl, bpg=blk,
            fg_pct=_f(row.find("td", {"data-stat": "fg_pct"})) or 0,
            three_pct=_f(row.find("td", {"data-stat": "fg3_pct"})) or 0,
            ft_pct=_f(row.find("td", {"data-stat": "ft_pct"})) or 0,
            position=pos,
        )
        prev = by_id.get(bbr_id)
        # Prefer the multi-team summary row (2TM/3TM) since it covers the whole season
        if not prev or (team_str in ("2TM", "3TM", "TOT") and prev.team not in ("2TM", "3TM", "TOT")):
            by_id[bbr_id] = rating
    out = list(by_id.values())
    return out


def main():
    print("Scraping BBR 2025-26 per-game stats...")
    ratings = scrape_ratings()
    out_path = Path(__file__).resolve().parents[2] / "data" / "raw" / "player_ratings_2026.json"
    out_path.write_text(json.dumps([asdict(r) for r in ratings], indent=2))
    print(f"Wrote {len(ratings)} player ratings -> {out_path}")
    # Print top 15 by overall
    ratings.sort(key=lambda r: -r.overall)
    print("\nTop 15 overall:")
    for r in ratings[:15]:
        print(f"  {r.overall:>2}  {r.name:<25s} {r.team:<5s} {r.mpg:>4.1f}mpg comp={r.composite}")


if __name__ == "__main__":
    main()
