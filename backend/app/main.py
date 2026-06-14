"""FastAPI entrypoint for the NBA GM game."""
from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.schema import Base


# In production (Render) we want the SQLite file on a writable path. /app/data
# is fine on Render's ephemeral disk — state resets on cold starts but that's
# acceptable for a feedback demo. Locally we use backend/data/nbagm.db.
DB_PATH = Path(os.environ.get("DB_PATH", Path(__file__).resolve().parents[1] / "data" / "nbagm.db"))
DB_PATH.parent.mkdir(parents=True, exist_ok=True)
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
    # Always make sure the schema is up to date with the latest model defs.
    Base.metadata.create_all(engine)
    # If the DB is empty (first boot in production, or after a Render cold
    # start), populate it from the seed JSONs so users see a working game on
    # their first request.
    from sqlalchemy import select
    from app.db.schema import Team
    with SessionLocal() as db:
        any_team = db.execute(select(Team).limit(1)).first()
    if not any_team:
        from app.db.seed import main as seed_main
        seed_main(engine=engine)
    yield


app = FastAPI(title="NBA GM", version="0.1.0", lifespan=lifespan)

# Allowed CORS origins: localhost for dev + anything matching the configured
# regex (Vercel preview URLs all match *.vercel.app). Override CORS_ALLOW_ORIGINS
# via env var to lock down to your own production frontend if you prefer.
_default_origins = [
    "http://localhost:3000",
    "http://localhost:3001",
    "http://127.0.0.1:3000",
    "http://127.0.0.1:3001",
]
_env_origins = os.environ.get("CORS_ALLOW_ORIGINS", "").strip()
if _env_origins == "*":
    cors_kwargs = {"allow_origin_regex": ".*"}
elif _env_origins:
    cors_kwargs = {"allow_origins": _default_origins + [o.strip() for o in _env_origins.split(",") if o.strip()]}
else:
    cors_kwargs = {
        "allow_origins": _default_origins,
        "allow_origin_regex": r"https://.*\.vercel\.app",
    }
app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    **cors_kwargs,
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
