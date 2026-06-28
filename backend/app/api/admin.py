"""Admin / lifecycle endpoints: reset, renounce cap holds, mode switching."""
from __future__ import annotations

import shutil
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.schema import CapHold, Player

router = APIRouter(prefix="/api/admin", tags=["admin"])

# Path constants for mode swapping
DB_PATH = Path(__file__).resolve().parents[2] / "data" / "nbagm.db"
CAREER_BACKUP = Path(__file__).resolve().parents[2] / "data" / "nbagm_career_save.db"

# In-memory tracking of which mode is currently active. Default to "career".
_active_mode = "career"


def get_active_mode() -> str:
    return _active_mode


def get_db():
    from app.main import SessionLocal
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.post("/reset")
def reset_game():
    """Hard reset: wipe the working DB AND delete the career save backup so
    the user gets a truly fresh 2026 offseason next time they enter either
    mode. Also forces a clean schema (drop_all + create_all) to scrub any
    stale tables left over from prior versions."""
    global _active_mode
    from app.db.schema import Base
    from app.db.seed import main as seed_main
    from app.main import engine

    # Delete the career save backup so the user can't accidentally restore old state
    deleted_backup = False
    if CAREER_BACKUP.exists():
        try:
            CAREER_BACKUP.unlink()
            deleted_backup = True
        except Exception:
            pass

    # Drop + recreate every table so any leftover schema state is purged
    try:
        engine.dispose()
        Base.metadata.drop_all(engine)
        Base.metadata.create_all(engine)
    except Exception:
        pass

    seed_main(engine=engine)
    _active_mode = "career"
    return {
        "ok": True,
        "message": "Hard reset complete — career save cleared, 2026 offseason restored.",
        "career_backup_deleted": deleted_backup,
    }


class EnterModeIn(BaseModel):
    mode: str   # "career" | "offseason"


@router.post("/enter-mode")
def enter_mode(req: EnterModeIn):
    """Switch active game mode. Career state is only persisted via explicit
    /save-career calls — entering career mode always restores from the last
    saved snapshot (so unsaved sims/trades are discarded on re-entry).

    - **→ Offseason**: always reseed (fresh sandbox each entry)
    - **→ Career**: restore from nbagm_career_save.db if it exists, else seed fresh
    """
    global _active_mode
    target = req.mode.lower()
    if target not in ("career", "offseason"):
        raise HTTPException(400, "mode must be 'career' or 'offseason'")

    from app.db.schema import Base
    from app.db.seed import main as seed_main
    from app.main import engine

    msg_parts = []

    if target == "offseason":
        # Fully drop + recreate all tables so the Offseason sandbox is *guaranteed*
        # independent from any prior Career state. (seed_main also wipes data,
        # but drop_all + create_all gives total isolation from any leftover
        # schema differences or stale rows.)
        from app.db.schema import Base
        try:
            engine.dispose()
            Base.metadata.drop_all(engine)
            Base.metadata.create_all(engine)
        except Exception:
            pass
        seed_main(engine=engine)
        msg_parts.append("fresh sandbox started")
    else:
        if CAREER_BACKUP.exists():
            try:
                engine.dispose()
                shutil.copy2(CAREER_BACKUP, DB_PATH)
                # The backup may have been created before newer tables existed
                # (e.g. TradeException). Ensure all tables are present.
                Base.metadata.create_all(engine)
                msg_parts.append("career state restored from last save")
            except Exception as e:
                seed_main(engine=engine)
                msg_parts.append(f"career restore failed, started fresh: {e}")
        else:
            # No backup file. Only reseed if the DB is actually empty — otherwise
            # leave the existing populated state alone. (Without this, every
            # visit to /setup/team?mode=career would re-run the ~8s seed.)
            from app.db.schema import Team
            from sqlalchemy.orm import Session as _S
            with _S(engine) as db:
                has_data = db.query(Team).first() is not None
            if has_data:
                msg_parts.append("career mode active (no save yet, current state preserved)")
            else:
                seed_main(engine=engine)
                msg_parts.append("career state initialised fresh")

    _active_mode = target
    return {"ok": True, "mode": target, "message": "; ".join(msg_parts) or "no change"}


@router.get("/mode")
def get_mode():
    return {"mode": _active_mode}


