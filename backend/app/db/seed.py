"""Seed the SQLite DB from scraped JSON files.

Run with: python -m app.db.seed
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.data.teams import TEAMS
from app.db.schema import (
    Base, CapHold, Contract, ContractSeason, DraftPick, OptionType, PickStatus, Player, Prospect, Team,
)

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
DB_PATH = DATA_DIR / "nbagm.db"
RAW = DATA_DIR / "raw"


def seed_teams(db: Session) -> None:
    print("Seeding teams...")
    for t in TEAMS:
        db.merge(Team(
            tricode=t.tricode, full_name=t.full_name, city=t.city, nickname=t.nickname,
            conference=t.conference, division=t.division,
            primary_color=t.primary_color, secondary_color=t.secondary_color,
        ))
    db.commit()
    print(f"  -> {len(TEAMS)} teams")


def _estimate_yos(age: int | None) -> int:
    """Rough estimate of years of service from age. Most NBA players enter at 19-20."""
    if not age:
        return 0
    return max(0, min(age - 19, 20))


def _cap_hold_amount(last_salary: int, years_of_service: int, overall: int | None = None, age: int | None = None, position: str | None = None) -> int:
    """Cap hold formula. CBA-realistic but capped at 135% of expected market value
    so holds don't wildly exceed the player's actual worth (e.g., a $28M TO declined
    shouldn't become a $42M cap hold for a $19M player).
    """
    if last_salary <= 3_000_000:
        return last_salary
    if years_of_service <= 2:
        raw = int(last_salary * 2.5)
    else:
        raw = max(int(last_salary * 1.5), 5_000_000)
    # Cap at 135% of market value if we know the player's rating
    if overall is not None:
        from app.cba.market_value import expected_market_value
        market = expected_market_value(overall, age, "2026-27", position)
        raw = min(raw, int(market * 1.35))
        raw = max(raw, int(last_salary * 0.5))   # floor: 50% of last
    return raw


def seed_contracts(db: Session) -> None:
    path = RAW / "contracts_2026_offseason.json"
    if not path.exists():
        print(f"  ! {path} not found, skipping contracts")
        return
    print("Seeding contracts + cap holds for expiring players...")
    data: dict[str, list[dict]] = json.loads(path.read_text())
    total_players = 0
    total_contracts = 0
    total_holds = 0
    for tricode, players in data.items():
        for p in players:
            # Skip players with no contract data (free agents / two-way unsigned)
            if not p["seasons"]:
                continue
            future_seasons = [s for s in p["seasons"] if s["season"] != "2025-26"]
            yos = _estimate_yos(p["age"])
            last_25_26 = next((s for s in p["seasons"] if s["season"] == "2025-26"), None)
            is_fa = not future_seasons
            existing = db.query(Player).filter(Player.bbr_id == p["bbr_id"]).one_or_none()
            if not existing:
                existing = Player(
                    bbr_id=p["bbr_id"], name=p["name"], age=p["age"],
                    team_tricode=tricode if future_seasons else None,
                    is_free_agent=is_fa,
                    fa_type="UFA" if is_fa else None,
                    years_of_service=yos,
                )
                db.add(existing)
                db.flush()
                total_players += 1
            else:
                existing.team_tricode = tricode if future_seasons else None
                existing.is_free_agent = is_fa
                if not existing.years_of_service:
                    existing.years_of_service = yos
            # Cap hold: this player was on `tricode` last year, now expiring
            if is_fa and last_25_26 and last_25_26["salary"] > 0:
                hold = _cap_hold_amount(last_25_26["salary"], yos,
                                        overall=existing.overall, age=existing.age,
                                        position=existing.position)
                db.add(CapHold(
                    player_id=existing.id, team_tricode=tricode,
                    season="2026-27", amount=hold, renounced=False,
                    notes=f"Bird-rights cap hold from prior ${last_25_26['salary']:,} salary",
                ))
                total_holds += 1
            if not future_seasons:
                continue
            contract = Contract(
                player_id=existing.id, team_tricode=tricode,
                signed_date=date(2024, 7, 1),  # placeholder
                signed_using="UNKNOWN",
                is_active=True,
            )
            db.add(contract)
            db.flush()
            for s in future_seasons:
                db.add(ContractSeason(
                    contract_id=contract.id, season=s["season"], salary=s["salary"],
                    option_type=OptionType(s["option"]),
                    guaranteed=s["guaranteed"],
                ))
            total_contracts += 1
    db.commit()
    print(f"  -> {total_players} players, {total_contracts} active contracts, {total_holds} cap holds")


def seed_free_agents(db: Session) -> None:
    path = RAW / "free_agents_2026.json"
    if not path.exists():
        print(f"  ! {path} not found, skipping FAs")
        return
    print("Seeding free agents...")
    data = json.loads(path.read_text())
    count_new = 0
    count_enriched = 0
    for fa in data:
        existing = db.query(Player).filter(Player.name == fa["name"]).one_or_none()
        if existing:
            # Only enrich metadata. Do NOT flip FA status or fa_type: if they have
            # a contract with 2026-27 money (PO/TO/guaranteed), they're still under
            # contract until they actually opt out. The FA-flip happens when the
            # user/AI processes options during the offseason phase.
            if fa.get("age") and not existing.age:
                existing.age = fa["age"]
            if fa.get("years_of_service") is not None:
                existing.years_of_service = fa["years_of_service"]
            if existing.is_free_agent:
                existing.fa_type = fa["fa_type"]
            count_enriched += 1
            continue
        db.add(Player(
            name=fa["name"], age=fa.get("age"),
            position=fa.get("position"),
            years_of_service=fa.get("years_of_service") or 0,
            team_tricode=None,
            is_free_agent=True,
            fa_type=fa["fa_type"],
        ))
        count_new += 1
    db.commit()
    print(f"  -> {count_new} new FA players, {count_enriched} existing players enriched")


def seed_draft_picks(db: Session) -> None:
    """Seed 2026 picks (with full traded-pick attribution) + 2027-2032 (default
    ownership = own picks, plus hand-curated known trades layered on top).
    """
    from app.data.future_picks_curated import KNOWN_TRADED_PICKS
    from app.data.teams import TEAMS

    # 2026: full scraped data
    path = RAW / "draft_2026_order.json"
    if not path.exists():
        print(f"  ! {path} not found, skipping 2026 picks")
    else:
        print("Seeding 2026 draft picks...")
        data = json.loads(path.read_text())
        count = 0
        for round_idx, round_key in enumerate(["first_round", "second_round"], start=1):
            for entry in data[round_key]:
                db.add(DraftPick(
                    season_year=2026,
                    round=round_idx,
                    original_team_tricode=entry["original_team"],
                    owner_tricode=entry["team"],
                    pick_number=entry["pick"],
                    status=PickStatus.OWNED,
                    notes=entry.get("note"),
                ))
                count += 1
        db.commit()
        print(f"  -> {count} draft picks for 2026")

    # 2027-2032: default each team owns its own picks, then overlay traded picks
    print("Seeding 2027-2032 draft picks (defaults + known trades)...")
    traded_index = {(p.year, p.round, p.original): p for p in KNOWN_TRADED_PICKS if not p.is_swap}
    swap_index = {(p.year, p.round, p.original): p for p in KNOWN_TRADED_PICKS if p.is_swap}
    count = 0
    for year in range(2027, 2033):
        for round_ in (1, 2):
            for team in TEAMS:
                traded = traded_index.get((year, round_, team.tricode))
                owner = traded.owner if traded else team.tricode
                protection_text = traded.protection if traded else None
                note = traded.note if traded else None
                db.add(DraftPick(
                    season_year=year,
                    round=round_,
                    original_team_tricode=team.tricode,
                    owner_tricode=owner,
                    pick_number=None,
                    status=PickStatus.LOTTERY_PENDING if round_ == 1 else PickStatus.OWNED,
                    protection_text=protection_text,
                    is_swap=False,
                    notes=note,
                ))
                count += 1
            # Add swap rights as separate pick rows (they're virtual rights, not pick obligations)
            for (sy, sr, sorig), sw in swap_index.items():
                if sy == year and sr == round_:
                    db.add(DraftPick(
                        season_year=year,
                        round=round_,
                        original_team_tricode=sorig,
                        owner_tricode=sw.owner,
                        pick_number=None,
                        status=PickStatus.OWNED,
                        protection_text=sw.protection,
                        is_swap=True,
                        swap_with_team=sw.swap_with,
                        notes=sw.note,
                    ))
                    count += 1
    db.commit()
    print(f"  -> {count} draft picks for 2027-2032 (incl swap rights)")


def seed_prospects(db: Session) -> None:
    print("Seeding draft prospects...")
    total = 0
    for year in (2026, 2027, 2028):
        path = RAW / f"prospects_{year}.json"
        if not path.exists():
            print(f"  ! {path} not found")
            continue
        for entry in json.loads(path.read_text()):
            db.add(Prospect(
                draft_year=year,
                rank=entry["rank"],
                name=entry["name"],
                position=entry.get("position"),
                college=entry.get("college"),
                age=entry.get("age"),
                overall=entry.get("overall"),
                potential=entry.get("potential"),
            ))
            total += 1
    db.commit()
    print(f"  -> {total} prospects across 2026 + 2027 + 2028")


def _salary_implied_ovr_floor(salary_y1: int) -> int:
    """Stars who didn't play much last year still deserve a high baseline OVR
    based on their max-contract status. Prevents Bradley-Beal-style underrating
    when scraping injured players' limited stats."""
    if salary_y1 >= 50_000_000: return 88
    if salary_y1 >= 40_000_000: return 85
    if salary_y1 >= 30_000_000: return 81
    if salary_y1 >= 20_000_000: return 77
    if salary_y1 >= 15_000_000: return 73
    return 0


def _ascending_player_bump(age: int | None, mpg: float | None, ovr: int | None) -> int:
    """Young players who broke through last season + playoffs should get an
    OVR bump to reflect their trajectory. More inclusive than before."""
    if not age or not mpg or not ovr:
        return 0
    # Stars are stars — don't bump them above 90
    if ovr >= 90:
        return 0
    if age <= 22 and mpg >= 18 and ovr >= 65:
        return 5   # Big riser (Ajay Mitchell, Reed Sheppard, Stephon Castle tier)
    if age <= 23 and mpg >= 20 and ovr >= 68:
        return 4
    if age <= 24 and mpg >= 22 and ovr >= 72:
        return 3
    if age <= 25 and mpg >= 26 and ovr >= 75:
        return 2
    if age <= 26 and mpg >= 28 and ovr >= 78:
        return 1
    return 0


def seed_player_ratings(db: Session) -> None:
    """Apply real stat-derived ratings + per-game baseline stats from BBR scrape.
    Then apply salary-implied floor for injured stars + recompute cap holds."""
    path = RAW / "player_ratings_2026.json"
    if not path.exists():
        print(f"  ! {path} not found — skipping ratings")
        return
    print("Applying stat-based ratings + baseline stats to players...")
    data = json.loads(path.read_text())
    matched = 0
    for r in data:
        bbr_id = r["bbr_id"]
        player = db.query(Player).filter(Player.bbr_id == bbr_id).one_or_none()
        if not player:
            continue
        player.overall = r["overall"]
        player.potential = r["potential"]
        player.baseline_ppg = r.get("ppg", 0)
        player.baseline_rpg = r.get("rpg", 0)
        player.baseline_apg = r.get("apg", 0)
        player.baseline_spg = r.get("spg", 0)
        player.baseline_bpg = r.get("bpg", 0)
        player.baseline_mpg = r.get("mpg", 0)
        if r.get("position") and not player.position:
            player.position = r["position"]
        matched += 1
    db.commit()
    print(f"  -> {matched} players rated + baseline stats applied")

    # Ascending player bump for young high-mpg performers
    print("Applying ascending-player OVR bumps...")
    bumped_ascending = 0
    ascending_examples = []
    for player in db.query(Player).all():
        if not player.overall:
            continue
        bump = _ascending_player_bump(player.age, player.baseline_mpg, player.overall)
        if bump > 0:
            old = player.overall
            player.overall = min(96, player.overall + bump)
            if player.potential and player.potential < player.overall + 5:
                player.potential = min(99, player.overall + 5)
            bumped_ascending += 1
            if old < player.overall:
                ascending_examples.append((player.name, old, player.overall))
    db.commit()
    print(f"  -> {bumped_ascending} ascending young players bumped")
    if ascending_examples:
        ascending_examples.sort(key=lambda x: -(x[2] - x[1]))
        for n, o, w in ascending_examples[:6]:
            print(f"     {n}: {o} -> {w}")

    # Salary-implied floor for high-paid players (injured stars get min OVR for their tier)
    print("Applying salary-implied OVR floors...")
    boosted = 0
    raw_contracts = json.loads((RAW / "contracts_2026_offseason.json").read_text())
    salary_by_bbr: dict[str, int] = {}
    for team_tricode, players in raw_contracts.items():
        for p in players:
            current_year = next((s for s in p["seasons"] if s["season"] in ("2025-26", "2026-27")), None)
            if current_year and current_year["salary"] > 0:
                salary_by_bbr[p["bbr_id"]] = current_year["salary"]
    for bbr_id, sal in salary_by_bbr.items():
        floor = _salary_implied_ovr_floor(sal)
        if floor <= 0:
            continue
        player = db.query(Player).filter(Player.bbr_id == bbr_id).one_or_none()
        if not player or not player.overall:
            continue
        if player.overall < floor:
            player.overall = floor
            # Bump potential too if needed
            if player.potential and player.potential < floor:
                player.potential = floor
            boosted += 1
    db.commit()
    print(f"  -> {boosted} players bumped by salary-implied OVR floor")

    # Recompute cap holds now that OVR is set (after the salary floor too)
    print("Recomputing cap holds with player ratings...")
    raw_contracts = json.loads((RAW / "contracts_2026_offseason.json").read_text())
    # Build a quick lookup: bbr_id -> 2025-26 salary
    last_salary_by_bbr: dict[str, int] = {}
    for team_tricode, players in raw_contracts.items():
        for p in players:
            last = next((s for s in p["seasons"] if s["season"] == "2025-26"), None)
            if last and last["salary"] > 0:
                last_salary_by_bbr[p["bbr_id"]] = last["salary"]
    fixed = 0
    for hold in db.query(CapHold).all():
        player = db.get(Player, hold.player_id)
        if not player or not player.bbr_id:
            continue
        last_sal = last_salary_by_bbr.get(player.bbr_id, 0)
        if last_sal <= 0:
            continue
        yos = player.years_of_service or 0
        new_hold = _cap_hold_amount(last_sal, yos,
                                     overall=player.overall, age=player.age,
                                     position=player.position)
        if new_hold != hold.amount:
            hold.amount = new_hold
            fixed += 1
    db.commit()
    print(f"  -> {fixed} cap holds recomputed with ratings")


def _wipe_data(db: Session) -> None:
    """Delete all rows from all tables. Keeps the file (so other processes
    holding the connection don't get readonly errors)."""
    from sqlalchemy import delete
    for table in reversed(Base.metadata.sorted_tables):
        db.execute(delete(table))
    db.commit()


def main(wipe_only: bool = False, engine=None):
    """Seed the DB. If `engine` provided, use it (data-only wipe + reseed) so
    callers like the /api/admin/reset endpoint don't have to drop the file."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if engine is None:
        if DB_PATH.exists():
            DB_PATH.unlink()
            print(f"Removed existing DB at {DB_PATH}")
        engine = create_engine(f"sqlite:///{DB_PATH}", future=True)
        Base.metadata.create_all(engine)
    else:
        Base.metadata.create_all(engine)
    with Session(engine) as db:
        if engine is not None:
            _wipe_data(db)
        seed_teams(db)
        seed_contracts(db)
        seed_free_agents(db)
        seed_draft_picks(db)
        seed_prospects(db)
        seed_player_ratings(db)
    print(f"\nSeed complete -> {DB_PATH}")


if __name__ == "__main__":
    main()
