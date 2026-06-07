"""Admin / lifecycle endpoints: reset, renounce cap holds."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.schema import CapHold, Player

router = APIRouter(prefix="/api/admin", tags=["admin"])


def get_db():
    from app.main import SessionLocal
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.post("/reset")
def reset_game():
    """Wipe all data and re-run the full seed in-place (does NOT drop the file
    so the running server keeps its connection)."""
    from app.db.seed import main as seed_main
    from app.main import engine
    seed_main(engine=engine)
    return {"ok": True, "message": "Game reset to 2026-27 offseason."}


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
