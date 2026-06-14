"""CBA rules engine: validation logic for trades, signings, and roster moves.

This is the heart of the legality system. Every trade/signing must pass through
the validators here. We return a list of structured violations rather than
throwing — callers can show them in the UI or override (sandbox mode).

Reference: 2023 NBA CBA (effective 2023-07-01 through 2030-06-30).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Iterable

from sqlalchemy.orm import Session

from app.cba.constants import (
    CAP_HISTORY, EXCEPTIONS_2026_27,
    RAISE_PCT_BIRD, RAISE_PCT_NON_BIRD,
    MAX_LENGTH_BIRD, MAX_LENGTH_OUTSIDE,
    MAX_PCT_0_6_YRS, MAX_PCT_7_9_YRS, MAX_PCT_10_PLUS_YRS,
    TRADE_MATCH_BELOW_TAX, TRADE_MATCH_TAXPAYER,
    TRADE_MATCH_FIRST_APRON, TRADE_MATCH_SECOND_APRON,
    cap_for, min_salary,
)
from app.db.schema import CapHold, Contract, ContractSeason, DraftPick, OptionType, PickStatus, Player


# ---------------------------------------------------------------------------
# Violation types
# ---------------------------------------------------------------------------


class Severity(str, Enum):
    BLOCKER = "BLOCKER"   # cannot proceed
    WARNING = "WARNING"   # legal but risky


@dataclass
class Violation:
    code: str
    severity: Severity
    message: str
    team: str | None = None


# ---------------------------------------------------------------------------
# Team financial snapshot
# ---------------------------------------------------------------------------


@dataclass
class TeamFinances:
    tricode: str
    season: str
    total_salary: int
    cap: int
    luxury_tax: int
    first_apron: int
    second_apron: int

    @property
    def is_over_cap(self) -> bool:
        return self.total_salary > self.cap

    @property
    def is_taxpayer(self) -> bool:
        return self.total_salary > self.luxury_tax

    @property
    def is_above_first_apron(self) -> bool:
        return self.total_salary > self.first_apron

    @property
    def is_above_second_apron(self) -> bool:
        return self.total_salary > self.second_apron

    @property
    def cap_space(self) -> int:
        return max(0, self.cap - self.total_salary)


def compute_team_finances(db: Session, tricode: str, season: str) -> TeamFinances:
    """Sum all contract-seasons for the team for the given season."""
    rows = (
        db.query(ContractSeason.salary)
        .join(Contract, Contract.id == ContractSeason.contract_id)
        .filter(
            Contract.team_tricode == tricode,
            Contract.is_active == True,
            ContractSeason.season == season,
        )
        .all()
    )
    total = sum(r[0] for r in rows)
    cap = cap_for(season)
    return TeamFinances(
        tricode=tricode, season=season, total_salary=total,
        cap=cap.salary_cap, luxury_tax=cap.luxury_tax,
        first_apron=cap.first_apron, second_apron=cap.second_apron,
    )


# ---------------------------------------------------------------------------
# Trade representation (input to validator)
# ---------------------------------------------------------------------------


@dataclass
class TradeLeg:
    """One team's outgoing assets in a trade. The same trade has 2+ legs (one per team)."""
    team: str
    outgoing_player_ids: list[int] = field(default_factory=list)
    outgoing_pick_ids: list[int] = field(default_factory=list)
    outgoing_cash: int = 0
    outgoing_trade_exception_used: int = 0


@dataclass
class TradeProposal:
    legs: list[TradeLeg]
    season: str = "2026-27"
    # destinations: maps "player:<id>" or "pick:<id>" -> destination team tricode.
    # For 2-team trades, can be empty (assets default to the other team).
    # For 3+ team trades, MUST cover every outgoing asset.
    destinations: dict[str, str] = field(default_factory=dict)

    @property
    def teams(self) -> list[str]:
        return [leg.team for leg in self.legs]

    def destination(self, kind: str, asset_id: int, src_team: str) -> str:
        """Resolve where an asset goes. Defaults to the OTHER team in 2-team trade."""
        key = f"{kind}:{asset_id}"
        if key in self.destinations:
            return self.destinations[key]
        if len(self.legs) == 2:
            return next(l.team for l in self.legs if l.team != src_team)
        # 3+ team without explicit routing — invalid
        raise ValueError(f"3+ team trade requires explicit routing for {key}")


