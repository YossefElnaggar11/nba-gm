"""AI trade evaluation for Career mode.

Goal: AI accepts most legal player-for-player trades that are close to fair
value, but scrutinizes pick trades much more carefully (per user direction:
'the thunder should not be able to trade the #12 pick in the draft for the #1
pick').

Pick value chart roughly follows the standard NBA trade-value charts.
"""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.cba.rules import TradeProposal, _outgoing_salary
from app.db.schema import Contract, ContractSeason, DraftPick, Player


# Pick value by overall slot (approximated; smooth power-law decay)
PICK_VALUE_BY_SLOT_2026 = {
    1: 1000, 2: 770, 3: 620, 4: 510, 5: 430,
    6: 370, 7: 320, 8: 280, 9: 250, 10: 225,
    11: 200, 12: 180, 13: 165, 14: 150, 15: 140,
    16: 130, 17: 122, 18: 115, 19: 108, 20: 102,
    21: 96, 22: 91, 23: 87, 24: 83, 25: 79,
    26: 76, 27: 73, 28: 70, 29: 68, 30: 66,
}
SECOND_ROUND_VALUE = 20

FUTURE_PICK_DISCOUNT_PER_YEAR = 0.85   # 2027 pick worth 85% of equivalent slot in 2026
UNPROTECTED_FUTURE_AVG_SLOT_VALUE = 130  # average value of an unprotected future 1st (around #15-16)


def pick_value(pk: DraftPick, current_year: int = 2026) -> float:
    """Estimate trade value of a pick."""
    if pk.is_swap:
        return 25.0  # swap rights are valuable but not as much as the pick itself
    if pk.round == 2:
        v = SECOND_ROUND_VALUE
    elif pk.season_year == current_year and pk.pick_number:
        v = PICK_VALUE_BY_SLOT_2026.get(pk.pick_number, 50)
    else:
        # Future pick — without knowing where it'll land, use an avg
        v = UNPROTECTED_FUTURE_AVG_SLOT_VALUE
    # Future discount
    years_out = max(0, pk.season_year - current_year)
    v *= FUTURE_PICK_DISCOUNT_PER_YEAR ** years_out
    # Protection penalty
    if pk.protection_text:
        text = pk.protection_text.lower()
        if "unprotected" in text:
            pass
        elif "lottery" in text:
            v *= 0.55
        elif "top-" in text or "top " in text:
            v *= 0.70
        else:
            v *= 0.80
    return v


def player_value(db: Session, player: Player, season: str = "2026-27") -> float:
    """Estimate trade value of a player based on overall, potential, age, and contract."""
    ovr = player.overall or _derive_rating_from_salary(db, player.id, season)
    pot = player.potential or max(ovr, ovr + 5)
    age = player.age or 27
    # Base value scales with ovr ^ 3 (stars are exponentially more valuable)
    base = max(0, ((ovr - 60) ** 2) / 3)
    # Potential bump (younger upside)
    pot_bump = max(0, (pot - ovr) * 1.5)
    # Age curve
    if age < 22:
        age_factor = 1.15
    elif age <= 26:
        age_factor = 1.25
    elif age <= 29:
        age_factor = 1.0
    elif age <= 32:
        age_factor = 0.75
    else:
        age_factor = 0.5
    return (base + pot_bump) * age_factor


def _derive_rating_from_salary(db: Session, player_id: int, season: str) -> int:
    cs = (
        db.query(ContractSeason)
        .join(Contract, Contract.id == ContractSeason.contract_id)
        .filter(
            Contract.player_id == player_id, Contract.is_active == True,
            ContractSeason.season == season,
        )
        .one_or_none()
    )
    if not cs:
        return 60
    s = cs.salary
    if s >= 55_000_000: return 92
    if s >= 45_000_000: return 88
    if s >= 35_000_000: return 84
    if s >= 25_000_000: return 79
    if s >= 15_000_000: return 74
    if s >= 8_000_000:  return 69
    if s >= 4_000_000:  return 64
    return 58


@dataclass
class TradeEvaluation:
    accepts: bool
    incoming_value: float
    outgoing_value: float
    threshold: float
    has_picks: bool
    explanation: str


def evaluate_for_team(db: Session, proposal: TradeProposal, team: str) -> TradeEvaluation:
    """Decide if `team` would accept this trade. Routing-aware."""
    own_leg = next(l for l in proposal.legs if l.team == team)
    other_legs = [l for l in proposal.legs if l.team != team]

    # Outgoing value = what `team` gives up
    outgoing = 0.0
    out_has_picks = False
    for pid in own_leg.outgoing_player_ids:
        p = db.get(Player, pid)
        if p:
            outgoing += player_value(db, p, proposal.season)
    for pkid in own_leg.outgoing_pick_ids:
        pk = db.get(DraftPick, pkid)
        if pk:
            outgoing += pick_value(pk)
            out_has_picks = True

    # Incoming = assets routed TO `team` from other legs
    incoming = 0.0
    in_has_picks = False
    for leg in other_legs:
        for pid in leg.outgoing_player_ids:
            try:
                dest = proposal.destination("player", pid, leg.team)
            except ValueError:
                continue
            if dest != team:
                continue
            p = db.get(Player, pid)
            if p:
                incoming += player_value(db, p, proposal.season)
        for pkid in leg.outgoing_pick_ids:
            try:
                dest = proposal.destination("pick", pkid, leg.team)
            except ValueError:
                continue
            if dest != team:
                continue
            pk = db.get(DraftPick, pkid)
            if pk:
                incoming += pick_value(pk)
                in_has_picks = True

    has_picks = out_has_picks or in_has_picks
    # Stricter threshold when picks are involved
    threshold = 0.98 if has_picks else 0.85
    required = outgoing * threshold
    accepts = incoming >= required

    if accepts:
        diff = ((incoming - outgoing) / max(outgoing, 1)) * 100
        explanation = f"{team} accepts. Incoming value {incoming:.0f} vs outgoing {outgoing:.0f} ({diff:+.0f}%)."
    else:
        deficit = (required - incoming) / max(outgoing, 1) * 100
        why = "(picks involved — stricter threshold)" if has_picks else ""
        explanation = (
            f"{team} rejects. Incoming {incoming:.0f} < required {required:.0f} "
            f"(short by {deficit:.0f}% of outgoing). {why}".strip()
        )
    return TradeEvaluation(
        accepts=accepts, incoming_value=incoming, outgoing_value=outgoing,
        threshold=threshold, has_picks=has_picks, explanation=explanation,
    )
