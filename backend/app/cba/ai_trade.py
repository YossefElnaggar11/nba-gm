"""AI trade evaluation — data-driven, based on real NBA trade patterns.

Conceptual model
================
A trade is acceptable to Team T if **the value of what T receives, weighted
through T's specific lens (team window, positional needs, cap situation,
age curve), is at least as high as what T gives up**, with a context-aware
threshold.

This mirrors how real NBA front offices actually think:

  - **Rebuilders** love picks + young players + contracts that turn into cap
    space; they hate paying age-30+ vets to win 40 games. They'll accept
    deals where they take on bad money if a 1st-rounder comes attached
    (real example: 2020-25 OKC/Detroit/Washington pick-stockpiling trades).
  - **Contenders** want established veterans on cost-controlled deals to
    fill specific positional needs; they discount picks because they're
    drafting at the back of the round and don't need projects. They'll
    happily ship picks for a difference-maker (real examples: 2024 Mavs
    for PJ Washington, 2024 Pacers for Pascal Siakam).
  - **Cap relief** matters massively to teams in the apron range — saving
    $5M-$10M is genuinely worth a 2nd-round pick on its own.
  - **Positional fit** can swing a trade: a 4th PG is worth less than a
    starting C even at equal OVR.

Module structure
================
1. `get_team_context(db, tricode, season)` — derives team's competitive
   window (CONTENDER/PLAYOFF/MID/REBUILD), positional surplus map, payroll
   status, and aging trajectory.
2. `value_player_for(player, ctx, season)` — values a player to a SPECIFIC
   receiving team: base value × age fit × position fit + contract surplus.
3. `value_pick_for(pick, ctx, current_year)` — values a pick: slot value ×
   future discount × window multiplier × protection penalty.
4. `evaluate_for_team(db, proposal, team)` — sums incoming/outgoing, applies
   cap relief / cap drag, compares against context-aware threshold.

The function preserves the same `TradeEvaluation` shape used by the API and
frontend so callers don't change.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from sqlalchemy.orm import Session

from app.cba.constants import CAP_HISTORY
from app.cba.market_value import expected_market_value
from app.cba.rules import (
    TradeProposal, _player_salary_in_season, compute_team_finances,
)
from app.db.schema import Contract, ContractSeason, DraftPick, Player, TeamRecord


# ---------------------------------------------------------------------------
# Pick-value chart (standard NBA trade-value style)
# ---------------------------------------------------------------------------

# Slot values calibrated against publicly-known NBA trade charts.
# These are SHARES of pick value; we multiply by 100 elsewhere to normalize.
PICK_VALUE_BY_SLOT: dict[int, float] = {
    1: 3000.0, 2: 2200.0, 3: 1800.0, 4: 1500.0, 5: 1300.0,
    6: 1150.0, 7: 1020.0, 8: 920.0, 9: 830.0, 10: 760.0,
    11: 700.0, 12: 650.0, 13: 610.0, 14: 570.0, 15: 540.0,
    16: 500.0, 17: 470.0, 18: 440.0, 19: 415.0, 20: 390.0,
    21: 370.0, 22: 350.0, 23: 330.0, 24: 315.0, 25: 300.0,
    26: 285.0, 27: 270.0, 28: 260.0, 29: 250.0, 30: 240.0,
}
SECOND_ROUND_VALUE = 80.0
FUTURE_PICK_DISCOUNT_PER_YEAR = 0.85          # 2027 pick worth 85% of equivalent 2026 slot
UNPROTECTED_FUTURE_AVG_SLOT_VALUE = 540.0     # ~#15 slot average
SWAP_VALUE = 220.0                            # swap rights ≈ deep 1st-rounder


# ---------------------------------------------------------------------------
# Team context
# ---------------------------------------------------------------------------


Window = Literal["CONTENDER", "PLAYOFF", "MID", "REBUILD"]


@dataclass
class TeamContext:
    tricode: str
    season: str
    window: Window
    avg_top8_age: float
    is_taxpayer: bool
    is_above_first_apron: bool
    is_above_second_apron: bool
    cap_space: int
    pos_counts: dict[str, int]                 # how many top-12 players at each pos
    has_max_star: bool                         # any player with OVR >= 90
    has_blue_chip_young: bool                  # any OVR >= 85 with age <= 23


def _team_top_players(db: Session, tricode: str, season: str, limit: int = 12) -> list[Player]:
    rows = (
        db.query(Player)
        .join(Contract, Contract.player_id == Player.id)
        .join(ContractSeason, ContractSeason.contract_id == Contract.id)
        .filter(
            Contract.team_tricode == tricode,
            Contract.is_active == True,
            ContractSeason.season == season,
        )
        .all()
    )
    rows.sort(key=lambda p: -(p.overall or 0))
    return rows[:limit]


def get_team_context(db: Session, tricode: str, season: str) -> TeamContext:
    top = _team_top_players(db, tricode, season, limit=12)
    fin = compute_team_finances(db, tricode, season)

    # Derive competitive window from last simmed season's record (if available),
    # otherwise from current roster talent.
    prev_season = _previous_season(season)
    rec = db.query(TeamRecord).filter(
        TeamRecord.season == prev_season,
        TeamRecord.team_tricode == tricode,
    ).first()
    if rec:
        if rec.wins >= 53: window: Window = "CONTENDER"
        elif rec.wins >= 44: window = "PLAYOFF"
        elif rec.wins >= 33: window = "MID"
        else: window = "REBUILD"
    else:
        # Fall back to top-8 talent + age
        top8 = top[:8]
        if not top8:
            window = "REBUILD"
        else:
            avg_top8 = sum(p.overall or 60 for p in top8) / len(top8)
            if avg_top8 >= 84: window = "CONTENDER"
            elif avg_top8 >= 80: window = "PLAYOFF"
            elif avg_top8 >= 76: window = "MID"
            else: window = "REBUILD"

    pos_counts: dict[str, int] = {"PG": 0, "SG": 0, "SF": 0, "PF": 0, "C": 0}
    for p in top:
        if p.position in pos_counts:
            pos_counts[p.position] += 1

    ages = [p.age for p in top[:8] if p.age]
    avg_age = sum(ages) / len(ages) if ages else 27.0

    return TeamContext(
        tricode=tricode,
        season=season,
        window=window,
        avg_top8_age=avg_age,
        is_taxpayer=fin.is_taxpayer,
        is_above_first_apron=fin.is_above_first_apron,
        is_above_second_apron=fin.is_above_second_apron,
        cap_space=fin.cap_space,
        pos_counts=pos_counts,
        has_max_star=any((p.overall or 0) >= 90 for p in top),
        has_blue_chip_young=any((p.overall or 0) >= 85 and (p.age or 30) <= 23 for p in top),
    )


def _previous_season(season: str) -> str:
    start = int(season.split("-")[0])
    return f"{start - 1}-{str(start % 100).zfill(2)}"


# ---------------------------------------------------------------------------
# Player valuation (asset value to a SPECIFIC receiving team)
# ---------------------------------------------------------------------------


def _base_player_value(ovr: int, potential: int, age: int) -> float:
    """OVR-driven base value, scaled so an 85-OVR prime player ≈ 1000 units
    (roughly equivalent to a top-5 draft pick on the chart above)."""
    if ovr < 60:
        return 0.0
    # Cubic shape — stars far more valuable than the diff in OVR points suggests
    # 60 → ~0, 75 → ~225, 85 → ~1000, 92 → ~2400, 96 → ~3500
    base = ((ovr - 60) ** 2.6) * 0.7
    # Potential bump (only counts for young players who haven't peaked)
    if age <= 24 and potential > ovr:
        base += (potential - ovr) ** 1.8 * 12
    return base


def _age_fit_multiplier(age: int, window: Window) -> float:
    """How well a player's age fits the team's window."""
    if window == "REBUILD":
        if age <= 22: return 1.30
        if age <= 24: return 1.18
        if age <= 26: return 1.05
        if age <= 29: return 0.85
        if age <= 31: return 0.60
        return 0.30
    if window == "MID":
        if age <= 24: return 1.15
        if age <= 28: return 1.08
        if age <= 31: return 0.95
        return 0.75
    if window == "PLAYOFF":
        if age <= 22: return 0.95
        if age <= 28: return 1.10
        if age <= 31: return 1.00
        return 0.78
    # CONTENDER — wants productive vets right now
    if age <= 21: return 0.80
    if age <= 24: return 1.00
    if age <= 31: return 1.18
    if age <= 33: return 1.05
    return 0.75


def _pos_fit_multiplier(pos: str | None, ctx: TeamContext) -> float:
    """Surplus at a position discounts incoming value; deficit boosts it."""
    if pos not in ctx.pos_counts:
        return 1.0
    # Typical top-12 distribution: 2.5 PG, 2.5 SG, 2 SF, 2.5 PF, 2.5 C
    target = {"PG": 2.5, "SG": 2.5, "SF": 2.0, "PF": 2.5, "C": 2.5}[pos]
    current = ctx.pos_counts[pos]
    delta = current - target
    if delta <= -1.5: return 1.25      # major hole
    if delta <= -0.5: return 1.12      # mild deficit
    if delta >= 2.0: return 0.80       # logjam
    if delta >= 1.0: return 0.90       # surplus
    return 1.0


def _contract_surplus_units(player: Player, season: str, salary: int) -> float:
    """How below-market the contract is, in value units. $1M surplus ≈ 8 units."""
    if not player.overall:
        return 0.0
    market = expected_market_value(player.overall, player.age, season, player.position)
    surplus = market - salary
    return surplus / 1_000_000 * 8.0


def value_player_for(
    db: Session, player: Player, ctx: TeamContext, season: str, salary: int | None = None,
) -> float:
    if not player:
        return 0.0
    ovr = player.overall or 60
    pot = player.potential or ovr
    age = player.age or 27
    base = _base_player_value(ovr, pot, age)
    age_mult = _age_fit_multiplier(age, ctx.window)
    pos_mult = _pos_fit_multiplier(player.position, ctx)
    sal = salary if salary is not None else _player_salary_in_season(db, player.id, season)
    contract_units = _contract_surplus_units(player, season, sal)
    return base * age_mult * pos_mult + contract_units


# ---------------------------------------------------------------------------
# Pick valuation
# ---------------------------------------------------------------------------


def _window_pick_multiplier(window: Window) -> float:
    """Contenders discount picks; rebuilders premium them."""
    return {
        "CONTENDER": 0.70,
        "PLAYOFF": 0.90,
        "MID": 1.10,
        "REBUILD": 1.40,
    }[window]


def _protection_penalty(text: str | None) -> float:
    if not text:
        return 1.0
    t = text.lower()
    if "unprotected" in t:
        return 1.0
    if "top-4" in t or "top 4" in t:
        return 0.60
    if "lottery" in t or "top-14" in t or "top 14" in t:
        return 0.45
    if "top-" in t or "top " in t:
        return 0.72
    return 0.85


def value_pick_for(pk: DraftPick, ctx: TeamContext, current_year: int) -> float:
    if pk.is_swap:
        v = SWAP_VALUE
    elif pk.round == 2:
        v = SECOND_ROUND_VALUE
    elif pk.season_year == current_year and pk.pick_number:
        v = PICK_VALUE_BY_SLOT.get(pk.pick_number, 220.0)
    else:
        v = UNPROTECTED_FUTURE_AVG_SLOT_VALUE
    years_out = max(0, pk.season_year - current_year)
    v *= FUTURE_PICK_DISCOUNT_PER_YEAR ** years_out
    v *= _protection_penalty(pk.protection_text)
    v *= _window_pick_multiplier(ctx.window)
    return v


# ---------------------------------------------------------------------------
# Cap impact (saving money for taxpayers, taking on bad money for under-cap)
# ---------------------------------------------------------------------------


def _cap_impact_units(ctx: TeamContext, net_salary_in: int) -> float:
    """How much (positive or negative) the salary delta is worth to this team.

    Real NBA dynamics:
      - Above 2nd apron: saving $1M ≈ ~2x dollar value because of repeater tax + draft penalties
      - Above 1st apron: $1M ≈ ~1.5x
      - Above tax: $1M ≈ ~1x
      - Under cap with space: TAKING ON $1M of dead money costs ~0.4 units/$ M
      - Otherwise: small effect
    """
    if net_salary_in == 0:
        return 0.0
    delta_m = net_salary_in / 1_000_000
    if ctx.is_above_second_apron:
        # Saving money is gold; adding is brutal
        return -delta_m * 6.0       # +5M saved → +30 units; +5M added → -30
    if ctx.is_above_first_apron:
        return -delta_m * 4.0
    if ctx.is_taxpayer:
        return -delta_m * 2.5
    if not ctx.is_above_first_apron and ctx.cap_space > 5_000_000 and net_salary_in > 0:
        # Under cap teams: taking on dead salary is a small cost
        return -delta_m * 1.2
    return -delta_m * 0.4           # mild aversion to adding salary as default


# ---------------------------------------------------------------------------
# Acceptance threshold (context-aware)
# ---------------------------------------------------------------------------


def _threshold(ctx: TeamContext, has_picks_outgoing: bool) -> float:
    """How much incoming value (as fraction of outgoing) does the team require?

    Rebuilders that aren't sending picks are fairly lenient — they're stockpiling.
    Contenders are strict because every deal is "the move".
    """
    base = {
        "CONTENDER": 0.95,
        "PLAYOFF": 0.90,
        "MID": 0.88,
        "REBUILD": 0.82,
    }[ctx.window]
    # If team is sending out a pick, they want to *win* the trade
    if has_picks_outgoing and ctx.window == "REBUILD":
        base += 0.10                # rebuilder hates losing picks
    elif has_picks_outgoing:
        base += 0.05
    return base


# ---------------------------------------------------------------------------
# Public API: TradeEvaluation
# ---------------------------------------------------------------------------


@dataclass
class TradeEvaluation:
    accepts: bool
    incoming_value: float
    outgoing_value: float
    threshold: float
    has_picks: bool
    explanation: str


def evaluate_for_team(db: Session, proposal: TradeProposal, team: str) -> TradeEvaluation:
    own_leg = next(l for l in proposal.legs if l.team == team)
    other_legs = [l for l in proposal.legs if l.team != team]
    ctx = get_team_context(db, team, proposal.season)
    current_year = int(proposal.season.split("-")[0])

    # Outgoing value
    out_player_val = 0.0
    out_pick_val = 0.0
    out_salary = 0
    out_pick_count = 0
    out_player_names: list[str] = []
    for pid in own_leg.outgoing_player_ids:
        p = db.get(Player, pid)
        if not p:
            continue
        sal = _player_salary_in_season(db, pid, proposal.season)
        out_salary += sal
        out_player_val += value_player_for(db, p, ctx, proposal.season, salary=sal)
        out_player_names.append(p.name)
    for pkid in own_leg.outgoing_pick_ids:
        pk = db.get(DraftPick, pkid)
        if not pk:
            continue
        out_pick_val += value_pick_for(pk, ctx, current_year)
        out_pick_count += 1

    # Incoming value (assets routed TO this team)
    in_player_val = 0.0
    in_pick_val = 0.0
    in_salary = 0
    in_pick_count = 0
    in_player_names: list[str] = []
    for leg in other_legs:
        for pid in leg.outgoing_player_ids:
            try:
                dest = proposal.destination("player", pid, leg.team)
            except ValueError:
                continue
            if dest != team:
                continue
            p = db.get(Player, pid)
            if not p:
                continue
            sal = _player_salary_in_season(db, pid, proposal.season)
            in_salary += sal
            in_player_val += value_player_for(db, p, ctx, proposal.season, salary=sal)
            in_player_names.append(p.name)
        for pkid in leg.outgoing_pick_ids:
            try:
                dest = proposal.destination("pick", pkid, leg.team)
            except ValueError:
                continue
            if dest != team:
                continue
            pk = db.get(DraftPick, pkid)
            if not pk:
                continue
            in_pick_val += value_pick_for(pk, ctx, current_year)
            in_pick_count += 1

    net_salary_in = in_salary - out_salary
    cap_units = _cap_impact_units(ctx, net_salary_in)

    incoming_total = in_player_val + in_pick_val + cap_units
    outgoing_total = out_player_val + out_pick_val
    has_picks = out_pick_count > 0 or in_pick_count > 0
    threshold = _threshold(ctx, has_picks_outgoing=out_pick_count > 0)
    required = outgoing_total * threshold
    accepts = incoming_total >= required

    diff_pct = ((incoming_total - outgoing_total) / max(outgoing_total, 1)) * 100
    cap_summary = ""
    if abs(cap_units) >= 3:
        cap_summary = f" Cap: {cap_units:+.0f} units ({'saves' if net_salary_in < 0 else 'adds'} ${abs(net_salary_in):,}/yr)."

    in_names_str = ", ".join(in_player_names) or "no players"
    out_names_str = ", ".join(out_player_names) or "no players"
    window_desc = ctx.window.lower()

    if accepts:
        explanation = (
            f"{team} ({window_desc}) accepts. "
            f"Incoming {incoming_total:.0f} ({in_names_str}) vs outgoing {outgoing_total:.0f} "
            f"({out_names_str}); {diff_pct:+.0f}% relative.{cap_summary}"
        )
    else:
        deficit_pct = (required - incoming_total) / max(outgoing_total, 1) * 100
        why_strict = " (picks involved — stricter threshold)" if out_pick_count > 0 else ""
        explanation = (
            f"{team} ({window_desc}) rejects. "
            f"Incoming {incoming_total:.0f} vs required {required:.0f} "
            f"(short by {deficit_pct:.0f}% of outgoing){why_strict}.{cap_summary}"
        )

    return TradeEvaluation(
        accepts=accepts,
        incoming_value=incoming_total,
        outgoing_value=outgoing_total,
        threshold=threshold,
        has_picks=has_picks,
        explanation=explanation,
    )


# Re-exports for backwards compat (old callers may have imported these)
def player_value(db: Session, player: Player, season: str = "2026-27") -> float:
    """Legacy single-team-agnostic value used by some callers."""
    if not player:
        return 0.0
    ovr = player.overall or 60
    pot = player.potential or ovr
    age = player.age or 27
    return _base_player_value(ovr, pot, age)