# ---------------------------------------------------------------------------
# Trade validation
# ---------------------------------------------------------------------------


def _player_salary_in_season(db: Session, player_id: int, season: str) -> int:
    cs = (
        db.query(ContractSeason)
        .join(Contract, Contract.id == ContractSeason.contract_id)
        .filter(
            Contract.player_id == player_id,
            Contract.is_active == True,
            ContractSeason.season == season,
        )
        .one_or_none()
    )
    return cs.salary if cs else 0


def _outgoing_salary(db: Session, leg: TradeLeg, season: str) -> int:
    return sum(_player_salary_in_season(db, pid, season) for pid in leg.outgoing_player_ids)


def _incoming_salary(db: Session, proposal: TradeProposal, recipient: str) -> int:
    """Sum of salary of players being routed TO `recipient` across all legs."""
    total = 0
    for leg in proposal.legs:
        if leg.team == recipient:
            continue
        for pid in leg.outgoing_player_ids:
            try:
                dest = proposal.destination("player", pid, leg.team)
            except ValueError:
                continue
            if dest == recipient:
                total += _player_salary_in_season(db, pid, proposal.season)
    return total


def _allowed_inbound(team_fin: TeamFinances, outgoing: int) -> int:
    """Maximum salary this team can take in given its apron position.

    2023 CBA tiers (most-restrictive last):
      below tax       : 200% + $250k
      tax to 1st apron: 125% + $100k
      1st to 2nd apron: 110% + $100k
      above 2nd apron : 100% (and no aggregation)
    """
    if team_fin.is_above_second_apron:
        rule = TRADE_MATCH_SECOND_APRON
    elif team_fin.is_above_first_apron:
        rule = TRADE_MATCH_FIRST_APRON
    elif team_fin.is_taxpayer:
        rule = TRADE_MATCH_TAXPAYER
    else:
        rule = TRADE_MATCH_BELOW_TAX
    return int(outgoing * rule.multiplier) + rule.plus_dollars


