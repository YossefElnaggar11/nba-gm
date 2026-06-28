"""Apply real-world 2026 offseason events (draft, trades, FA signings) on top
of the base seed.

Source of truth is `backend/data/raw/real_2026_events.json`. Whenever it has
non-empty `draft` / `trades` / `signings` arrays, those override the mock
auto-draft and get layered on. The admin import endpoint writes new data into
this file and re-applies it.
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.db.schema import (
    CapHold, Contract, ContractSeason, DraftPick, OptionType, PickStatus,
    Player, Prospect, Transaction, TransactionType,
)


EVENTS_PATH = Path(__file__).resolve().parents[1] / "data" / "raw" / "real_2026_events.json"


# ---------------------------------------------------------------------------
# File I/O
# ---------------------------------------------------------------------------


def load_events() -> dict:
    """Read the events file from disk, returning a stable shape."""
    if not EVENTS_PATH.exists():
        return {"draft_year": 2026, "draft": [], "trades": [], "signings": []}
    try:
        data = json.loads(EVENTS_PATH.read_text())
    except Exception:
        return {"draft_year": 2026, "draft": [], "trades": [], "signings": []}
    return {
        "draft_year": data.get("draft_year", 2026),
        "draft": data.get("draft", []),
        "trades": data.get("trades", []),
        "signings": data.get("signings", []),
    }


def save_events(events: dict) -> None:
    """Persist the events file to disk so it survives the next seed."""
    payload = {
        "_doc": "Real-world 2026 NBA offseason events. Apply via POST /api/admin/import-events.",
        "draft_year": events.get("draft_year", 2026),
        "draft": events.get("draft", []),
        "trades": events.get("trades", []),
        "signings": events.get("signings", []),
    }
    EVENTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    EVENTS_PATH.write_text(json.dumps(payload, indent=2))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _norm(s: str) -> str:
    """Loose name normalisation — strip diacritics, lowercase, drop punctuation."""
    import unicodedata
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.lower()
    for ch in [".", ",", "'", "-"]:
        s = s.replace(ch, "")
    return " ".join(s.split())


def find_player(db: Session, name: str) -> Player | None:
    """Look up a player by name — exact first, then loose match."""
    p = db.query(Player).filter(Player.name == name).first()
    if p:
        return p
    target = _norm(name)
    for cand in db.query(Player).all():
        if _norm(cand.name) == target:
            return cand
    return None


def find_pick(db: Session, year: int, round_: int, original_team: str) -> DraftPick | None:
    """Look up an outgoing pick by year, round, and the team that originated it."""
    return (
        db.query(DraftPick)
        .filter(
            DraftPick.season_year == year,
            DraftPick.round == round_,
            DraftPick.original_team_tricode == original_team,
            DraftPick.is_swap == False,
        )
        .first()
    )


def _parse_pick_spec(spec: str, fallback_team: str) -> tuple[int, int, str] | None:
    """Parse a pick string like '2027:1' or '2027:1:HOU' → (year, round, original_team).
    Falls back to fallback_team (the leg's team) if no original is given."""
    parts = spec.split(":")
    if len(parts) < 2:
        return None
    try:
        year = int(parts[0])
        round_ = int(parts[1])
    except ValueError:
        return None
    original = parts[2] if len(parts) >= 3 else fallback_team
    return (year, round_, original.upper())


# ---------------------------------------------------------------------------
# Draft
# ---------------------------------------------------------------------------


def revert_2026_draft(db: Session) -> None:
    """Undo any prior auto/real draft so we can re-apply from scratch.

    - Deletes Player rows created from 2026 prospects (rookie contracts cascade).
    - Resets 2026 prospects: drafted_to_team = None, created_player_id = None.
    - Resets 2026 picks: status = OWNED (not CONVEYED).
    """
    prospects = db.query(Prospect).filter(Prospect.draft_year == 2026).all()
    for p in prospects:
        if p.created_player_id:
            player = db.get(Player, p.created_player_id)
            if player:
                # Cascade should remove contracts; manual cleanup as safety.
                for c in player.contracts:
                    db.delete(c)
                db.delete(player)
        p.created_player_id = None
        p.drafted_to_team = None
        p.drafted_at_pick = None
    db.flush()
    picks = db.query(DraftPick).filter(
        DraftPick.season_year == 2026,
        DraftPick.is_swap == False,
    ).all()
    for pk in picks:
        pk.status = PickStatus.OWNED
    db.commit()


def apply_draft(db: Session, picks_data: list[dict]) -> dict:
    """Apply real draft results. Each entry: {pick, team, player, ...optional}.

    Behavior:
      - Look up the existing Prospect by name (loose match). If not found,
        CREATE a Prospect with the provided rank/college/age/overall/potential.
      - Look up the DraftPick by year + pick_number.
      - Mark CONVEYED + create rookie contract via _create_rookie_contract.
      - Returns a summary {applied, errors}.
    """
    from app.api.draft_picks import _create_rookie_contract

    applied: list[dict] = []
    errors: list[dict] = []

    for entry in picks_data:
        pick_num = entry.get("pick")
        team = (entry.get("team") or "").upper()
        name = entry.get("player")
        if not pick_num or not team or not name:
            errors.append({"entry": entry, "reason": "missing pick / team / player"})
            continue

        # Find the slot
        pick = db.query(DraftPick).filter(
            DraftPick.season_year == 2026,
            DraftPick.pick_number == pick_num,
            DraftPick.is_swap == False,
        ).first()
        if not pick:
            errors.append({"entry": entry, "reason": f"pick #{pick_num} not found"})
            continue

        if pick.owner_tricode != team:
            # User says team X picked at #N — but our pick data says team Y owns it.
            # Trust the user's data: this means a draft-day trade happened that we
            # don't have. Reassign the owner.
            pick.owner_tricode = team

        # Find or create the prospect
        prospect = (
            db.query(Prospect)
            .filter(Prospect.draft_year == 2026, Prospect.created_player_id.is_(None))
            .all()
        )
        match = next((p for p in prospect if _norm(p.name) == _norm(name)), None)
        if not match:
            match = Prospect(
                draft_year=2026,
                rank=entry.get("rank") or pick_num,
                name=name,
                position=entry.get("position"),
                college=entry.get("college"),
                age=entry.get("age"),
                overall=entry.get("overall"),
                potential=entry.get("potential"),
            )
            db.add(match)
            db.flush()

        # Apply overrides from input if present
        for fld in ("position", "college", "age", "overall", "potential"):
            if entry.get(fld) is not None:
                setattr(match, fld, entry[fld])

        match.drafted_to_team = team
        match.drafted_at_pick = pick_num
        player = _create_rookie_contract(db, match, team, pick_num)
        match.created_player_id = player.id
        pick.status = PickStatus.CONVEYED
        applied.append({"pick": pick_num, "team": team, "player": match.name, "player_id": player.id})

    db.commit()
    return {"applied": applied, "errors": errors}


# ---------------------------------------------------------------------------
# Trades
# ---------------------------------------------------------------------------


def apply_trade(db: Session, trade: dict) -> dict:
    """Execute a real trade. Format:
      {description, legs: [{team, out_players: [name], out_picks: ["YEAR:RD" or "YEAR:RD:ORIG"]}]}

    Routing is auto-default for 2-team trades (asset goes to the other team).
    For 3+ team trades, append {to: "TEAM"} to each player/pick entry
    (legs[i].out_players_routed: [{player: name, to: TEAM}]).
    """
    legs = trade.get("legs", [])
    if len(legs) < 2:
        return {"ok": False, "error": "trade must have at least 2 legs"}

    # Pre-resolve all assets to make sure we can move them
    leg_assets: list[dict] = []   # per leg: {team, players: [(p, dest)], picks: [(pk, dest)]}
    teams_in_trade = [l["team"].upper() for l in legs]

    for i, leg in enumerate(legs):
        team = leg["team"].upper()
        players_resolved = []
        picks_resolved = []

        # Default destination for 2-team trades = the other team
        default_dest = teams_in_trade[1 - i] if len(teams_in_trade) == 2 else None

        # Routed players (3+ team format)
        for r in leg.get("out_players_routed", []):
            name = r["player"]
            dest = r["to"].upper()
            player = find_player(db, name)
            if not player:
                return {"ok": False, "error": f"player not found: {name}"}
            if player.team_tricode != team:
                return {"ok": False, "error": f"{name} is on {player.team_tricode}, not {team}"}
            players_resolved.append((player, dest))

        # Simple players (uses default_dest)
        for name in leg.get("out_players", []):
            player = find_player(db, name)
            if not player:
                return {"ok": False, "error": f"player not found: {name}"}
            if player.team_tricode != team:
                return {"ok": False, "error": f"{name} is on {player.team_tricode}, not {team}"}
            if not default_dest:
                return {"ok": False, "error": f"3+ team trade: route {name} via out_players_routed"}
            players_resolved.append((player, default_dest))

        # Routed picks
        for r in leg.get("out_picks_routed", []):
            parsed = _parse_pick_spec(r["pick"], team)
            if not parsed:
                return {"ok": False, "error": f"bad pick spec: {r['pick']}"}
            year, rd, orig = parsed
            pk = find_pick(db, year, rd, orig)
            if not pk:
                return {"ok": False, "error": f"pick not found: {r['pick']}"}
            if pk.owner_tricode != team:
                return {"ok": False, "error": f"pick {r['pick']} is owned by {pk.owner_tricode}, not {team}"}
            picks_resolved.append((pk, r["to"].upper()))

        # Simple picks (uses default_dest)
        for spec in leg.get("out_picks", []):
            parsed = _parse_pick_spec(spec, team)
            if not parsed:
                return {"ok": False, "error": f"bad pick spec: {spec}"}
            year, rd, orig = parsed
            pk = find_pick(db, year, rd, orig)
            if not pk:
                return {"ok": False, "error": f"pick not found: {spec}"}
            if pk.owner_tricode != team:
                return {"ok": False, "error": f"pick {spec} is owned by {pk.owner_tricode}, not {team}"}
            if not default_dest:
                return {"ok": False, "error": f"3+ team trade: route pick {spec} via out_picks_routed"}
            picks_resolved.append((pk, default_dest))

        leg_assets.append({"team": team, "players": players_resolved, "picks": picks_resolved})

    # All resolved successfully — apply
    moved_players = []
    for la in leg_assets:
        for player, dest in la["players"]:
            player.team_tricode = dest
            player.bird_years_with_team = 0
            for c in player.contracts:
                if c.is_active:
                    c.team_tricode = dest
            moved_players.append({"player": player.name, "from": la["team"], "to": dest})
        for pk, dest in la["picks"]:
            pk.owner_tricode = dest

    desc = trade.get("description") or " <-> ".join(la["team"] for la in leg_assets)
    db.add(Transaction(
        type=TransactionType.TRADE,
        payload={
            "legs": [
                {
                    "team": la["team"],
                    "out_players": [p.name for p, _ in la["players"]],
                    "out_picks": [f"{pk.season_year}:R{pk.round}" for pk, _ in la["picks"]],
                }
                for la in leg_assets
            ],
        },
        description=f"REAL TRADE: {desc}",
        is_user_action=False,
    ))
    db.commit()
    return {"ok": True, "moved": moved_players, "description": desc}


# ---------------------------------------------------------------------------
# Free agent signings
# ---------------------------------------------------------------------------


def apply_signing(db: Session, signing: dict) -> dict:
    """Apply a single real-world FA signing.
      {player, team, salary_year1, years, using?, raise_pct?, contract_seasons?}

    If `contract_seasons` is provided (list of {season, salary, option_type?}),
    we use those literally; otherwise we generate from salary_year1 + years +
    raise_pct (default 8% for BIRD, 5% otherwise).
    """
    name = signing.get("player")
    team = (signing.get("team") or "").upper()
    if not name or not team:
        return {"ok": False, "error": "missing player or team"}

    player = find_player(db, name)
    if not player:
        return {"ok": False, "error": f"player not found: {name}"}

    # Deactivate any existing active contract
    for c in player.contracts:
        if c.is_active:
            c.is_active = False
    # Clear any cap holds on the player
    for h in db.query(CapHold).filter(CapHold.player_id == player.id, CapHold.renounced == False).all():
        h.renounced = True

    using = signing.get("using") or ("BIRD" if signing.get("salary_year1", 0) > 5_000_000 else "MIN")
    contract = Contract(
        player_id=player.id,
        team_tricode=team,
        signed_date=date.today(),
        signed_using=using,
        is_active=True,
    )
    db.add(contract)
    db.flush()

    seasons = signing.get("contract_seasons")
    if seasons:
        for s in seasons:
            db.add(ContractSeason(
                contract_id=contract.id,
                season=s["season"],
                salary=int(s["salary"]),
                option_type=OptionType(s.get("option_type", "NONE")),
                guaranteed=s.get("guaranteed", True),
            ))
    else:
        raise_pct = signing.get("raise_pct", 0.08 if using == "BIRD" else 0.05)
        sal = int(signing["salary_year1"])
        years = int(signing.get("years", 1))
        from app.cba.constants import CAP_HISTORY
        cap_keys = list(CAP_HISTORY.keys())
        try:
            start_idx = cap_keys.index(signing.get("first_season", "2026-27"))
        except ValueError:
            start_idx = 0
        for season in cap_keys[start_idx:start_idx + years]:
            db.add(ContractSeason(
                contract_id=contract.id,
                season=season,
                salary=sal,
                option_type=OptionType.NONE,
                guaranteed=True,
            ))
            sal = int(sal * (1 + raise_pct))

    player.team_tricode = team
    player.is_free_agent = False
    player.fa_type = None
    player.bird_years_with_team = 1

    db.add(Transaction(
        type=TransactionType.SIGN_FA,
        payload={"player_id": player.id, "team": team, "using": using, "real": True},
        description=f"REAL SIGNING: {player.name} → {team} ({using})",
        is_user_action=False,
    ))
    db.commit()
    return {"ok": True, "player": player.name, "team": team}


# ---------------------------------------------------------------------------
# Orchestration — called from seed and from admin endpoint
# ---------------------------------------------------------------------------


def apply_all_events(db: Session, events: dict) -> dict:
    """Apply draft + trades + signings in order. Trades happen BEFORE signings
    because a player traded mid-offseason needs to be on the new team when his
    extension is recorded.

    Order rationale:
      1. Draft (rookies join their teams)
      2. Trades (players move between teams)
      3. Signings (FAs / re-signings, using whatever team they're on now)
    """
    summary: dict[str, Any] = {"draft": None, "trades": [], "signings": []}

    draft_picks = events.get("draft") or []
    if draft_picks:
        revert_2026_draft(db)
        summary["draft"] = apply_draft(db, draft_picks)
        # Fill any picks the user didn't specify with the mock auto-draft so
        # the back half of round 2 still gets rookies on rosters.
        from app.db.seed import seed_2026_draft_results
        seed_2026_draft_results(db)

    for trade in events.get("trades") or []:
        summary["trades"].append(apply_trade(db, trade))

    for sig in events.get("signings") or []:
        summary["signings"].append(apply_signing(db, sig))

    return summary
