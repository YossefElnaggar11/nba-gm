"""Recent transactions endpoint — used by the undo UI to find what to revert."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.schema import Transaction

router = APIRouter(prefix="/api/transactions", tags=["transactions"])


def get_db():
    from app.main import SessionLocal
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.get("")
def list_recent(limit: int = 20, team: str | None = None, db: Session = Depends(get_db)):
    q = db.query(Transaction).order_by(Transaction.occurred_at.desc())
    if team:
        team = team.upper()
        # Filter by mention of team in payload or description (simple)
        rows = []
        for t in q.limit(limit * 3).all():
            payload_str = str(t.payload or "")
            if team in (t.description or "") or team in payload_str:
                rows.append(t)
                if len(rows) >= limit:
                    break
    else:
        rows = q.limit(limit).all()
    return [
        {
            "id": t.id,
            "occurred_at": t.occurred_at.isoformat() if t.occurred_at else None,
            "type": t.type.value if hasattr(t.type, "value") else t.type,
            "description": t.description,
            "payload": t.payload,
            "is_user_action": t.is_user_action,
        }
        for t in rows
    ]
