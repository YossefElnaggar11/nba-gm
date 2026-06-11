"""FastAPI entrypoint for the NBA GM game."""
from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.schema import Base


DB_PATH = Path(__file__).resolve().parents[1] / "data" / "nbagm.db"
DB_URL = f"sqlite:///{DB_PATH}"

engine = create_engine(DB_URL, echo=False, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(engine)
    yield


app = FastAPI(title="NBA GM", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:3001", "http://127.0.0.1:3000", "http://127.0.0.1:3001"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
from app.api import teams as teams_router       # noqa: E402
from app.api import draft as draft_router        # noqa: E402
from app.api import cap as cap_router            # noqa: E402
from app.api import free_agents as fa_router     # noqa: E402
from app.api import trades as trades_router      # noqa: E402
from app.api import options as options_router    # noqa: E402
from app.api import signings as signings_router  # noqa: E402
from app.api import draft_picks as draft_picks_router  # noqa: E402
from app.api import sim as sim_router                    # noqa: E402
from app.api import rollover as rollover_router            # noqa: E402
from app.api import admin as admin_router                  # noqa: E402
from app.api import extensions as extensions_router        # noqa: E402
from app.api import stats as stats_router                  # noqa: E402
from app.api import state as state_router                  # noqa: E402
from app.api import leaders as leaders_router              # noqa: E402
from app.api import transactions as transactions_router    # noqa: E402

app.include_router(teams_router.router)
app.include_router(draft_router.router)
app.include_router(cap_router.router)
app.include_router(fa_router.router)
app.include_router(trades_router.router)
app.include_router(options_router.router)
app.include_router(signings_router.router)
app.include_router(draft_picks_router.router)
app.include_router(sim_router.router)
app.include_router(rollover_router.router)
app.include_router(admin_router.router)
app.include_router(extensions_router.router)
app.include_router(stats_router.router)
app.include_router(state_router.router)
app.include_router(leaders_router.router)
app.include_router(transactions_router.router)


@app.get("/")
def root():
    return {"app": "NBA GM", "version": "0.1.0", "current_season": "2026-27"}


@app.get("/health")
def health():
    return {"status": "ok"}
