"""Season simulation engine v3.

Calibrated against 5 seasons of real NBA standings (2020-25):
  Historical: mean=41, std=11.8, max=68, 60+ wins=3.3%, 70+ wins=0%, under 25=15.3%
  Target distribution: same shape, no 70-win-team epidemics.

Approach:
  - Each team's effective rating = weighted top-8 (with injury discounts)
  - League average rating computed DYNAMICALLY
  - Logistic curve maps rating delta -> win pct, SOFT-BOUNDED to [0.18, 0.71]
    so theoretical max ~58 wins; lucky variance can push to ~70 rare.
  - Schedule strength: top teams lose 1-2 expected wins (play more contenders)
  - Per-player season stats generated using BBR baselines + variance
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.data.teams import TEAMS
from app.db.schema import (
    Contract, ContractSeason, DraftPick, PickStatus, Player, PlayerSeasonStats,
    Prospect, Season, TeamRecord,
)


# ---------------------------------------------------------------------------
# Rating derivation
# ---------------------------------------------------------------------------


def estimate_rating(salary: int, explicit: int | None = None) -> int:
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


def team_strength(db: Session, tricode: str, season: str = "2026-27") -> tuple[float, list[tuple[str, int]]]:
    rows = _player_rows(db, tricode, season)
    if not rows:
        return 45.0, []
    rated = [(r[1], estimate_rating(r[0], r[2])) for r in rows]
    rated.sort(key=lambda x: -x[1])
    top8 = rated[:8]
    weights = [2.5, 2.2, 1.6, 1.3, 1.0, 0.9, 0.8, 0.7][:len(top8)]
    weighted_sum = sum(r * w for (_, r), w in zip(top8, weights))
    avg = weighted_sum / sum(weights)
    bench_penalty = max(0, 10 - len(rated)) * 1.5
    return avg - bench_penalty, top8


# Well-known reputational modifiers — captures coaching, continuity, system
# Applied as a small +/- to effective rating. Reset each rollover (or auto-decay).
COACHING_BONUS: dict[str, float] = {
    "BOS": 1.5, "DEN": 1.2, "MIA": 1.2, "OKC": 1.0, "IND": 0.7,
    "CLE": 0.7, "MIN": 0.5, "DAL": 0.4, "MIL": 0.3, "ORL": 0.3,
    "NYK": 0.4, "GSW": 0.3,
    "POR": -0.4, "WAS": -0.6, "CHA": -0.6, "BKN": -0.3, "UTA": -0.3,
    "TOR": -0.2, "SAS": -0.2,
}


def team_effective_rating(db: Session, tricode: str, season: str, injuries: dict[int, int]) -> float:
    rows = _player_rows(db, tricode, season)
    if not rows:
        return 45.0
    rated: list[tuple[int, int, int, str | None]] = []
    for r in rows:
        salary, _name, overall, pid = r[0], r[1], r[2], r[3]
        pos = r[4]
        rating = estimate_rating(salary, overall)
        missed = injuries.get(pid, 0)
        rated.append((rating, missed, pid, pos))
    rated.sort(key=lambda x: -x[0])
    top8 = rated[:8]
    # Star-heavy weighting: top star matters disproportionately
    weights = [3.2, 2.3, 1.7, 1.4, 1.1, 0.95, 0.85, 0.75][:len(top8)]
    weighted_sum = 0.0
    weight_sum = 0.0
    for (rating, missed, _pid, _pos), w in zip(top8, weights):
        availability = max(0.4, (82 - missed) / 82)
        weighted_sum += rating * w * availability
        weight_sum += w
    avg = weighted_sum / weight_sum if weight_sum > 0 else 60

    # Position completeness — penalty if missing PG or C in top 8
    top8_positions = {p for (_, _, _, p) in top8 if p}
    if "PG" not in top8_positions and not (top8_positions & {"SG"}):
        avg -= 1.5
    if "C" not in top8_positions and "PF" not in top8_positions:
        avg -= 1.8
    elif "C" not in top8_positions:
        avg -= 0.6  # PF can flex but it's not ideal

    # Bench depth: count rotation players (top 10) — thin teams die in 82-game grind
    rotation = rated[:10]
    if len(rotation) < 10:
        avg -= (10 - len(rotation)) * 0.6
    # Solid 9-10 bench guys give a small bonus
    if len(rotation) >= 10:
        bench_quality = sum(r for (r, _, _, _) in rated[8:10]) / 2 if len(rated) >= 10 else 60
        if bench_quality > 67:
            avg += min(1.5, (bench_quality - 67) * 0.25)

    # Coaching / system modifier
    avg += COACHING_BONUS.get(tricode, 0.0)

    # Continuity / chemistry: bonus if top-3 players have been with the team multiple years
    # (uses bird_years_with_team which increments each rollover for players who stay)
    top3_pids = [r[2] for r in top8[:3] if r[2] is not None]
    if top3_pids:
        from app.db.schema import Player as _PMod
        from sqlalchemy import select as _sel
        continuity_score = 0
        for pid_ in top3_pids:
            p_obj = db.get(_PMod, pid_)
            if p_obj:
                continuity_score += min(p_obj.bird_years_with_team or 0, 5)
        # Up to +1.0 bonus for fully-continuous top 3 (15 total continuity-years)
        avg += min(1.0, continuity_score / 15)

    return avg


# ---------------------------------------------------------------------------
# Injury simulation
# ---------------------------------------------------------------------------


def simulate_injuries(db: Session, season: str) -> dict[int, int]:
    """Calibrated to NBA injury reality:
      - Roughly 30% of players miss 10+ games
      - 5-7% miss 40+ games
      - Stars miss less (durability bonus) but it costs more wins when they do
      - Older players miss more games
    """
    injuries: dict[int, int] = {}
    for team in TEAMS:
        rows = _player_rows(db, team.tricode, season)
        for r in rows:
            salary, _name, overall, pid = r[0], r[1], r[2], r[3]
            age = r[5] or 27
            ovr = overall or estimate_rating(salary)
            # Star durability: top guys play more durably (better treatment, more cautious management)
            if ovr >= 92: base = 0.16
            elif ovr >= 85: base = 0.20
            else: base = 0.25
            # Age scaling
            if age >= 35: base += 0.22
            elif age >= 32: base += 0.12
            elif age >= 29: base += 0.05
            if random.random() < base:
                # Missed games scales with severity randomness
                roll = random.random()
                if roll < 0.10:
                    missed = random.randint(40, 65)   # major injury
                elif roll < 0.30:
                    missed = random.randint(20, 40)   # moderate
                else:
                    missed = random.randint(5, 18)    # minor
                injuries[pid] = missed
            # Rare catastrophic season-ender (1.5%)
            if random.random() < 0.015:
                injuries[pid] = max(injuries.get(pid, 0), random.randint(55, 75))
    return injuries


# ---------------------------------------------------------------------------
# Regular season
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
    injuries: dict[int, int] = field(default_factory=dict)
    # 3 All-NBA teams of 5 (positional), 24 All-Stars (12 per conference)
    all_nba_first: list[dict] = field(default_factory=list)
    all_nba_second: list[dict] = field(default_factory=list)
    all_nba_third: list[dict] = field(default_factory=list)
    all_stars_east: list[dict] = field(default_factory=list)
    all_stars_west: list[dict] = field(default_factory=list)


# Calibrated to historical (2020-25): max 68w, mean 41, 60+ wins at 3.3%, 70+ at 0%
SCALE = 5.5           # slightly sharper rating sensitivity
WIN_PCT_FLOOR = 0.18  # bottom teams expected ~15 wins
WIN_PCT_CEILING = 0.78  # top teams expected ~64 wins (allows occasional 70+)
SEASON_NOISE = 7.0    # variance lets top teams hit 65-68 sometimes


def simulate_regular_season(db: Session, season: str = "2026-27") -> SimResult:
    result = SimResult(season=season)
    injuries = simulate_injuries(db, season)
    result.injuries = injuries
    ratings: dict[str, float] = {}
    for team in TEAMS:
        ratings[team.tricode] = team_effective_rating(db, team.tricode, season, injuries)

    league_avg = sum(ratings.values()) / len(ratings)

    # Detect injury cascades: teams that lost 2+ top-5 players for 30+ games
    cascade_penalty: dict[str, float] = {}
    for team in TEAMS:
        rows = _player_rows(db, team.tricode, season)
        if not rows:
            continue
        top5 = sorted(rows, key=lambda r: -(r[2] or 0))[:5]
        majors = sum(1 for r in top5 if injuries.get(r[3], 0) >= 30)
        if majors >= 2:
            cascade_penalty[team.tricode] = -3.0   # rotation chaos
        elif majors == 1:
            star_missed = next((injuries[r[3]] for r in top5 if injuries.get(r[3], 0) >= 30), 0)
            if star_missed >= 50:
                cascade_penalty[team.tricode] = -2.0

    for team in TEAMS:
        rating = ratings[team.tricode]
        delta = rating - league_avg
        raw = 1 / (1 + math.exp(-delta / SCALE))
        win_pct = WIN_PCT_FLOOR + (WIN_PCT_CEILING - WIN_PCT_FLOOR) * raw
        ew = win_pct * 82
        # Schedule strength: elite teams rest stars; very bad teams tank late
        if delta > 8:
            ew -= 1.0      # elite teams sit stars in back-to-backs
        if delta < -10:
            ew -= 1.5      # bad teams tank late in season for lottery
        ew += cascade_penalty.get(team.tricode, 0)
        # Hard cap at 73 wins (NBA all-time record by 2015-16 Warriors)
        wins = round(max(5, min(73, random.gauss(ew, SEASON_NOISE))))
        losses = 82 - wins
        result.standings[team.tricode] = {
            "wins": wins, "losses": losses,
            "conference": team.conference,
            "rating": round(rating, 1),
            "league_avg": round(league_avg, 1),
            "expected_wins": round(ew, 1),
        }

    for conf in ("East", "West"):
        teams = [t for t in TEAMS if t.conference == conf]
        teams_sorted = sorted(
            teams,
            key=lambda t: (-result.standings[t.tricode]["wins"], -result.standings[t.tricode]["rating"]),
        )
        seeds = [t.tricode for t in teams_sorted]
        if conf == "East":
            result.east_seeds = seeds
        else:
            result.west_seeds = seeds

    return result


# ---------------------------------------------------------------------------
# Playoffs
# ---------------------------------------------------------------------------


def _series_winner(db: Session, team_a: str, team_b: str, season: str, rating_a: float, rating_b: float) -> tuple[str, int, int]:
    p_a = 1 / (1 + math.exp(-(rating_a - rating_b) / 5.0))
    wins_a = wins_b = 0
    for _ in range(7):
        if random.random() < p_a:
            wins_a += 1
        else:
            wins_b += 1
        if wins_a == 4 or wins_b == 4:
            break
    return (team_a if wins_a > wins_b else team_b, wins_a, wins_b)


def simulate_playoffs(db: Session, sim: SimResult, season: str = "2026-27") -> SimResult:
    def bracket_round(seeds: list[str], pairs: list[tuple[int, int]]) -> list[str]:
        winners = []
        round_label = "R1" if len(pairs) == 4 else "R2" if len(pairs) == 2 else "CONF_FINALS"
        for a_idx, b_idx in pairs:
            a, b = seeds[a_idx], seeds[b_idx]
            ra = sim.standings[a]["rating"]
            rb = sim.standings[b]["rating"]
            w, _, _ = _series_winner(db, a, b, season, ra, rb)
            winners.append(w)
            loser = b if w == a else a
            sim.playoff_results.setdefault(loser, round_label)
        return winners

    east8, west8 = sim.east_seeds[:8], sim.west_seeds[:8]
    r1 = [(0, 7), (3, 4), (2, 5), (1, 6)]
    east_r2 = bracket_round(east8, r1)
    west_r2 = bracket_round(west8, r1)
    east_cf = bracket_round(east_r2, [(0, 1), (2, 3)])
    west_cf = bracket_round(west_r2, [(0, 1), (2, 3)])
    east_champ = bracket_round(east_cf, [(0, 1)])[0]
    west_champ = bracket_round(west_cf, [(0, 1)])[0]
    ra = sim.standings[east_champ]["rating"]
    rb = sim.standings[west_champ]["rating"]
    champ, _, _ = _series_winner(db, east_champ, west_champ, season, ra, rb)
    sim.champion = champ
    sim.playoff_results[east_champ] = "CHAMPION" if champ == east_champ else "FINALS"
    sim.playoff_results[west_champ] = "CHAMPION" if champ == west_champ else "FINALS"
    # Finals MVP: pick highest-rated rotation player on champion, with stat-based variance
    rows = _player_rows(db, champ, season)
    candidates = []
    for r in rows:
        pid, name = r[3], r[1]
        ovr = r[2] or estimate_rating(r[0])
        if ovr < 75:
            continue
        stats = db.query(PlayerSeasonStats).filter(
            PlayerSeasonStats.player_id == pid,
            PlayerSeasonStats.season == season,
        ).first()
        if stats and stats.games_played < 50:
            continue
        ppg_bonus = (stats.ppg if stats else 0) * 0.3
        score = ovr + ppg_bonus + random.uniform(-1.5, 1.5)
        candidates.append((score, name))
    if candidates:
        candidates.sort(key=lambda x: -x[0])
        sim.finals_mvp = candidates[0][1]
    return sim


# ---------------------------------------------------------------------------
# Per-player season stats generation
# ---------------------------------------------------------------------------


def _gen_player_stats(row, team_tricode: str, season: str, missed_games: int, role_rank: int) -> PlayerSeasonStats:
    """Generate a player's season stats from baselines + role + variance.

    role_rank: 0 = top option, 1 = 2nd, 2 = 3rd, etc.
    """
    salary, name, overall, pid = row[0], row[1], row[2], row[3]
    pos = row[4]
    age = row[5] or 27
    ppg = row[6] or 0.0
    rpg = row[7] or 0.0
    apg = row[8] or 0.0
    spg = row[9] or 0.0
    bpg = row[10] or 0.0
    mpg = row[11] or 0.0
    rating = overall or estimate_rating(salary)

    has_baseline = mpg > 0
    games_played = max(0, 82 - missed_games)
    started = games_played if role_rank < 5 else (games_played // 5 if role_rank < 8 else 0)

    if has_baseline:
        # Use BBR baseline with ±15% variance and slight age adjustment
        var = random.uniform(0.85, 1.15)
        age_mod = 1.0 if age <= 30 else (0.95 if age <= 33 else 0.88)
        ppg_out = ppg * var * age_mod
        rpg_out = rpg * var * age_mod
        apg_out = apg * var * age_mod
        spg_out = spg * var
        bpg_out = bpg * var
        mpg_out = mpg * (1.0 if role_rank < 5 else 0.85)
    else:
        # Rookie or newly acquired without baseline — generate from rating + role
        base_ppg = max(1.0, (rating - 50) * 0.55)
        if role_rank == 0: usage = 1.10
        elif role_rank < 3: usage = 0.95
        elif role_rank < 5: usage = 0.80
        elif role_rank < 8: usage = 0.55
        else: usage = 0.30
        ppg_out = base_ppg * usage * random.uniform(0.85, 1.15)
        rpg_out = max(1.0, (rating - 55) * 0.16 * (1.4 if pos in ("C", "PF") else 1.0))
        apg_out = max(0.5, (rating - 55) * 0.12 * (1.6 if pos in ("PG", "SG") else 0.8))
        spg_out = max(0.2, (rating - 55) * 0.025)
        bpg_out = max(0.1, (rating - 55) * 0.020 * (2.0 if pos in ("C", "PF") else 0.6))
        if role_rank == 0: mpg_out = 33
        elif role_rank < 3: mpg_out = 29
        elif role_rank < 5: mpg_out = 24
        elif role_rank < 8: mpg_out = 18
        else: mpg_out = 9

    # Shooting %s
    fg = max(0.35, min(0.60, random.gauss(0.46, 0.04)))
    three = max(0.20, min(0.50, random.gauss(0.36, 0.05)))
    ft = max(0.55, min(0.95, random.gauss(0.78, 0.06)))

    return PlayerSeasonStats(
        player_id=pid, season=season, team_tricode=team_tricode,
        games_played=games_played, games_started=started,
        mpg=round(mpg_out, 1),
        ppg=round(ppg_out, 1), rpg=round(rpg_out, 1), apg=round(apg_out, 1),
        spg=round(spg_out, 1), bpg=round(bpg_out, 1),
        fg_pct=round(fg, 3), three_pct=round(three, 3), ft_pct=round(ft, 3),
        is_injured=missed_games >= 20,
    )


def generate_player_season_stats(db: Session, sim: SimResult, season: str = "2026-27") -> int:
    """For every contracted player on every team, generate season stats."""
    db.query(PlayerSeasonStats).filter(PlayerSeasonStats.season == season).delete()
    db.flush()
    count = 0
    seen_players: set[int] = set()
    for team in TEAMS:
        rows = _player_rows(db, team.tricode, season)
        if not rows:
            continue
        # Dedupe within team (a player with multiple active contracts on same team)
        unique_rows = []
        for r in rows:
            if r[3] not in seen_players:
                unique_rows.append(r)
                seen_players.add(r[3])
        rated = sorted(range(len(unique_rows)),
                       key=lambda i: -(unique_rows[i][2] or estimate_rating(unique_rows[i][0])))
        for rank, idx in enumerate(rated):
            r = unique_rows[idx]
            pid = r[3]
            stats = _gen_player_stats(r, team.tricode, season, sim.injuries.get(pid, 0), rank)
            db.add(stats)
            count += 1
    db.commit()
    return count


# ---------------------------------------------------------------------------
# Awards (uses generated stats for more grounded picks)
# ---------------------------------------------------------------------------


def select_awards(db: Session, sim: SimResult, season: str = "2026-27") -> None:
    # MVP: stats × rating × team success. Grounding in OVR prevents low-rated
    # players from winning MVP just because their stats roll high one season.
    top_teams = sorted(sim.standings.keys(), key=lambda t: -sim.standings[t]["wins"])[:6]
    mvp_candidates = []
    for tricode in top_teams:
        rows = _player_rows(db, tricode, season)
        for r in rows:
            pid, name = r[3], r[1]
            ovr = r[2] or estimate_rating(r[0])
            if ovr < 78:
                continue   # MVPs are virtually always top-tier OVR
            stats = db.query(PlayerSeasonStats).filter(
                PlayerSeasonStats.player_id == pid,
                PlayerSeasonStats.season == season,
            ).first()
            if not stats or stats.games_played < 55:
                continue
            stat_score = (stats.ppg * 1.0 + stats.rpg * 0.5 + stats.apg * 0.8
                          + stats.spg * 1.0 + stats.bpg * 1.2)
            # Ground in OVR: a 90-OVR player getting 25 ppg matters more than a 75-OVR player getting 25 ppg
            rating_factor = (ovr / 82) ** 1.5
            seed_boost = 1.10 if tricode in top_teams[:3] else 1.0
            mvp_candidates.append((stat_score * rating_factor * seed_boost, name, tricode))
    if mvp_candidates:
        mvp_candidates.sort(key=lambda x: -x[0])
        top3 = mvp_candidates[:3]
        weights = [3.5, 1.5, 1.0][:len(top3)]
        choice = random.choices(top3, weights=weights, k=1)[0]
        sim.mvp = choice[1]
        sim.mvp_team = choice[2]

    # DPOY: defensive stats + position bonus, must be different from MVP
    dpoy_candidates = []
    for team in TEAMS:
        rows = _player_rows(db, team.tricode, season)
        for r in rows:
            pid, name, pos = r[3], r[1], r[4]
            if sim.mvp and name == sim.mvp:
                continue
            stats = db.query(PlayerSeasonStats).filter(
                PlayerSeasonStats.player_id == pid,
                PlayerSeasonStats.season == season,
            ).first()
            if not stats or stats.games_played < 55:
                continue
            pos_bonus = 1.30 if pos == "C" else (1.10 if pos == "PF" else 1.0)
            score = (stats.spg * 2.5 + stats.bpg * 3.0 + stats.rpg * 0.4) * pos_bonus
            dpoy_candidates.append((score, name, team.tricode))
    if dpoy_candidates:
        dpoy_candidates.sort(key=lambda x: -x[0])
        top3 = dpoy_candidates[:3]
        weights = [3.0, 1.5, 1.0][:len(top3)]
        choice = random.choices(top3, weights=weights, k=1)[0]
        sim.dpoy = choice[1]
        sim.dpoy_team = choice[2]

    # ROY: highest stats among drafted rookies
    draft_year = int(season.split("-")[0])
    rookies = (
        db.query(Player)
        .join(Prospect, Prospect.created_player_id == Player.id)
        .filter(Prospect.draft_year == draft_year)
        .all()
    )
    if rookies:
        scored = []
        for r in rookies:
            stats = db.query(PlayerSeasonStats).filter(
                PlayerSeasonStats.player_id == r.id,
                PlayerSeasonStats.season == season,
            ).one_or_none()
            if not stats:
                continue
            score = stats.ppg + stats.rpg * 0.5 + stats.apg * 0.8
            scored.append((score, r.name, r.team_tricode))
        if scored:
            scored.sort(key=lambda x: -x[0])
            sim.roy = scored[0][1]
            sim.roy_team = scored[0][2]

    # All-NBA teams (positional: 2G/2F/1C per team) + All-Stars (12 per conference)
    all_players_scored = []
    for team in TEAMS:
        rows = _player_rows(db, team.tricode, season)
        for r in rows:
            pid, name, pos = r[3], r[1], r[4]
            ovr = r[2] or estimate_rating(r[0])
            stats = db.query(PlayerSeasonStats).filter(
                PlayerSeasonStats.player_id == pid,
                PlayerSeasonStats.season == season,
            ).first()
            if not stats or stats.games_played < 50:
                continue
            score = (stats.ppg * 1.0 + stats.rpg * 0.4 + stats.apg * 0.7
                     + stats.spg * 1.0 + stats.bpg * 1.0) * (ovr / 80) ** 1.3
            all_players_scored.append({
                "name": name, "team": team.tricode, "position": pos or "F",
                "score": round(score, 1),
                "ppg": stats.ppg, "rpg": stats.rpg, "apg": stats.apg,
                "ovr": ovr, "conference": team.conference,
            })
    all_players_scored.sort(key=lambda x: -x["score"])

    # Positional selection for All-NBA teams
    def select_all_nba_team(pool: list[dict]) -> tuple[list[dict], list[dict]]:
        guards, forwards, centers = [], [], []
        for p in pool:
            pos = p["position"]
            if pos in ("PG", "SG", "G"):
                guards.append(p)
            elif pos in ("SF", "PF", "F"):
                forwards.append(p)
            elif pos == "C":
                centers.append(p)
        team_picks: list[dict] = []
        for g in guards[:2]: team_picks.append(g)
        for f in forwards[:2]: team_picks.append(f)
        for c in centers[:1]: team_picks.append(c)
        # Remove picked from pool, return rest
        chosen_ids = {p["name"] for p in team_picks}
        remainder = [p for p in pool if p["name"] not in chosen_ids]
        return team_picks, remainder

    pool = all_players_scored[:]
    first, pool = select_all_nba_team(pool)
    second, pool = select_all_nba_team(pool)
    third, _ = select_all_nba_team(pool)
    sim.all_nba_first = first
    sim.all_nba_second = second
    sim.all_nba_third = third
    sim.all_stars_east = [p for p in all_players_scored if p["conference"] == "East"][:12]
    sim.all_stars_west = [p for p in all_players_scored if p["conference"] == "West"][:12]


# ---------------------------------------------------------------------------
# Persist + next draft order
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
        key=lambda s: (s["wins"], -s["rating"]),
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


def simulate_season(db: Session, season: str = "2026-27") -> SimResult:
    sim = simulate_regular_season(db, season)
    simulate_playoffs(db, sim, season)
    generate_player_season_stats(db, sim, season)
    select_awards(db, sim, season)
    persist_results(db, sim)
    next_draft_year = int(season.split("-")[0]) + 1
    assign_next_draft_order(db, sim, next_draft_year)
    return sim