def validate_trade(db: Session, proposal: TradeProposal) -> list[Violation]:
    violations: list[Violation] = []

    if len(proposal.legs) < 2:
        violations.append(Violation("TRADE_TOO_FEW_TEAMS", Severity.BLOCKER,
                                    "Trade must involve at least 2 teams."))
        return violations

    # 0. Validate all referenced entities exist
    for leg in proposal.legs:
        for pid in leg.outgoing_player_ids:
            p = db.get(Player, pid)
            if not p:
                violations.append(Violation("PLAYER_NOT_FOUND", Severity.BLOCKER,
                                            f"Player id={pid} not found", team=leg.team))
                continue
            if p.team_tricode != leg.team:
                violations.append(Violation("PLAYER_NOT_ON_TEAM", Severity.BLOCKER,
                                            f"Player {p.name} is not on {leg.team}", team=leg.team))
        for pkid in leg.outgoing_pick_ids:
            pk = db.get(DraftPick, pkid)
            if not pk:
                violations.append(Violation("PICK_NOT_FOUND", Severity.BLOCKER,
                                            f"Pick id={pkid} not found", team=leg.team))
                continue
            if pk.owner_tricode != leg.team:
                violations.append(Violation("PICK_NOT_OWNED", Severity.BLOCKER,
                                            f"Pick {pk.season_year} R{pk.round} not owned by {leg.team}",
                                            team=leg.team))
    if any(v.severity == Severity.BLOCKER for v in violations):
        return violations

    # 1. Recently-signed restrictions
    # (3-month moratorium for newly signed players, etc. — TODO)

    # 2. Salary matching per team — explicit routing
    fins = {leg.team: compute_team_finances(db, leg.team, proposal.season) for leg in proposal.legs}
    for leg in proposal.legs:
        out = _outgoing_salary(db, leg, proposal.season)
        inc = _incoming_salary(db, proposal, leg.team)
        fin = fins[leg.team]
        # If under cap and can absorb without matching: cap space approach
        if fin.cap_space >= inc:
            continue  # cap space absorption — no matching needed

        # Otherwise, apply salary matching rule
        allowed = _allowed_inbound(fin, out)
        if inc > allowed:
            if fin.is_above_second_apron:
                apron_status = "above 2nd apron"
            elif fin.is_above_first_apron:
                apron_status = "1st-apron taxpayer"
            elif fin.is_taxpayer:
                apron_status = "taxpayer (below 1st apron)"
            else:
                apron_status = "below tax"
            violations.append(Violation(
                "SALARY_MATCH_FAIL", Severity.BLOCKER,
                f"{leg.team} ({apron_status}) cannot take in ${inc:,} for ${out:,} outgoing "
                f"(max ${allowed:,}).",
                team=leg.team,
            ))

    # 3. Second apron aggregation restriction
    for leg in proposal.legs:
        fin = fins[leg.team]
        if fin.is_above_second_apron and len(leg.outgoing_player_ids) > 1:
            violations.append(Violation(
                "SECOND_APRON_NO_AGGREGATION", Severity.BLOCKER,
                f"{leg.team} is above the second apron and cannot aggregate multiple "
                f"player salaries into a single trade.",
                team=leg.team,
            ))

    # 4. Stepien rule — cannot trade away consecutive future 1st-rounders
    for leg in proposal.legs:
        for pkid in leg.outgoing_pick_ids:
            pk = db.get(DraftPick, pkid)
            if pk and pk.round == 1 and pk.original_team_tricode == leg.team:
                if _would_violate_stepien(db, leg.team, pk.season_year, exclude_pick_id=pkid):
                    violations.append(Violation(
                        "STEPIEN_RULE", Severity.BLOCKER,
                        f"{leg.team} cannot trade away its {pk.season_year} 1st-round pick — "
                        f"would leave them without a 1st in two consecutive seasons.",
                        team=leg.team,
                    ))

    # Roster size check — would any team end up with more than 15 standard contracts?
    from app.cba.roster import STANDARD_ROSTER_MAX
    for leg in proposal.legs:
        outgoing_pids = set(leg.outgoing_player_ids)
        # Incoming players for this team
        incoming_count = 0
        for other in proposal.legs:
            if other.team == leg.team:
                continue
            for pid in other.outgoing_player_ids:
                try:
                    dest = proposal.destination("player", pid, other.team)
                except ValueError:
                    continue
                if dest == leg.team:
                    incoming_count += 1
        # Current standard contracts (excluding outgoing players)
        standard_now = (
            db.query(Contract)
            .filter(Contract.team_tricode == leg.team, Contract.is_active == True, Contract.is_two_way == False)
            .all()
        )
        standard_count = sum(1 for c in standard_now if c.player_id not in outgoing_pids)
        if standard_count + incoming_count > STANDARD_ROSTER_MAX:
            violations.append(Violation(
                "ROSTER_OVERFLOW", Severity.BLOCKER,
                f"{leg.team} would end up with {standard_count + incoming_count} standard "
                f"contracts after this trade (max {STANDARD_ROSTER_MAX}). "
                f"Release someone first, or send out an additional player.",
                team=leg.team,
            ))

    # 5. Touched-player rules:
    #    - Players signed within last 3 months can't be aggregated (TODO)
    #    - Players acquired via S&T can't be re-traded for 6 months (TODO)
    #    - Players with no-trade clauses (TODO)
    for leg in proposal.legs:
        for pid in leg.outgoing_player_ids:
            p = db.get(Player, pid)
            if p and getattr(p, "contracts", None):
                active = next((c for c in p.contracts if c.is_active), None)
                if active and active.no_trade_clause:
                    violations.append(Violation(
                        "NO_TRADE_CLAUSE", Severity.WARNING,
                        f"{p.name} has a no-trade clause and must waive it.",
                        team=leg.team,
                    ))

    return violations


