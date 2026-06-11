"""Season simulation engine v4 — per-game, ORtg/DRtg driven.

Realism architecture
====================

1. **Team profiles** are derived from the roster:
   - Each player gets an offensive impact and defensive impact based on OVR,
     position, age, and prior baseline stats.
   - Top-12 rotation gets NBA-style minutes + usage shares
     (36/32/30/28/24 starters, 22/18/16/12/8/6/4 bench).
   - Team ORtg = league_avg (115) + Σ (off_impact × minutes_share).
   - Team DRtg = league_avg − Σ (def_impact × minutes_share).
   - Coaching nudges (±2 net rtg) and continuity bonuses are layered on top.

2. **Schedule** mirrors the real NBA 82-game format:
   - 4 vs each division opponent (16)
   - 4 vs 6 of 10 same-conf non-div opponents (24) + 3 vs the other 4 (12)
   - 2 vs each non-conf opponent (30)
   - Home/away split as evenly as possible per series.

3. **Injury timelines**: each player rolls 0..2 injury intervals before the
   season (start_day, end_day). Star availability, age, and bad luck all matter.
   Game-by-game availability is checked when computing today's effective ratings.

4. **Per-game sim**:
   - Compute today's home ORtg/DRtg / away ORtg/DRtg accounting for who's out.
   - Expected margin = (home.net − away.net) + HCA.
   - Sample actual margin from N(expected, ~11.6).
   - Total game scoring sampled around league pace × ORtg average.
   - Winner is recorded; team points accumulate.

5. **Player stats** are derived from total team production over 82 games:
   - share_i = (usage_i × mpg_i × availability_i) / Σ (...)
   - PPG = team_total_pts × share / games_played, etc., with per-player variance.
   - Rebounding/assists/steals/blocks weighted by position (C reb, PG ast, etc.).
   - Shooting % grounded in OVR + role.

6. **Playoffs**: best-of-7 series, per game, slightly tighter variance + bigger
   HCA. Per-player playoff stats accumulated for Finals MVP selection.

7. **Awards**:
   - MVP: top-3 seed + best stat × OVR composite + voter-style variance.
   - DPOY: anchor of top defense, weighted by blocks/steals + position bonus.
   - ROY: best rookie with 50+ games played.
   - 6MOY: bench scorer (depth rank ≥ 5) with high PPG.
   - MIP: largest YoY OVR jump (requires prior season).
   - All-NBA 1st/2nd/3rd (2G/2F/1C).
   - All-Defensive 1st/2nd (def stats + position).
   - All-Rookie 1st/2nd.

Calibration targets (matches NBA 2020-25 averages)
---------------------------------------------------
  - League avg wins/team: 41
  - Std dev across teams: ~12
  - Top seed: 60-66 wins typical; 70+ rare
  - Bottom: 14-22 wins typical
  - Avg score per team per game: ~115
  - Margin std per game: ~11.6
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import NamedTuple

from sqlalchemy.orm import Session

from app.data.teams import TEAMS, BY_TRICODE
from app.db.schema import (
    Contract, ContractSeason, DraftPick, PickStatus, Player, PlayerSeasonStats,
    Prospect, Season, TeamRecord,
)


# ---------------------------------------------------------------------------
# Calibration constants
# ---------------------------------------------------------------------------

LEAGUE_AVG_ORTG = 115.0          # modern NBA average
LEAGUE_AVG_PACE = 99.5           # possessions per 48 minutes (per team)
HCA_NET_RTG = 3.0                # home court ≈ +3 net rtg
HCA_NET_RTG_PLAYOFFS = 3.5
GAME_MARGIN_STD = 11.6           # std dev of game margin around expected
GAME_MARGIN_STD_PLAYOFFS = 10.6
TEAM_SCORE_STD = 7.5             # std dev of team's total points in a game

# NBA-style depth chart (top 12 only — others get DNP-coach decisions)
DEPTH_MPG = [36.0, 32.0, 30.0, 28.0, 24.0, 22.0, 18.0, 16.0, 12.0, 8.0, 6.0, 4.0]
DEPTH_USAGE = [0.30, 0.25, 0.21, 0.17, 0.15, 0.20, 0.18, 0.16, 0.14, 0.13, 0.12, 0.11]

# Coaching nudges (net rating points; ±2 cap). Mostly stays small —
# the bulk of strength comes from roster talent.
COACHING_NET_RTG: dict[str, float] = {
    "OKC": 2.0, "BOS": 1.8, "DEN": 1.5, "CLE": 1.4, "MIN": 1.2,
    "NYK": 1.0, "IND": 1.0, "MIA": 1.0, "HOU": 0.8, "ORL": 0.6,
    "MIL": 0.5, "DAL": 0.4, "GSW": 0.4, "SAS": 0.3, "LAL": 0.1,
    "LAC": -0.1, "PHI": -0.2, "ATL": -0.1, "MEM": 0.1, "DET": -0.1,
    "CHI": -0.4, "TOR": -0.3, "SAC": -0.4, "BKN": -0.6, "UTA": -0.5,
    "POR": -0.7, "PHX": -0.8, "NOP": -0.6, "WAS": -1.0, "CHA": -1.0,
}


def estimate_rating(salary: int, explicit: int | None = None) -> int:
    """Estimate OVR from salary if explicit unknown (legacy helper)."""
    if explicit:
        return int(explicit)
    if salary >= 55_000_000: return random.randint(91, 95)
    if salary >= 45_000_000: return random.randint(86, 92)
    if salary >= 35_000_000: return random.randint(81, 88)
    if salary >= 25_000_000: return random.randint(76, 84)
    if salary >= 15_000_000: return random.randint(71, 79)
    if salary >= 8_000_000:  return random.randint(66, 74)
    if salary >= 4_000_000:  return random.randint(60, 70)
    if salary >= 2_000_000:  return random.randint(57, 65)
    return random.randint(53, 62)


# ---------------------------------------------------------------------------
# Player & team profile builders
# ---------------------------------------------------------------------------


@dataclass
class PlayerProfile:
    pid: int
    name: str
    pos: str            # PG/SG/SF/PF/C (may be "F"/"G" fallback)
    age: int
    ovr: int
    salary: int
    baseline_ppg: float
    baseline_rpg: float
    baseline_apg: float
    baseline_spg: float
    baseline_bpg: float
    baseline_mpg: float
    rank: int = 0                              # 0=star, 1=2nd option, ...
    mpg_share: float = 0.0                     # share of team minutes (0..1)
    usage_weight: float = 0.0                  # usage rate as fraction
    off_impact: float = 0.0                    # ORtg points above league avg, weighted by min share
    def_impact: float = 0.0                    # DRtg points above league avg
    miss_intervals: list[tuple[int, int]] = field(default_factory=list)
    games_missed: int = 0


@dataclass
class TeamProfile:
    tricode: str
    conference: str
    division: str
    players: list[PlayerProfile]
    o_rtg_full: float            # full-strength ORtg
    d_rtg_full: float            # full-strength DRtg
    coach_net: float
    continuity_net: float

    def full_net_rtg(self) -> float:
        return self.o_rtg_full - self.d_rtg_full + self.coach_net + self.continuity_net


def _player_rows(db: Session, tricode: str, season: str):
    return (
        db.query(
            ContractSeason.salary, Player.name, Player.overall, Player.id,
            Player.position, Player.age, Player.baseline_ppg, Player.baseline_rpg,
            Player.baseline_apg, Player.baseline_spg, Player.baseline_bpg, Player.baseline_mpg,
        )
        .join(Contract, Contract.id == ContractSeason.contract_id)
        .join(Player, Player.id == Contract.player_id)
        .filter(
            Contract.team_tricode == tricode,
            Contract.is_active == True,
            ContractSeason.season == season,
        )
        .all()
    )


def _off_impact(p: PlayerProfile) -> float:
    """Raw per-100-poss offensive impact above replacement (75 OVR)."""
    base = (p.ovr - 75) * 0.32          # 95 OVR → +6.4; 65 OVR → -3.2
    if p.pos in ("PG", "G"):
        base *= 1.10
    elif p.pos == "SG":
        base *= 1.04
    elif p.pos == "SF":
        base *= 1.00
    elif p.pos == "PF":
        base *= 0.95
    elif p.pos == "C":
        base *= 0.90
    # Age curve
    if p.age <= 21: base *= 0.85
    elif p.age == 22: base *= 0.92
    elif p.age >= 36: base *= 0.80
    elif p.age >= 33: base *= 0.92
    return base


def _def_impact(p: PlayerProfile) -> float:
    """Raw per-100-poss defensive impact (positive = good defense)."""
    base = (p.ovr - 75) * 0.26
    if p.pos == "C":
        base *= 1.30
    elif p.pos == "PF":
        base *= 1.10
    elif p.pos == "SF":
        base *= 1.05
    elif p.pos == "SG":
        base *= 0.96
    else:  # PG/G
        base *= 0.92
    # Boost for proven defenders (high spg/bpg baselines)
    proven = (p.baseline_spg or 0) * 0.7 + (p.baseline_bpg or 0) * 1.0
    base += proven * 0.50
    # Age curve (defenders peak slightly later)
    if p.age <= 21: base *= 0.88
    elif p.age >= 36: base *= 0.82
    elif p.age >= 33: base *= 0.92
    return base


def _continuity_bonus(db: Session, players: list[PlayerProfile]) -> float:
    """Up to ~1 net rtg bonus when the top 3 have been together for years."""
    top3 = players[:3]
    if not top3:
        return 0.0
    score = 0
    for p in top3:
        pmod = db.get(Player, p.pid)
        if pmod:
            score += min(pmod.bird_years_with_team or 0, 5)
    return min(1.0, score / 15)


def build_team_profile(db: Session, tricode: str, season: str) -> TeamProfile:
    rows = _player_rows(db, tricode, season)
    team = BY_TRICODE[tricode]
    if not rows:
        # Empty roster: average team
        return TeamProfile(
            tricode=tricode, conference=team.conference, division=team.division,
            players=[],
            o_rtg_full=LEAGUE_AVG_ORTG, d_rtg_full=LEAGUE_AVG_ORTG,
            coach_net=COACHING_NET_RTG.get(tricode, 0.0), continuity_net=0.0,
        )
    # Build raw profiles + dedupe
    seen: set[int] = set()
    profs: list[PlayerProfile] = []
    for r in rows:
        salary, name, overall, pid = r[0], r[1], r[2], r[3]
        if pid in seen:
            continue
        seen.add(pid)
        rating = overall if overall else estimate_rating(salary)
        profs.append(PlayerProfile(
            pid=pid, name=name, pos=r[4] or "F", age=r[5] or 27,
            ovr=rating, salary=salary,
            baseline_ppg=r[6] or 0.0, baseline_rpg=r[7] or 0.0, baseline_apg=r[8] or 0.0,
            baseline_spg=r[9] or 0.0, baseline_bpg=r[10] or 0.0, baseline_mpg=r[11] or 0.0,
        ))
    profs.sort(key=lambda p: -p.ovr)
    # Assign depth chart, mpg share, usage
    for i, p in enumerate(profs):
        p.rank = i
        if i < len(DEPTH_MPG):
            p.mpg_share = DEPTH_MPG[i] / 240.0      # 5 positions × 48 min
            p.usage_weight = DEPTH_USAGE[i]
        else:
            p.mpg_share = 0.0
            p.usage_weight = 0.0
    # Compute ORtg / DRtg (sum of impacts weighted by minutes share)
    o_total = LEAGUE_AVG_ORTG
    d_total = LEAGUE_AVG_ORTG
    for p in profs:
        if p.mpg_share <= 0:
            continue
        p.off_impact = _off_impact(p)
        p.def_impact = _def_impact(p)
        # Each player's impact contributes proportional to their share of the 5 floor slots.
        # mpg_share is fraction of 240 total minutes; multiply by 5 to express as
        # fraction of the lineup at any moment.
        weight = p.mpg_share * 5
        o_total += p.off_impact * weight
        d_total -= p.def_impact * weight
    # Roster-completeness penalty: thin teams hurt more in 82-game grind
    rotation = sum(1 for p in profs if p.mpg_share > 0)
    if rotation < 10:
        o_total -= (10 - rotation) * 0.4
        d_total += (10 - rotation) * 0.4
    # Positional balance — penalty for missing C or PG in top 7
    top7_positions = {p.pos for p in profs[:7]}
    if "C" not in top7_positions and "PF" not in top7_positions:
        d_total += 1.5
    elif "C" not in top7_positions:
        d_total += 0.6
    if "PG" not in top7_positions and "SG" not in top7_positions and "G" not in top7_positions:
        o_total -= 1.5
    coach = COACHING_NET_RTG.get(tricode, 0.0)
    cont = _continuity_bonus(db, profs)
    return TeamProfile(
        tricode=tricode, conference=team.conference, division=team.division,
        players=profs,
        o_rtg_full=o_total, d_rtg_full=d_total,
        coach_net=coach, continuity_net=cont,
    )


def team_strength(db: Session, tricode: str, season: str = "2026-27") -> tuple[float, list[tuple[str, int]]]:
    """Compatibility shim for /api/sim/strength.  Returns a "strength" number
    (a top-8 weighted OVR) and a top-8 (name, ovr) list — preserved so the
    existing strength UI keeps working."""
    rows = _player_rows(db, tricode, season)
    if not rows:
        return 75.0, []
    rated = [(r[1], r[2] if r[2] else estimate_rating(r[0])) for r in rows]
    rated.sort(key=lambda x: -x[1])
    top8 = rated[:8]
    weights = [2.5, 2.2, 1.6, 1.3, 1.0, 0.9, 0.8, 0.7][:len(top8)]
    avg = sum(r * w for (_, r), w in zip(top8, weights)) / sum(weights)
    return avg, top8


# ---------------------------------------------------------------------------
# Injury simulation
# ---------------------------------------------------------------------------


def simulate_injury_timelines(profiles: dict[str, TeamProfile], n_games: int = 82) -> None:
    """For each rotation player, assign 0..2 injury intervals (start, end) in
    the [0, n_games) game-index space. Stars are durable, vets miss more,
    catastrophic injuries are rare (~1.5%)."""
    for prof in profiles.values():
        for p in prof.players:
            if p.mpg_share <= 0:
                continue
            # Probability of *any* significant injury this season
            if p.ovr >= 92: p_inj = 0.30
            elif p.ovr >= 85: p_inj = 0.40
            elif p.ovr >= 75: p_inj = 0.48
            else: p_inj = 0.55
            if p.age >= 35: p_inj += 0.15
            elif p.age >= 32: p_inj += 0.08
            elif p.age >= 29: p_inj += 0.03
            intervals: list[tuple[int, int]] = []
            if random.random() < p_inj:
                # Primary injury
                start = random.randint(0, n_games - 3)
                # Length: 60% minor (3-12), 30% moderate (15-30), 10% major (35-65)
                roll = random.random()
                if roll < 0.60: length = random.randint(3, 12)
                elif roll < 0.90: length = random.randint(15, 30)
                else: length = random.randint(35, 65)
                end = min(n_games - 1, start + length)
                intervals.append((start, end))
            # Possible secondary injury (lower prob)
            if random.random() < 0.18:
                start = random.randint(0, n_games - 3)
                length = random.randint(2, 12)
                end = min(n_games - 1, start + length)
                # Skip if overlapping completely
                intervals.append((start, end))
            # Rare catastrophic season-ender
            if random.random() < 0.015:
                start = random.randint(0, n_games - 20)
                end = n_games - 1
                intervals = [(start, end)]
            # Total games missed (union of intervals — approx by max)
            days_out = set()
            for s, e in intervals:
                for d in range(s, e + 1):
                    days_out.add(d)
            p.miss_intervals = intervals
            p.games_missed = len(days_out)


def _is_available(p: PlayerProfile, day: int) -> bool:
    for s, e in p.miss_intervals:
        if s <= day <= e:
            return False
    return True


# ---------------------------------------------------------------------------
# Schedule generation
# ---------------------------------------------------------------------------


class Game(NamedTuple):
    home: str
    away: str
    day: int       # 0..81 within each team's calendar (we use a global day too)


def build_schedule(profiles: dict[str, TeamProfile]) -> dict[str, list[Game]]:
    """Generate an 82-game schedule per team that mirrors the real NBA format.

    Returns a dict tricode → list of 82 Games (in random calendar order),
    where each Game records (home, away, day_index for that team).
    """
    teams_by_div: dict[str, list[str]] = {}
    teams_by_conf: dict[str, list[str]] = {}
    for prof in profiles.values():
        teams_by_div.setdefault(prof.division, []).append(prof.tricode)
        teams_by_conf.setdefault(prof.conference, []).append(prof.tricode)

    # Build pairwise matchup counts: how many games team A plays vs team B
    matchups: dict[tuple[str, str], int] = {}
    tricodes = list(profiles.keys())
    for a in tricodes:
        a_prof = profiles[a]
        same_conf_non_div = [b for b in teams_by_conf[a_prof.conference]
                             if b != a and b not in teams_by_div[a_prof.division]]
        same_div = [b for b in teams_by_div[a_prof.division] if b != a]
        non_conf = [b for b in tricodes if profiles[b].conference != a_prof.conference]
        # 4 vs each division opp
        for b in same_div:
            matchups[(a, b)] = matchups.get((a, b), 0) + 2  # 2 home games each = 4 total
        # 4 vs 6 same-conf non-div + 3 vs other 4
        random.shuffle(same_conf_non_div)
        for i, b in enumerate(same_conf_non_div):
            if i < 6:
                matchups[(a, b)] = matchups.get((a, b), 0) + 2   # 2H + 2A = 4 games
            else:
                # 3 games: 2H 1A or 1H 2A — alternate
                home_count = 2 if i % 2 == 0 else 1
                matchups[(a, b)] = matchups.get((a, b), 0) + home_count
        # 2 vs each non-conf opp (1H 1A)
        for b in non_conf:
            matchups[(a, b)] = matchups.get((a, b), 0) + 1

    # Construct game list (each (a,b) entry above is # of games team a hosts vs team b)
    schedule_per_team: dict[str, list[Game]] = {t: [] for t in tricodes}
    for (home, away), n_home in matchups.items():
        for _ in range(n_home):
            day = random.randint(0, 81)
            game = Game(home=home, away=away, day=day)
            schedule_per_team[home].append(game)
            schedule_per_team[away].append(game)

    # Pad/trim if mismatches (should rarely be needed; safety net for integer rounding)
    for t in tricodes:
        games = schedule_per_team[t]
        if len(games) > 82:
            schedule_per_team[t] = games[:82]
        elif len(games) < 82:
            # Add filler games vs random opponents
            while len(schedule_per_team[t]) < 82:
                other = random.choice([x for x in tricodes if x != t])
                day = random.randint(0, 81)
                schedule_per_team[t].append(Game(home=t, away=other, day=day))
        # Sort each team's calendar by day
        schedule_per_team[t].sort(key=lambda g: g.day)
    return schedule_per_team


# ---------------------------------------------------------------------------
# Per-game simulation
# ---------------------------------------------------------------------------


def _effective_ratings(prof: TeamProfile, day: int) -> tuple[float, float]:
    """Recompute today's ORtg/DRtg with absent players subtracted out and
    bench guys taking their share."""
    # Identify active players in the top 12
    active_in_top12: list[PlayerProfile] = []
    benchwarmers: list[PlayerProfile] = []
    for i, p in enumerate(prof.players):
        if i < 12 and _is_available(p, day):
            active_in_top12.append(p)
        elif _is_available(p, day):
            benchwarmers.append(p)
    # Find how many of the top-12 slots are open due to injury
    slots_open = 12 - len(active_in_top12)
    # Fill open slots with the next available benchwarmers
    fill = benchwarmers[:slots_open]
    floor = active_in_top12 + fill
    if not floor:
        # No one available — return weak default
        return LEAGUE_AVG_ORTG - 6, LEAGUE_AVG_ORTG + 6
    # Reassign minutes_share to active players using DEPTH_MPG by rank (within today's lineup)
    o = LEAGUE_AVG_ORTG
    d = LEAGUE_AVG_ORTG
    for i, p in enumerate(floor[:12]):
        share = DEPTH_MPG[i] / 240.0
        weight = share * 5
        o += p.off_impact * weight
        d -= p.def_impact * weight
    # Coaching + continuity always apply (system, not player-dependent)
    o += prof.coach_net * 0.5
    d -= prof.coach_net * 0.5
    o += prof.continuity_net * 0.5
    d -= prof.continuity_net * 0.5
    return o, d


@dataclass
class GameResult:
    home: str
    away: str
    home_pts: int
    away_pts: int
    home_won: bool
    day: int


def simulate_game(home_prof: TeamProfile, away_prof: TeamProfile, day: int,
                  is_playoff: bool = False) -> GameResult:
    home_o, home_d = _effective_ratings(home_prof, day)
    away_o, away_d = _effective_ratings(away_prof, day)
    # Correct net-rtg formula: margin per 100 = NetRtg(home) - NetRtg(away)
    home_net = home_o - home_d
    away_net = away_o - away_d
    expected_margin_per_100 = home_net - away_net
    # Convert to points: 99.5 poss / team / game so the per-100 ratio scales 1:1.
    expected_margin = expected_margin_per_100 * (LEAGUE_AVG_PACE / 100.0)
    # Home court advantage
    expected_margin += (HCA_NET_RTG_PLAYOFFS if is_playoff else HCA_NET_RTG)
    # Cap absurdly large expected margins (NBA real top diff ≈ ±14)
    expected_margin = max(-22.0, min(22.0, expected_margin))
    margin_std = GAME_MARGIN_STD_PLAYOFFS if is_playoff else GAME_MARGIN_STD
    actual_margin = random.gauss(expected_margin, margin_std)
    # Total scoring: each team's expected points uses the (their_O + opp_D - league_avg) formula.
    home_exp_pts = home_o + (away_d - LEAGUE_AVG_ORTG)
    away_exp_pts = away_o + (home_d - LEAGUE_AVG_ORTG)
    avg_total_per_100 = home_exp_pts + away_exp_pts
    avg_total = avg_total_per_100 * (LEAGUE_AVG_PACE / 100.0)
    if is_playoff: avg_total -= 5.0   # playoff defenses tighten
    total_points = max(160.0, random.gauss(avg_total, TEAM_SCORE_STD * 1.4))
    home_pts = round((total_points + actual_margin) / 2)
    away_pts = round((total_points - actual_margin) / 2)
    if home_pts == away_pts:  # no ties in NBA
        if random.random() < 0.5: home_pts += 1
        else: away_pts += 1
    return GameResult(
        home=home_prof.tricode, away=away_prof.tricode,
        home_pts=home_pts, away_pts=away_pts,
        home_won=home_pts > away_pts, day=day,
    )


# ---------------------------------------------------------------------------
# Season aggregation
# ---------------------------------------------------------------------------


@dataclass
class SimResult:
    season: str
    standings: dict[str, dict] = field(default_factory=dict)
    east_seeds: list[str] = field(default_factory=list)
    west_seeds: list[str] = field(default_factory=list)
    playoff_results: dict[str, str] = field(default_factory=dict)
    champion: str | None = None
    finals_mvp: str | None = None
    mvp: str | None = None
    mvp_team: str | None = None
    dpoy: str | None = None
    dpoy_team: str | None = None
    roy: str | None = None
    roy_team: str | None = None
    six_man: str | None = None
    six_man_team: str | None = None
    mip: str | None = None
    mip_team: str | None = None
    injuries: dict[int, int] = field(default_factory=dict)
    all_nba_first: list[dict] = field(default_factory=list)
    all_nba_second: list[dict] = field(default_factory=list)
    all_nba_third: list[dict] = field(default_factory=list)
    all_defensive_first: list[dict] = field(default_factory=list)
    all_defensive_second: list[dict] = field(default_factory=list)
    all_rookie_first: list[dict] = field(default_factory=list)
    all_rookie_second: list[dict] = field(default_factory=list)
    all_stars_east: list[dict] = field(default_factory=list)
    all_stars_west: list[dict] = field(default_factory=list)
    # Per-team season totals (for stat aggregation)
    team_totals: dict[str, dict] = field(default_factory=dict)


def simulate_regular_season(db: Session, season: str) -> tuple[SimResult, dict[str, TeamProfile]]:
    result = SimResult(season=season)
    # 1. Build all team profiles
    profiles: dict[str, TeamProfile] = {
        t.tricode: build_team_profile(db, t.tricode, season) for t in TEAMS
    }
    # 2. Simulate injury timelines
    simulate_injury_timelines(profiles, n_games=82)
    # Track games missed for SimResult
    for prof in profiles.values():
        for p in prof.players:
            if p.games_missed > 0:
                result.injuries[p.pid] = p.games_missed
    # 3. Build schedule
    schedule_per_team = build_schedule(profiles)
    # 4. Flatten to a global list of games (each game appears once — host side)
    seen_game_keys: set[int] = set()
    global_games: list[Game] = []
    for t, games in schedule_per_team.items():
        for g in games:
            if g.home == t:   # only add from hosting team's calendar (dedup)
                key = id(g)
                if key not in seen_game_keys:
                    seen_game_keys.add(key)
                    global_games.append(g)
    # Initialise standings & totals
    for prof in profiles.values():
        result.standings[prof.tricode] = {
            "wins": 0, "losses": 0, "home_wins": 0, "away_wins": 0,
            "conference": prof.conference,
            "rating": round(prof.full_net_rtg() + 100, 1),   # display: 100 = avg
            "league_avg": 100.0,
            "o_rtg": round(prof.o_rtg_full + prof.coach_net * 0.5 + prof.continuity_net * 0.5, 1),
            "d_rtg": round(prof.d_rtg_full - prof.coach_net * 0.5 - prof.continuity_net * 0.5, 1),
            "net_rtg": round(prof.full_net_rtg(), 1),
            "points_for": 0, "points_against": 0,
        }
        result.team_totals[prof.tricode] = {
            "team_pts": 0, "opp_pts": 0, "games_played": 0,
            "wins": 0, "losses": 0,
        }
    # 5. Simulate each game
    for g in global_games:
        home_prof = profiles[g.home]
        away_prof = profiles[g.away]
        gr = simulate_game(home_prof, away_prof, g.day, is_playoff=False)
        s_home = result.standings[g.home]
        s_away = result.standings[g.away]
        s_home["points_for"] += gr.home_pts
        s_home["points_against"] += gr.away_pts
        s_away["points_for"] += gr.away_pts
        s_away["points_against"] += gr.home_pts
        if gr.home_won:
            s_home["wins"] += 1
            s_home["home_wins"] += 1
            s_away["losses"] += 1
        else:
            s_away["wins"] += 1
            s_away["away_wins"] += 1
            s_home["losses"] += 1
        result.team_totals[g.home]["team_pts"] += gr.home_pts
        result.team_totals[g.home]["opp_pts"] += gr.away_pts
        result.team_totals[g.home]["games_played"] += 1
        result.team_totals[g.away]["team_pts"] += gr.away_pts
        result.team_totals[g.away]["opp_pts"] += gr.home_pts
        result.team_totals[g.away]["games_played"] += 1
    # 6. Seed each conference (tiebreakers: wins, then net rtg)
    for conf in ("East", "West"):
        teams = [t for t in result.standings if result.standings[t]["conference"] == conf]
        teams.sort(key=lambda t: (-result.standings[t]["wins"], -result.standings[t]["net_rtg"]))
        if conf == "East":
            result.east_seeds = teams
        else:
            result.west_seeds = teams
    return result, profiles


# ---------------------------------------------------------------------------
# Per-player season stats (derived from team totals + usage shares)
# ---------------------------------------------------------------------------


def _generate_player_season_stats(db: Session, sim: SimResult,
                                  profiles: dict[str, TeamProfile], season: str) -> int:
    db.query(PlayerSeasonStats).filter(PlayerSeasonStats.season == season).delete()
    db.flush()
    count = 0
    # Position-specific weights for distributing team rebound/assist/steal/block totals
    POS_REB = {"C": 2.6, "PF": 1.9, "SF": 1.1, "SG": 0.75, "PG": 0.65, "F": 1.5, "G": 0.7}
    POS_AST = {"PG": 2.6, "G": 2.2, "SG": 1.15, "SF": 1.0, "PF": 0.65, "F": 0.8, "C": 0.65}
    POS_STL = {"PG": 1.4, "SG": 1.25, "SF": 1.1, "PF": 0.9, "C": 0.7, "G": 1.3, "F": 1.0}
    POS_BLK = {"C": 3.2, "PF": 1.4, "SF": 0.5, "SG": 0.25, "PG": 0.15, "F": 0.9, "G": 0.2}

    for tricode, prof in profiles.items():
        if not prof.players:
            continue
        team_games_played = sim.team_totals[tricode]["games_played"]
        team_pts = sim.team_totals[tricode]["team_pts"]
        team_ppg = team_pts / team_games_played if team_games_played else 0

        # Build active rotation with availability fractions
        rotation: list[tuple[PlayerProfile, float, int]] = []   # (player, availability_factor, games_played)
        for p in prof.players:
            if p.mpg_share <= 0:
                continue
            gp = max(0, 82 - p.games_missed)
            if gp < 1:
                continue
            availability = gp / 82
            rotation.append((p, availability, gp))

        # Total team weights per stat (mpg × pos_factor × availability)
        def _ovr_factor(o: int) -> float:
            return 0.5 + max(0.0, (o - 65) / 30)  # 65 OVR=0.5, 80=1.0, 95=1.5

        # Scoring share semantics: each player's share of team scoring per game played
        # = usage_rate × (his minutes / 48). Sum across the rotation ≈ 1.0.
        # Rebound/assist/steal/block shares use position-weighted minutes with a
        # gentle OVR bump so all-stars do their thing on both sides of the ledger.
        scoring_units: list[float] = []
        reb_units: list[float] = []
        ast_units: list[float] = []
        stl_units: list[float] = []
        blk_units: list[float] = []
        for p, _avail, _gp in rotation:
            mpg = DEPTH_MPG[p.rank]
            ovrf_mild = 0.75 + max(0.0, (p.ovr - 70) / 50)    # 70 → 0.75, 95 → 1.25
            # Usage already encodes role; layer in a small star adjustment so a
            # 95-OVR top option scores a touch more than an 80-OVR top option.
            usage_adj = p.usage_weight * (0.85 + max(0.0, (p.ovr - 70) / 90))
            scoring_units.append(usage_adj * (mpg / 48))
            reb_units.append(POS_REB.get(p.pos, 1.1) * mpg * ovrf_mild)
            ast_units.append(POS_AST.get(p.pos, 1.0) * mpg * ovrf_mild)
            stl_units.append(POS_STL.get(p.pos, 1.0) * mpg * (0.85 + ovrf_mild * 0.2))
            blk_units.append(POS_BLK.get(p.pos, 0.6) * mpg * (0.8 + ovrf_mild * 0.25))
        sum_scoring = sum(scoring_units) or 1.0
        sum_reb = sum(reb_units) or 1.0
        sum_ast = sum(ast_units) or 1.0
        sum_stl = sum(stl_units) or 1.0
        sum_blk = sum(blk_units) or 1.0

        # NBA team totals (per game): adjusted slightly by team rating
        net = prof.full_net_rtg()
        team_total_rpg = 43.5 + max(-2, min(2, net * 0.2))      # ~43.5 ± 2
        team_total_apg = 26.5 + max(-2, min(3, net * 0.3))      # better teams pass more
        team_total_spg = 7.6
        team_total_bpg = 5.0

        for i, (p, avail, games_played) in enumerate(rotation):
            mpg_val = DEPTH_MPG[p.rank]
            started = games_played if p.rank < 5 else (games_played // 4 if p.rank < 8 else 0)

            ppg_variance = random.uniform(0.92, 1.08)
            scoring_share = scoring_units[i] / sum_scoring
            ppg = team_ppg * scoring_share * ppg_variance

            # Realism guardrails — only superstars (90+) hit 30+ PPG sustainably
            if p.ovr < 90 and ppg > 28: ppg = 28 + (ppg - 28) * 0.35
            if p.ovr < 86 and ppg > 25: ppg = 25 + (ppg - 25) * 0.45
            if p.ovr < 80 and ppg > 22: ppg = 22 + (ppg - 22) * 0.55

            rpg_share = reb_units[i] / sum_reb
            ast_share = ast_units[i] / sum_ast
            stl_share = stl_units[i] / sum_stl
            blk_share = blk_units[i] / sum_blk

            rpg_derived = team_total_rpg * rpg_share * random.uniform(0.88, 1.12)
            apg_derived = team_total_apg * ast_share * random.uniform(0.88, 1.12)
            spg_derived = team_total_spg * stl_share * random.uniform(0.85, 1.15)
            bpg_derived = team_total_bpg * blk_share * random.uniform(0.85, 1.15)

            # Blend with prior-year baseline (when available): 55% baseline + 45% derived,
            # so traded players' new context still moves their numbers but their established
            # production carries through.
            rpg = (p.baseline_rpg * 0.55 + rpg_derived * 0.45) if p.baseline_rpg > 0 else rpg_derived
            apg = (p.baseline_apg * 0.55 + apg_derived * 0.45) if p.baseline_apg > 0 else apg_derived
            spg = (p.baseline_spg * 0.55 + spg_derived * 0.45) if p.baseline_spg > 0 else spg_derived
            bpg = (p.baseline_bpg * 0.55 + bpg_derived * 0.45) if p.baseline_bpg > 0 else bpg_derived

            rpg = max(0.3, rpg)
            apg = max(0.2, apg)
            spg = max(0.15, spg)
            bpg = max(0.05, bpg)
            mpg = mpg_val

            # Shooting %s — efficiency rises with OVR but never absurd
            fg_base = 0.45 + max(0, p.ovr - 78) * 0.0035
            fg = max(0.36, min(0.62, random.gauss(fg_base, 0.030)))
            # Bigs shoot higher FG%, guards lower
            if p.pos == "C": fg = min(0.65, fg + 0.04)
            elif p.pos in ("PG", "G"): fg = max(0.36, fg - 0.02)
            three_base = 0.34 + max(0, p.ovr - 78) * 0.002
            if p.pos == "C": three_base -= 0.05
            elif p.pos in ("PG", "SG", "SF"): three_base += 0.02
            three = max(0.20, min(0.46, random.gauss(three_base, 0.040)))
            ft_base = 0.76 + max(0, p.ovr - 78) * 0.002
            if p.pos == "C": ft_base -= 0.06
            ft = max(0.55, min(0.96, random.gauss(ft_base, 0.050)))

            stats = PlayerSeasonStats(
                player_id=p.pid, season=season, team_tricode=tricode,
                games_played=games_played, games_started=started,
                mpg=round(mpg, 1),
                ppg=round(ppg, 1), rpg=round(rpg, 1), apg=round(apg, 1),
                spg=round(spg, 1), bpg=round(bpg, 1),
                fg_pct=round(fg, 3), three_pct=round(three, 3), ft_pct=round(ft, 3),
                is_injured=p.games_missed >= 20,
            )
            db.add(stats)
            count += 1
    db.commit()
    return count


# ---------------------------------------------------------------------------
# Playoffs (per-game best-of-7 with playoff stat tracking)
# ---------------------------------------------------------------------------


@dataclass
class PlayoffStat:
    ppg: float = 0.0
    rpg: float = 0.0
    apg: float = 0.0
    games: int = 0


def _simulate_series(home_prof: TeamProfile, away_prof: TeamProfile,
                     playoff_stats: dict[str, dict[int, PlayoffStat]]) -> tuple[str, int, int]:
    """Best-of-7. home_prof has home court (games 1,2,5,7). Track per-game player
    stats in playoff_stats[tricode][pid]."""
    wins_h = wins_a = 0
    home_pattern = [home_prof.tricode, home_prof.tricode, away_prof.tricode, away_prof.tricode,
                    home_prof.tricode, away_prof.tricode, home_prof.tricode]
    for i in range(7):
        host = home_pattern[i]
        if host == home_prof.tricode:
            gr = simulate_game(home_prof, away_prof, day=82 + i, is_playoff=True)
        else:
            gr = simulate_game(away_prof, home_prof, day=82 + i, is_playoff=True)
        # Distribute the game's points to player playoff stat trackers
        for prof, pts_team in ((home_prof, gr.home_pts if host == home_prof.tricode else gr.away_pts),
                               (away_prof, gr.away_pts if host == home_prof.tricode else gr.home_pts)):
            ps = playoff_stats.setdefault(prof.tricode, {})
            # Compute scoring share for available players
            available = [p for p in prof.players if _is_available(p, 82 + i) and p.mpg_share > 0]
            units = [(p, p.usage_weight * p.mpg_share) for p in available]
            total = sum(u for _, u in units) or 1.0
            for p, u in units:
                share = u / total
                ppg_inst = pts_team * share * random.uniform(0.85, 1.15)
                # Star elevation in playoffs
                if p.rank == 0: ppg_inst *= 1.10
                stat = ps.setdefault(p.pid, PlayoffStat())
                stat.ppg += ppg_inst
                stat.rpg += {"C": 1.0, "PF": 0.85, "SF": 0.55, "PG": 0.35, "SG": 0.40}.get(p.pos, 0.55) * (DEPTH_MPG[p.rank] / 6) * random.uniform(0.7, 1.3)
                stat.apg += {"PG": 1.0, "G": 0.9, "SG": 0.55, "SF": 0.50, "PF": 0.35, "C": 0.30}.get(p.pos, 0.5) * (DEPTH_MPG[p.rank] / 8) * random.uniform(0.7, 1.3)
                stat.games += 1
        # Update series count based on home/away mapping
        if host == home_prof.tricode:
            if gr.home_won: wins_h += 1
            else: wins_a += 1
        else:
            if gr.home_won: wins_a += 1
            else: wins_h += 1
        if wins_h == 4 or wins_a == 4:
            break
    if wins_h > wins_a:
        return home_prof.tricode, wins_h, wins_a
    return away_prof.tricode, wins_a, wins_h


def simulate_playoffs(db: Session, sim: SimResult, profiles: dict[str, TeamProfile],
                      season: str) -> None:
    playoff_stats: dict[str, dict[int, PlayoffStat]] = {}

    def bracket(seeds: list[str], pairs: list[tuple[int, int]], label: str) -> list[str]:
        winners = []
        for a_idx, b_idx in pairs:
            a, b = seeds[a_idx], seeds[b_idx]
            # Higher seed (lower idx) gets home court
            if a_idx < b_idx:
                home_prof, away_prof = profiles[a], profiles[b]
            else:
                home_prof, away_prof = profiles[b], profiles[a]
            winner, _, _ = _simulate_series(home_prof, away_prof, playoff_stats)
            winners.append(winner)
            loser = b if winner == a else a
            sim.playoff_results.setdefault(loser, label)
        return winners

    east8 = sim.east_seeds[:8]
    west8 = sim.west_seeds[:8]
    r1 = [(0, 7), (3, 4), (2, 5), (1, 6)]
    east_r2 = bracket(east8, r1, "R1")
    west_r2 = bracket(west8, r1, "R1")
    east_cf = bracket(east_r2, [(0, 1), (2, 3)], "R2")
    west_cf = bracket(west_r2, [(0, 1), (2, 3)], "R2")
    east_champ = bracket(east_cf, [(0, 1)], "CONF_FINALS")[0]
    west_champ = bracket(west_cf, [(0, 1)], "CONF_FINALS")[0]
    # Finals: home court goes to better record
    ec_wins = sim.standings[east_champ]["wins"]
    wc_wins = sim.standings[west_champ]["wins"]
    if ec_wins >= wc_wins:
        home_prof = profiles[east_champ]
        away_prof = profiles[west_champ]
    else:
        home_prof = profiles[west_champ]
        away_prof = profiles[east_champ]
    champ, _, _ = _simulate_series(home_prof, away_prof, playoff_stats)
    sim.champion = champ
    runner_up = east_champ if champ == west_champ else west_champ
    sim.playoff_results[champ] = "CHAMPION"
    sim.playoff_results[runner_up] = "FINALS"
    # Finals MVP: best playoff scorer on champion (with rating weight)
    champ_stats = playoff_stats.get(champ, {})
    best_score = -1
    best_pid = None
    for p in profiles[champ].players:
        st = champ_stats.get(p.pid)
        if not st or st.games == 0:
            continue
        per_game = st.ppg / st.games
        # Score combines per-game prod + OVR + small variance
        score = per_game + (st.rpg / st.games) * 0.4 + (st.apg / st.games) * 0.6 + p.ovr * 0.3 + random.uniform(-1, 1)
        if score > best_score:
            best_score = score
            best_pid = p.pid
    if best_pid is not None:
        winner_p = next((p for p in profiles[champ].players if p.pid == best_pid), None)
        if winner_p:
            sim.finals_mvp = winner_p.name


# ---------------------------------------------------------------------------
# Awards
# ---------------------------------------------------------------------------


def _player_pos_bucket(pos: str) -> str:
    """Bucket positions to G/F/C for All-NBA / All-Def."""
    if pos in ("PG", "SG", "G"): return "G"
    if pos in ("SF", "PF", "F"): return "F"
    if pos == "C": return "C"
    return "F"


def select_awards(db: Session, sim: SimResult, profiles: dict[str, TeamProfile],
                  season: str) -> None:
    # Pre-fetch all season stats once
    rows = db.query(PlayerSeasonStats).filter(PlayerSeasonStats.season == season).all()
    stats_by_pid = {r.player_id: r for r in rows}

    # Build a flat list of (profile_player, stat, tricode)
    pool: list[dict] = []
    for tricode, prof in profiles.items():
        for p in prof.players:
            st = stats_by_pid.get(p.pid)
            if not st:
                continue
            pool.append({
                "player": p, "stat": st, "tricode": tricode,
                "wins": sim.standings[tricode]["wins"],
                "conference": prof.conference,
                "net_rtg": sim.standings[tricode]["net_rtg"],
                "team_d_rtg": sim.standings[tricode]["d_rtg"],
            })

    # ---- MVP ----
    # Top-3 seed + best stat × OVR composite; small chance of upset from #4-6 seeds
    top_teams_sorted = sorted(profiles.keys(), key=lambda t: -sim.standings[t]["wins"])
    top6 = set(top_teams_sorted[:6])
    mvp_cands = []
    for entry in pool:
        p, st, tri = entry["player"], entry["stat"], entry["tricode"]
        if tri not in top6: continue
        if p.ovr < 84: continue            # MVPs are virtually always superstars
        if st.games_played < 60: continue  # availability requirement
        stat_score = st.ppg + st.apg * 0.7 + st.rpg * 0.45 + st.spg * 1.2 + st.bpg * 1.0
        # Efficiency bump
        ts_proxy = st.fg_pct + st.three_pct * 0.5 + st.ft_pct * 0.2
        rating_factor = max(0.0, (p.ovr - 70) / 22) ** 1.3
        seed_factor = 1.15 if tri in set(top_teams_sorted[:3]) else 1.0
        score = stat_score * rating_factor * seed_factor + ts_proxy * 8
        mvp_cands.append((score, p.name, tri))
    if mvp_cands:
        mvp_cands.sort(key=lambda x: -x[0])
        top3 = mvp_cands[:3]
        weights = [4.0, 1.5, 1.0][:len(top3)]
        choice = random.choices(top3, weights=weights, k=1)[0]
        sim.mvp = choice[1]
        sim.mvp_team = choice[2]

    # ---- DPOY ----
    # Defensive anchor: high spg+bpg, on a top-10 defense, position bonus for big men.
    defense_sorted = sorted(profiles.keys(), key=lambda t: sim.standings[t]["d_rtg"])
    top_def = set(defense_sorted[:10])
    dpoy_cands = []
    for entry in pool:
        p, st, tri = entry["player"], entry["stat"], entry["tricode"]
        if p.name == sim.mvp: continue
        if st.games_played < 55: continue
        if tri not in top_def: continue
        pos_b = {"C": 1.35, "PF": 1.12, "SF": 1.0, "SG": 0.9, "PG": 0.88}.get(p.pos, 1.0)
        score = (st.spg * 2.8 + st.bpg * 3.5 + st.rpg * 0.35) * pos_b + (p.ovr - 75) * 0.15
        dpoy_cands.append((score, p.name, tri))
    if dpoy_cands:
        dpoy_cands.sort(key=lambda x: -x[0])
        top3 = dpoy_cands[:3]
        weights = [3.0, 1.5, 1.0][:len(top3)]
        choice = random.choices(top3, weights=weights, k=1)[0]
        sim.dpoy = choice[1]
        sim.dpoy_team = choice[2]

    # ---- ROY ----
    draft_year = int(season.split("-")[0])
    rookies = (
        db.query(Player)
        .join(Prospect, Prospect.created_player_id == Player.id)
        .filter(Prospect.draft_year == draft_year)
        .all()
    )
    roy_cands = []
    for r in rookies:
        st = stats_by_pid.get(r.id)
        if not st or st.games_played < 50: continue
        score = st.ppg + st.rpg * 0.5 + st.apg * 0.8 + st.spg * 1.0 + st.bpg * 1.0
        roy_cands.append((score, r.name, r.team_tricode, r.id, st))
    roy_cands.sort(key=lambda x: -x[0])
    if roy_cands:
        sim.roy = roy_cands[0][1]
        sim.roy_team = roy_cands[0][2]

    # ---- 6MOY: bench scorer (rank 5+) on a winning team ----
    six_cands = []
    for entry in pool:
        p, st, tri = entry["player"], entry["stat"], entry["tricode"]
        if p.rank < 5: continue              # rank 0-4 = starting rotation
        if st.games_played < 50: continue
        if st.ppg < 9: continue              # real 6MOY range starts ~12, but lower OVR teams have lower bars
        # Bench-scorer score (rewards offense + team success)
        team_w = sim.standings[tri]["wins"]
        score = st.ppg * 1.2 + st.apg * 0.5 + st.rpg * 0.3 + (p.ovr - 70) * 0.35 + max(0, team_w - 40) * 0.15
        six_cands.append((score, p.name, tri))
    if six_cands:
        six_cands.sort(key=lambda x: -x[0])
        choice = six_cands[0]
        sim.six_man = choice[1]
        sim.six_man_team = choice[2]

    # ---- MIP: biggest YoY OVR jump (requires last season to exist) ----
    prev_season_str = f"{int(season.split('-')[0]) - 1}-{int(season.split('-')[1]) - 1:02d}"
    prev_stats_rows = db.query(PlayerSeasonStats).filter(PlayerSeasonStats.season == prev_season_str).all()
    prev_stats_by_pid = {r.player_id: r for r in prev_stats_rows}
    mip_cands = []
    for entry in pool:
        p, st, tri = entry["player"], entry["stat"], entry["tricode"]
        prev_st = prev_stats_by_pid.get(p.pid)
        if not prev_st: continue
        if prev_st.games_played < 30 or st.games_played < 50: continue
        if prev_st.ppg < 5: continue       # need to have been playing some
        ppg_jump = st.ppg - prev_st.ppg
        if ppg_jump < 4: continue
        # Score: PPG jump + OVR bracket (most MIPs are 21-26 years old)
        age_b = 1.2 if 21 <= p.age <= 26 else 1.0
        score = ppg_jump * age_b + (st.apg - prev_st.apg) * 0.5 + (st.rpg - prev_st.rpg) * 0.4
        mip_cands.append((score, p.name, tri))
    if mip_cands:
        mip_cands.sort(key=lambda x: -x[0])
        choice = mip_cands[0]
        sim.mip = choice[1]
        sim.mip_team = choice[2]

    # ---- All-NBA / All-Stars / All-Defensive / All-Rookie ----
    # Universal "value" score for All-NBA + All-Star pools
    value_scored: list[dict] = []
    for entry in pool:
        p, st, tri = entry["player"], entry["stat"], entry["tricode"]
        if st.games_played < 50: continue
        team_seed_bonus = 1.10 if entry["net_rtg"] > 3 else (1.05 if entry["net_rtg"] > 0 else 1.0)
        ovr_factor = max(0.0, (p.ovr - 70) / 22) ** 1.2
        score = (st.ppg + st.rpg * 0.45 + st.apg * 0.75 + st.spg * 1.1 + st.bpg * 1.1) * ovr_factor * team_seed_bonus
        value_scored.append({
            "name": p.name, "team": tri, "position": p.pos, "ovr": p.ovr,
            "conference": entry["conference"],
            "ppg": st.ppg, "rpg": st.rpg, "apg": st.apg,
            "spg": st.spg, "bpg": st.bpg,
            "score": round(score, 1),
        })
    value_scored.sort(key=lambda x: -x["score"])

    def select_all_team(pool: list[dict]) -> tuple[list[dict], list[dict]]:
        guards, forwards, centers = [], [], []
        for p in pool:
            b = _player_pos_bucket(p["position"])
            if b == "G": guards.append(p)
            elif b == "F": forwards.append(p)
            else: centers.append(p)
        picks: list[dict] = []
        picks += guards[:2]
        picks += forwards[:2]
        picks += centers[:1]
        chosen = {p["name"] for p in picks}
        remainder = [p for p in pool if p["name"] not in chosen]
        return picks, remainder

    pool_copy = value_scored[:]
    f1, pool_copy = select_all_team(pool_copy)
    f2, pool_copy = select_all_team(pool_copy)
    f3, _ = select_all_team(pool_copy)
    sim.all_nba_first = f1
    sim.all_nba_second = f2
    sim.all_nba_third = f3
    sim.all_stars_east = [p for p in value_scored if p["conference"] == "East"][:12]
    sim.all_stars_west = [p for p in value_scored if p["conference"] == "West"][:12]

    # All-Defensive: rank by defensive score
    def_scored: list[dict] = []
    for entry in pool:
        p, st, tri = entry["player"], entry["stat"], entry["tricode"]
        if st.games_played < 50: continue
        pos_b = {"C": 1.35, "PF": 1.12, "SF": 1.0, "SG": 0.92, "PG": 0.9}.get(p.pos, 1.0)
        team_def_bonus = 1.0 + max(0, (115 - entry["team_d_rtg"]) * 0.04)
        score = (st.spg * 2.5 + st.bpg * 3.5 + st.rpg * 0.3) * pos_b * team_def_bonus + (p.ovr - 75) * 0.1
        def_scored.append({
            "name": p.name, "team": tri, "position": p.pos, "ovr": p.ovr,
            "spg": st.spg, "bpg": st.bpg, "score": round(score, 1),
            "conference": entry["conference"],
        })
    def_scored.sort(key=lambda x: -x["score"])
    d_pool = def_scored[:]
    sim.all_defensive_first, d_pool = select_all_team(d_pool)
    sim.all_defensive_second, _ = select_all_team(d_pool)

    # All-Rookie: top 10 rookies, 2 teams of 5 by stat composite
    rookie_pool = []
    for entry in roy_cands:
        score, name, tricode, pid, st = entry
        # find the profile player
        p_obj = None
        for tri, prof in profiles.items():
            if tri != tricode: continue
            for pl in prof.players:
                if pl.pid == pid:
                    p_obj = pl; break
            if p_obj: break
        pos = p_obj.pos if p_obj else "F"
        rookie_pool.append({
            "name": name, "team": tricode, "position": pos,
            "ppg": st.ppg, "rpg": st.rpg, "apg": st.apg,
            "score": round(score, 1),
        })
    sim.all_rookie_first = rookie_pool[:5]
    sim.all_rookie_second = rookie_pool[5:10]


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------


def persist_results(db: Session, sim: SimResult) -> None:
    season_row = db.get(Season, sim.season)
    if not season_row:
        season_row = Season(season=sim.season)
        db.add(season_row)
    season_row.simulated = True
    season_row.champion_tricode = sim.champion
    season_row.mvp_name = sim.mvp
    season_row.mvp_team = sim.mvp_team
    season_row.finals_mvp_name = sim.finals_mvp
    season_row.finals_mvp_team = sim.champion
    season_row.dpoy_name = sim.dpoy
    season_row.dpoy_team = sim.dpoy_team
    season_row.roy_name = sim.roy
    season_row.roy_team = sim.roy_team
    season_row.all_nba_json = {
        "first": sim.all_nba_first,
        "second": sim.all_nba_second,
        "third": sim.all_nba_third,
        "all_defensive_first": sim.all_defensive_first,
        "all_defensive_second": sim.all_defensive_second,
        "all_rookie_first": sim.all_rookie_first,
        "all_rookie_second": sim.all_rookie_second,
        "six_man": sim.six_man,
        "six_man_team": sim.six_man_team,
        "mip": sim.mip,
        "mip_team": sim.mip_team,
    }

    for tricode, s in sim.standings.items():
        seeds = sim.east_seeds if s["conference"] == "East" else sim.west_seeds
        seed = seeds.index(tricode) + 1 if tricode in seeds else None
        db.add(TeamRecord(
            season=sim.season, team_tricode=tricode,
            wins=s["wins"], losses=s["losses"], seed=seed,
            made_playoffs=(seed is not None and seed <= 8),
            playoff_exit_round=sim.playoff_results.get(tricode),
        ))
    db.commit()


# ---------------------------------------------------------------------------
# Draft order assignment (NBA lottery, weighted by inverse record)
# ---------------------------------------------------------------------------


PLAYOFF_EXIT_RANK = {None: 0, "R1": 1, "R2": 2, "CONF_FINALS": 3, "FINALS": 4, "CHAMPION": 5}


def assign_next_draft_order(db: Session, sim: SimResult, draft_year: int) -> None:
    standings_list = [
        {"tricode": t, **s, "playoff_exit": sim.playoff_results.get(t)}
        for t, s in sim.standings.items()
    ]
    non_playoff = sorted(
        [s for s in standings_list if not (
            s["tricode"] in sim.east_seeds[:8] or s["tricode"] in sim.west_seeds[:8]
        )],
        key=lambda s: (s["wins"], -s["net_rtg"]),
    )
    playoff = [s for s in standings_list if s not in non_playoff]
    pool = [s["tricode"] for s in non_playoff]
    weights = [max(1.0, 50 - i * 3.0) for i in range(len(pool))]
    top4: list[str] = []
    remaining_pool = pool[:]
    remaining_w = weights[:]
    for _ in range(min(4, len(remaining_pool))):
        idx = random.choices(range(len(remaining_pool)), weights=remaining_w, k=1)[0]
        top4.append(remaining_pool.pop(idx))
        remaining_w.pop(idx)
    rest_lottery = [t for t in pool if t not in top4]
    lottery_order = top4 + rest_lottery
    playoff_sorted = sorted(
        playoff,
        key=lambda s: (PLAYOFF_EXIT_RANK.get(s["playoff_exit"]), -s["wins"]),
    )
    playoff_order = [s["tricode"] for s in playoff_sorted]
    fr_order = lottery_order + playoff_order

    def _apply_round(round_: int, base_pick: int):
        for i, original in enumerate(fr_order, start=base_pick):
            pick = db.query(DraftPick).filter(
                DraftPick.season_year == draft_year,
                DraftPick.round == round_,
                DraftPick.original_team_tricode == original,
                DraftPick.is_swap == False,
            ).first()
            if pick:
                pick.pick_number = i
                pick.status = PickStatus.OWNED

    _apply_round(1, 1)
    _apply_round(2, 31)
    db.commit()


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


def simulate_season(db: Session, season: str = "2026-27") -> SimResult:
    sim, profiles = simulate_regular_season(db, season)
    _generate_player_season_stats(db, sim, profiles, season)
    simulate_playoffs(db, sim, profiles, season)
    select_awards(db, sim, profiles, season)
    persist_results(db, sim)
    next_draft_year = int(season.split("-")[0]) + 1
    assign_next_draft_order(db, sim, next_draft_year)
    return sim