@router.post("/save-career")
def save_career():
    """Explicit checkpoint: snapshot current state to career backup. Only meaningful
    in career mode — called automatically after sims/rollovers."""
    if _active_mode != "career":
        return {"ok": False, "message": f"Not in career mode (currently {_active_mode})"}
    try:
        shutil.copy2(DB_PATH, CAREER_BACKUP)
        return {"ok": True, "message": "Career state saved"}
    except Exception as e:
        return {"ok": False, "message": str(e)}


class ImportEventsIn(BaseModel):
    """Real-world 2026 offseason events the user wants applied to the DB.
    Any of the three lists can be omitted/empty. See docs/sample_real_events.json
    for the full schema."""
    draft: list[dict] | None = None
    trades: list[dict] | None = None
    signings: list[dict] | None = None
    merge: bool = True   # if True, append to existing events; if False, replace


@router.post("/import-events")
def import_events(req: ImportEventsIn):
    """Accept a JSON payload of real-world events, persist it to
    real_2026_events.json, and re-apply (revert+reapply) to the live DB.

    Whatever's in the file becomes the source of truth on the next reset/seed,
    so updates survive Render redeploys too.
    """
    from app.db.real_events import load_events, save_events, apply_all_events, revert_2026_draft
    from app.main import SessionLocal

    existing = load_events()
    new_draft = req.draft if req.draft is not None else (existing["draft"] if req.merge else [])
    new_trades = (existing["trades"] if req.merge else []) + (req.trades or [])
    new_signings = (existing["signings"] if req.merge else []) + (req.signings or [])

    events = {
        "draft_year": 2026,
        "draft": new_draft,
        "trades": new_trades,
        "signings": new_signings,
    }
    save_events(events)

    # Apply to the live DB. Note: we don't fully re-seed; we only revert the
    # 2026 draft (so we can re-apply with new picks) and then layer trades /
    # signings on top of current state.
    db = SessionLocal()
    try:
        if events["draft"]:
            revert_2026_draft(db)
        summary = apply_all_events(db, events)
        return {
            "ok": True,
            "saved_to": "data/raw/real_2026_events.json",
            "picks_applied": len(summary["draft"]["applied"]) if summary["draft"] else 0,
            "trades_applied": sum(1 for t in summary["trades"] if t.get("ok")),
            "signings_applied": sum(1 for s in summary["signings"] if s.get("ok")),
            "summary": summary,
        }
    finally:
        db.close()


@router.get("/events")
def get_events():
    """Return the current real_2026_events.json contents (for the admin UI)."""
    from app.db.real_events import load_events
    return load_events()


class ReleaseIn(BaseModel):
    player_id: int


@router.post("/release-player")
def release_player(req: ReleaseIn):
    """Waive a player to free agency. Deactivates their contract and clears the
    team's books for them (game simplification — real NBA stretches dead money)."""
    from app.main import SessionLocal
    from app.db.schema import Player as _P
    db = SessionLocal()
    try:
        p = db.get(_P, req.player_id)
        if not p:
            raise HTTPException(404, "Player not found")
        old_team = p.team_tricode
        for c in p.contracts:
            if c.is_active:
                c.is_active = False
        p.team_tricode = None
        p.is_free_agent = True
        p.fa_type = "UFA"
        db.commit()
        return {"ok": True, "player": p.name, "released_from": old_team}
    finally:
        db.close()


@router.post("/enforce-roster-max")
def enforce_roster_max():
    """Trim every team to 15 standard + 3 two-way contracts. Excess players go
    to FA. Useful before simming a season or as a manual cleanup."""
    from app.cba.roster import enforce_roster_max as _enforce
    from app.main import SessionLocal
    db = SessionLocal()
    try:
        result = _enforce(db)
        return {"ok": True, **result}
    finally:
        db.close()


@router.post("/renounce-hold/{hold_id}")
def renounce_hold(hold_id: int, db: Session = Depends(get_db)):
    """Renounce a cap hold (and the implicit Bird rights to re-sign that player)."""
    h = db.get(CapHold, hold_id)
    if not h:
        raise HTTPException(404, "Cap hold not found")
    if h.renounced:
        return {"ok": True, "already_renounced": True}
    h.renounced = True
    db.commit()
    p = db.get(Player, h.player_id)
    return {"ok": True, "player": p.name if p else None, "amount_cleared": h.amount}
