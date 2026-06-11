"""Season simulation API."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.data.teams import BY_TRICODE
from app.db.schema import Season, TeamRecord
from app.sim.engine import simulate_season, team_strength
from app.db.schema import Season as SeasonModel

router = APIRouter(prefix="/api/sim", tags=["sim"])


def get_db():
    from app.main import SessionLocal
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


SEASON_ORDER = ["2026-27", "2027-28"]


@router.post("/season/{season}")
def run_season(season: str, db: Session = Depends(get_db)):
    from app.db.schema import DraftPick, PickStatus
    # Enforce sequential simulation — can't sim 2027-28 before 2026-27 is done
    try:
        season_idx = SEASON_ORDER.index(season)
    except ValueError:
        raise HTTPException(400, f"Season {season} is not in the game scope ({SEASON_ORDER})")
    if season_idx > 0:
        prior = SEASON_ORDER[season_idx - 1]
        prior_row = db.get(Season, prior)
        if not prior_row or not prior_row.simulated:
            raise HTTPException(409, {
                "message": f"Cannot sim {season} — {prior} must be simulated first.",
                "blocked_by": prior,
            })

    # Enforce: this season's draft must be done before we can sim
    draft_year = int(season.split("-")[0])
    undrafted = (
        db.query(DraftPick)
        .filter(
            DraftPick.season_year == draft_year,
            DraftPick.status == PickStatus.OWNED,
            DraftPick.pick_number.isnot(None),
            DraftPick.is_swap == False,
        )
        .count()
    )
    if undrafted > 0:
        raise HTTPException(409, {
            "message": f"Cannot sim {season} — {undrafted} {draft_year} draft picks still unmade. Run the draft first.",
            "blocked_by": f"{draft_year} draft",
            "undrafted_count": undrafted,
        })

    existing = db.get(Season, season)
    if existing and existing.simulated:
        db.query(TeamRecord).filter(TeamRecord.season == season).delete()
        existing.simulated = False
        existing.champion_tricode = None
        db.commit()
    sim = simulate_season(db, season)
    return {
        "season": sim.season,
        "champion": sim.champion,
        "finals_mvp": sim.finals_mvp,
        "mvp": sim.mvp,
        "mvp_team": sim.mvp_team,
        "dpoy": sim.dpoy,
        "dpoy_team": sim.dpoy_team,
        "roy": sim.roy,
        "roy_team": sim.roy_team,
        "all_nba_first": sim.all_nba_first,
        "all_nba_second": sim.all_nba_second,
        "all_nba_third": sim.all_nba_third,
        "all_stars_east": sim.all_stars_east,
        "all_stars_west": sim.all_stars_west,
        "league_avg_rating": round(sum(s["rating"] for s in sim.standings.values()) / len(sim.standings), 1),
        "east_seeds": sim.east_seeds[:10],
        "west_seeds": sim.west_seeds[:10],
        "standings": [
            {
                "tricode": t,
                "wins": s["wins"], "losses": s["losses"],
                "conference": s["conference"], "rating": s["rating"],
                "playoff_exit": sim.playoff_results.get(t),
            }
            for t, s in sorted(sim.standings.items(), key=lambda kv: -kv[1]["wins"])
        ],
    }


@router.get("/standings/{season}")
def get_standings(season: str, db: Session = Depends(get_db)):
    rows = db.query(TeamRecord).filter(TeamRecord.season == season).all()
    if not rows:
        raise HTTPException(404, f"Season {season} not simulated yet")
    rows.sort(key=lambda r: (BY_TRICODE[r.team_tricode].conference, -r.wins))
    s_row = db.get(Season, season)
    return {
        "season": season,
        "champion": s_row.champion_tricode if s_row else None,
        "teams": [
            {
                "tricode": r.team_tricode,
                "conference": BY_TRICODE[r.team_tricode].conference,
                "wins": r.wins, "losses": r.losses,
                "seed": r.seed, "made_playoffs": r.made_playoffs,
                "playoff_exit_round": r.playoff_exit_round,
            }
            for r in rows
        ],
    }


@router.get("/strength/{tricode}")
def get_team_strength(tricode: str, season: str = "2026-27", db: Session = Depends(get_db)):
    rating, top8 = team_strength(db, tricode.upper(), season)
    return {
        "team": tricode.upper(),
        "season": season,
        "rating": round(rating, 1),
        "top8": [{"name": n, "ovr": r} for n, r in top8],
    }


@router.get("/awards-history")
def awards_history(db: Session = Depends(get_db)):
    """Per-season awards: champion, Finals MVP, MVP, DPOY, ROY, All-NBA."""
    seasons = db.query(SeasonModel).filter(SeasonModel.simulated == True).order_by(SeasonModel.season).all()
    return [
        {
            "season": s.season,
            "champion": s.champion_tricode,
            "finals_mvp": s.finals_mvp_name,
            "finals_mvp_team": s.finals_mvp_team,
            "mvp": s.mvp_name,
            "mvp_team": s.mvp_team,
            "dpoy": s.dpoy_name,
            "dpoy_team": s.dpoy_team,
            "roy": s.roy_name,
            "roy_team": s.roy_team,
            "all_nba": s.all_nba_json or {},
        }
        for s in seasons
    ]
