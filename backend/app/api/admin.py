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
    """Wipe all data and re-run the full seed in-place. Affects the CURRENTLY
    active mode's state only."""
    from app.db.seed import main as seed_main
    from app.main import engine
    seed_main(engine=engine)
    return {"ok": True, "message": f"Game reset (mode={_active_mode})."}


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

    from app.db.seed import main as seed_main
    from app.main import engine

    msg_parts = []

    if target == "offseason":
        seed_main(engine=engine)
        msg_parts.append("fresh sandbox started")
    else:
        if CAREER_BACKUP.exists():
            try:
                engine.dispose()
                shutil.copy2(CAREER_BACKUP, DB_PATH)
                msg_parts.append("career state restored from last save")
            except Exception as e:
                seed_main(engine=engine)
                msg_parts.append(f"career restore failed, started fresh: {e}")
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