def _would_violate_stepien(db: Session, team: str, traded_year: int, exclude_pick_id: int) -> bool:
    """After hypothetically removing the given pick, does the team have a 1st in each
    of the next 7 years, or violate the consecutive-year rule?"""
    picks = (
        db.query(DraftPick)
        .filter(
            DraftPick.original_team_tricode == team,  # only own picks count
            DraftPick.round == 1,
            DraftPick.owner_tricode == team,  # they still control it
            DraftPick.id != exclude_pick_id,
            DraftPick.season_year >= traded_year - 1,
            DraftPick.season_year <= traded_year + 7,
        )
        .all()
    )
    held_years = {p.season_year for p in picks}
    # Stepien: must have own 1st in either year N or year N+1 for any N.
    for year in range(traded_year, traded_year + 7):
        if year not in held_years and (year + 1) not in held_years:
            return True
    return False


# ---------------------------------------------------------------------------
# Free agent signing validation
# ---------------------------------------------------------------------------


@dataclass
class SigningProposal:
    player_id: int
    team: str
    season: str                          # first season
    salary_year1: int
    years: int                           # contract length
    raise_pct: float | None = None       # if None, infer based on signing type
    using: str = "BIRD"                  # signing mechanism (see Contract.signed_using)


def max_salary(years_of_service: int, season: str) -> int:
    cap = cap_for(season).salary_cap
    if years_of_service <= 6:
        pct = MAX_PCT_0_6_YRS
    elif years_of_service <= 9:
        pct = MAX_PCT_7_9_YRS
    else:
        pct = MAX_PCT_10_PLUS_YRS
    return int(cap * pct)


