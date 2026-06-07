from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.schema import DraftPick

router = APIRouter(prefix="/api/draft", tags=["draft"])


def get_db():
    from app.main import SessionLocal
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.get("/{year}/order")
def draft_order(year: int, db: Session = Depends(get_db)):
    picks = (
        db.query(DraftPick)
        .filter(DraftPick.season_year == year)
        .order_by(DraftPick.round, DraftPick.pick_number)
        .all()
    )
    return [
        {
            "id": p.id,
            "pick_number": p.pick_number,
            "round": p.round,
            "owner": p.owner_tricode,
            "original": p.original_team_tricode,
            "status": p.status.value if hasattr(p.status, "value") else p.status,
            "is_swap": p.is_swap,
            "protection": p.protection_text,
            "notes": p.notes,
        }
        for p in picks
    ]


@router.get("/team/{tricode}/arsenal")
def team_arsenal(tricode: str, db: Session = Depends(get_db)):
    tricode = tricode.upper()
    picks = (
        db.query(DraftPick)
        .filter(DraftPick.owner_tricode == tricode)
        .order_by(DraftPick.season_year, DraftPick.round, DraftPick.pick_number)
        .all()
    )
    return {
        "team": tricode,
        "picks": [
            {
                "year": p.season_year,
                "round": p.round,
                "pick_number": p.pick_number,
                "original": p.original_team_tricode,
                "is_swap": p.is_swap,
                "protection": p.protection_text,
            }
            for p in picks
        ],
    }