def validate_signing(db: Session, p: SigningProposal) -> list[Violation]:
    violations: list[Violation] = []
    player = db.get(Player, p.player_id)
    if not player:
        return [Violation("PLAYER_NOT_FOUND", Severity.BLOCKER, f"id={p.player_id}")]
    if not player.is_free_agent:
        violations.append(Violation("NOT_A_FREE_AGENT", Severity.BLOCKER,
                                    f"{player.name} is under contract."))

    # Roster size check: 15 standard + 3 two-way max
    from app.cba.roster import STANDARD_ROSTER_MAX, TWO_WAY_MAX
    contracts = (
        db.query(Contract)
        .filter(Contract.team_tricode == p.team.upper(), Contract.is_active == True)
        .all()
    )
    standard_count = sum(1 for c in contracts if not c.is_two_way)
    two_way_count = sum(1 for c in contracts if c.is_two_way)
    # MIN signings to bench / minimum-exception go to standard unless caller asked two-way
    if standard_count >= STANDARD_ROSTER_MAX:
        violations.append(Violation(
            "ROSTER_FULL", Severity.BLOCKER,
            f"{p.team} already has {standard_count}/{STANDARD_ROSTER_MAX} standard contracts. "
            f"Release a player on the team page before signing more.",
            team=p.team,
        ))
    elif standard_count >= STANDARD_ROSTER_MAX - 1 and two_way_count >= TWO_WAY_MAX:
        # Edge case but worth surfacing
        pass

    # Max contract check
    max_sal = max_salary(player.years_of_service, p.season)
    if p.salary_year1 > max_sal:
        violations.append(Violation(
            "EXCEEDS_MAX_SALARY", Severity.BLOCKER,
            f"${p.salary_year1:,} exceeds {player.years_of_service}-yr max of ${max_sal:,} "
            f"for {p.season}.",
        ))

    # Min salary check
    floor = min_salary(player.years_of_service, p.season)
    if p.salary_year1 < floor:
        violations.append(Violation(
            "BELOW_MIN_SALARY", Severity.BLOCKER,
            f"${p.salary_year1:,} is below {player.years_of_service}-yr min of ${floor:,} "
            f"for {p.season}.",
        ))

    # Contract length
    max_len = MAX_LENGTH_BIRD if p.using in ("BIRD", "MAX_BIRD") else MAX_LENGTH_OUTSIDE
    if p.years > max_len:
        violations.append(Violation(
            "EXCEEDS_MAX_LENGTH", Severity.BLOCKER,
            f"{p.years}-year contract exceeds max {max_len} for signing type {p.using}.",
        ))

    # Cap space / exception availability
    fin = compute_team_finances(db, p.team, p.season)

    # MIN exception: salary must actually be the minimum (no overpaying via "MIN")
    if p.using == "MIN":
        if p.salary_year1 > int(floor * 1.02):
            violations.append(Violation(
                "MIN_EXCEPTION_OVERPAY", Severity.BLOCKER,
                f"MIN exception only allows signing at the minimum salary (${floor:,}). "
                f"Pick a different mechanism (BIRD / NON_BIRD / MLE) for ${p.salary_year1:,}.",
            ))

    # BIRD / MAX_BIRD: team must actually hold this player's Bird rights (cap hold present)
    if p.using in ("BIRD", "MAX_BIRD"):
        hold_exists = db.query(CapHold).filter(
            CapHold.player_id == p.player_id,
            CapHold.team_tricode == p.team,
            CapHold.season == p.season,
            CapHold.renounced == False,
        ).first()
        # Or they were just under contract with this team this same season (rare race)
        if not hold_exists and (player.team_tricode != p.team):
            violations.append(Violation(
                "NO_BIRD_RIGHTS", Severity.BLOCKER,
                f"{p.team} does not hold Bird rights for {player.name} "
                f"(no non-renounced cap hold for {p.season}).",
                team=p.team,
            ))

    # NON_BIRD here is treated as "use cap space" — requires the team to actually
    # have it. (Over-the-cap teams cannot use cap space — they must use an exception.)
    if p.using == "NON_BIRD":
        if fin.is_over_cap or fin.cap_space < p.salary_year1:
            violations.append(Violation(
                "INSUFFICIENT_CAP_SPACE", Severity.BLOCKER,
                f"{p.team} doesn't have ${p.salary_year1:,} in cap space "
                f"(has ${max(0, fin.cap_space):,}). Use a different mechanism "
                f"(BIRD if your own FA, MLE if under tax, MIN otherwise).",
                team=p.team,
            ))
    if p.using in ("MLE_NON_TAX", "MLE_TAX", "MLE_ROOM"):
        cap_amount = {
            "MLE_NON_TAX": EXCEPTIONS_2026_27.non_taxpayer_mle,
            "MLE_TAX": EXCEPTIONS_2026_27.taxpayer_mle,
            "MLE_ROOM": EXCEPTIONS_2026_27.room_mle,
        }[p.using]
        if p.salary_year1 > cap_amount:
            violations.append(Violation(
                "MLE_EXCEEDED", Severity.BLOCKER,
                f"${p.salary_year1:,} exceeds {p.using} cap of ${cap_amount:,}.",
            ))
        if p.using == "MLE_TAX" and fin.is_above_first_apron:
            violations.append(Violation(
                "MLE_TAX_APRON_BLOCK", Severity.BLOCKER,
                f"{p.team} is above the first apron and cannot use the taxpayer MLE "
                f"(actually the taxpayer MLE is only available to teams above tax but "
                f"below first apron in 2023 CBA).",
                team=p.team,
            ))
        if p.using == "MLE_NON_TAX":
            # using the full non-tax MLE triggers a hard cap at the first apron
            # (validation should check resulting payroll <= first apron)
            new_total = fin.total_salary + p.salary_year1
            if new_total > fin.first_apron:
                violations.append(Violation(
                    "FIRST_APRON_HARD_CAP", Severity.BLOCKER,
                    f"Using the non-tax MLE hard-caps {p.team} at the first apron "
                    f"(${fin.first_apron:,}), but signing puts payroll at ${new_total:,}.",
                    team=p.team,
                ))

    # Second-apron restrictions on signings
    if fin.is_above_second_apron and p.using in ("MLE_NON_TAX", "MLE_TAX", "BAE"):
        violations.append(Violation(
            "SECOND_APRON_EXCEPTION_BLOCK", Severity.BLOCKER,
            f"{p.team} is above the second apron and cannot use {p.using}.",
            team=p.team,
        ))

    return violations
