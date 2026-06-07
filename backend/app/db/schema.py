"""SQLAlchemy ORM models for the NBA GM game.

Design principles:
  - Teams identified by tricode (BOS, LAL, etc.) — canonical key everywhere.
  - Contracts are immutable rows tied to (player, team, signed_date).
  - Player options / team options modelled as flags on SeasonSalary entries.
  - DraftPicks are first-class entities; ownership chains via trades.
  - GameState lets us snapshot/save and rewind.
"""
from __future__ import annotations

from datetime import date, datetime
from enum import Enum

from sqlalchemy import (
    Boolean, Date, DateTime, Enum as SAEnum, ForeignKey, Integer, String, Text, JSON
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# Reference / static
# ---------------------------------------------------------------------------


class Team(Base):
    __tablename__ = "teams"
    tricode: Mapped[str] = mapped_column(String(3), primary_key=True)
    full_name: Mapped[str] = mapped_column(String(64))
    city: Mapped[str] = mapped_column(String(64))
    nickname: Mapped[str] = mapped_column(String(64))
    conference: Mapped[str] = mapped_column(String(8))   # East | West
    division: Mapped[str] = mapped_column(String(16))
    primary_color: Mapped[str] = mapped_column(String(8))
    secondary_color: Mapped[str] = mapped_column(String(8))

    players: Mapped[list["Player"]] = relationship(back_populates="team")
    owned_picks: Mapped[list["DraftPick"]] = relationship(
        foreign_keys="DraftPick.owner_tricode", back_populates="owner",
    )


# ---------------------------------------------------------------------------
# Players & contracts
# ---------------------------------------------------------------------------


class OptionType(str, Enum):
    NONE = "NONE"
    PLAYER = "PLAYER"
    TEAM = "TEAM"
    EARLY_TERMINATION = "EARLY_TERMINATION"  # ETO — rare


class Player(Base):
    __tablename__ = "players"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    bbr_id: Mapped[str | None] = mapped_column(String(32), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(96), index=True)
    age: Mapped[int | None] = mapped_column(Integer)
    position: Mapped[str | None] = mapped_column(String(8))     # PG/SG/SF/PF/C
    height_in: Mapped[int | None] = mapped_column(Integer)
    weight_lb: Mapped[int | None] = mapped_column(Integer)
    years_of_service: Mapped[int] = mapped_column(Integer, default=0)
    team_tricode: Mapped[str | None] = mapped_column(ForeignKey("teams.tricode"), index=True)
    # Rating snapshot for sim
    overall: Mapped[int | None] = mapped_column(Integer)        # 40..99 a la 2K
    potential: Mapped[int | None] = mapped_column(Integer)
    # Baseline stats (from BBR scrape — used as sim input)
    baseline_ppg: Mapped[float | None] = mapped_column()
    baseline_rpg: Mapped[float | None] = mapped_column()
    baseline_apg: Mapped[float | None] = mapped_column()
    baseline_spg: Mapped[float | None] = mapped_column()
    baseline_bpg: Mapped[float | None] = mapped_column()
    baseline_mpg: Mapped[float | None] = mapped_column()
    # Status
    is_free_agent: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    fa_type: Mapped[str | None] = mapped_column(String(16))      # UFA | RFA | None
    # Bird rights tracker — count of years on current team without interruption
    bird_years_with_team: Mapped[int] = mapped_column(Integer, default=0)

    team: Mapped["Team | None"] = relationship(back_populates="players")
    contracts: Mapped[list["Contract"]] = relationship(back_populates="player", cascade="all, delete-orphan")


class Contract(Base):
    __tablename__ = "contracts"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id"), index=True)
    team_tricode: Mapped[str] = mapped_column(ForeignKey("teams.tricode"), index=True)
    signed_date: Mapped[date] = mapped_column(Date)
    signed_using: Mapped[str | None] = mapped_column(String(32))
    # One of: BIRD, EARLY_BIRD, NON_BIRD, MIN, MLE_NON_TAX, MLE_TAX, MLE_ROOM, BAE,
    #         ROOKIE_SCALE, MAX_BIRD, MAX_NON_BIRD, EXTENSION, S_AND_T, TRADE_ACQUIRED
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    is_two_way: Mapped[bool] = mapped_column(Boolean, default=False)
    no_trade_clause: Mapped[bool] = mapped_column(Boolean, default=False)
    poison_pill: Mapped[bool] = mapped_column(Boolean, default=False)
    notes: Mapped[str | None] = mapped_column(Text)

    player: Mapped[Player] = relationship(back_populates="contracts")
    seasons: Mapped[list["ContractSeason"]] = relationship(
        back_populates="contract", cascade="all, delete-orphan",
        order_by="ContractSeason.season",
    )


class ContractSeason(Base):
    __tablename__ = "contract_seasons"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    contract_id: Mapped[int] = mapped_column(ForeignKey("contracts.id"), index=True)
    season: Mapped[str] = mapped_column(String(7), index=True)     # "2026-27"
    salary: Mapped[int] = mapped_column(Integer)                   # dollars
    option_type: Mapped[OptionType] = mapped_column(SAEnum(OptionType), default=OptionType.NONE)
    guaranteed: Mapped[bool] = mapped_column(Boolean, default=True)
    partial_guarantee: Mapped[int | None] = mapped_column(Integer)  # dollars if partial
    decision_made: Mapped[bool] = mapped_column(Boolean, default=False)  # has option been picked up/declined?

    contract: Mapped[Contract] = relationship(back_populates="seasons")


# ---------------------------------------------------------------------------
# Draft picks (the "arsenal" — owned/owed/swap rights/protections)
# ---------------------------------------------------------------------------


class PickStatus(str, Enum):
    OWNED = "OWNED"
    CONVEYED = "CONVEYED"            # actually used in a draft
    LAPSED_TO_SECONDS = "LAPSED_TO_SECONDS"  # protection failed enough times
    LOTTERY_PENDING = "LOTTERY_PENDING"      # not yet determined


class DraftPick(Base):
    __tablename__ = "draft_picks"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    season_year: Mapped[int] = mapped_column(Integer, index=True)   # e.g. 2026
    round: Mapped[int] = mapped_column(Integer)                     # 1 or 2
    original_team_tricode: Mapped[str] = mapped_column(ForeignKey("teams.tricode"), index=True)
    owner_tricode: Mapped[str] = mapped_column(ForeignKey("teams.tricode"), index=True)
    # Realised pick position (set after lottery / regular-season finish)
    pick_number: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[PickStatus] = mapped_column(SAEnum(PickStatus), default=PickStatus.OWNED)
    # Protection: e.g. "top-4 protected; if not conveyed in 2026, becomes 2027 top-4, then unprotected 2028"
    protection_text: Mapped[str | None] = mapped_column(Text)
    # Machine-readable protection (jsonb): {"top_protected": 4, "lapse_to": "2027",
    #   "alternate_compensation": "2 second-rounders", ...}
    protection_json: Mapped[dict | None] = mapped_column(JSON)
    # Swap rights — if this is a SWAP, who can swap with whom
    is_swap: Mapped[bool] = mapped_column(Boolean, default=False)
    swap_with_team: Mapped[str | None] = mapped_column(ForeignKey("teams.tricode"))
    notes: Mapped[str | None] = mapped_column(Text)

    original_team: Mapped[Team] = relationship(foreign_keys=[original_team_tricode])
    owner: Mapped[Team] = relationship(foreign_keys=[owner_tricode], back_populates="owned_picks")


# ---------------------------------------------------------------------------
# Trades, signings, transactions
# ---------------------------------------------------------------------------


class TransactionType(str, Enum):
    TRADE = "TRADE"
    SIGN_FA = "SIGN_FA"
    RESIGN = "RESIGN"
    EXTEND = "EXTEND"
    WAIVE = "WAIVE"
    DRAFT_PICK = "DRAFT_PICK"
    PICK_OPTION = "PICK_OPTION"        # exercised / declined option
    BUYOUT = "BUYOUT"
    TRADE_EXCEPTION_USED = "TRADE_EXCEPTION_USED"


class Transaction(Base):
    __tablename__ = "transactions"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    type: Mapped[TransactionType] = mapped_column(SAEnum(TransactionType), index=True)
    # JSON: full ledger of assets moved (player_ids, pick_ids, cash, exceptions)
    payload: Mapped[dict] = mapped_column(JSON)
    description: Mapped[str] = mapped_column(Text)
    is_user_action: Mapped[bool] = mapped_column(Boolean, default=False)


# ---------------------------------------------------------------------------
# Season / sim state
# ---------------------------------------------------------------------------


class Season(Base):
    __tablename__ = "seasons"
    season: Mapped[str] = mapped_column(String(7), primary_key=True)  # "2026-27"
    simulated: Mapped[bool] = mapped_column(Boolean, default=False)
    champion_tricode: Mapped[str | None] = mapped_column(ForeignKey("teams.tricode"))
    mvp_player_id: Mapped[int | None] = mapped_column(ForeignKey("players.id"))
    rookie_of_year_player_id: Mapped[int | None] = mapped_column(ForeignKey("players.id"))
    mvp_name: Mapped[str | None] = mapped_column(String(96))
    mvp_team: Mapped[str | None] = mapped_column(String(3))
    finals_mvp_name: Mapped[str | None] = mapped_column(String(96))
    finals_mvp_team: Mapped[str | None] = mapped_column(String(3))
    dpoy_name: Mapped[str | None] = mapped_column(String(96))
    dpoy_team: Mapped[str | None] = mapped_column(String(3))
    roy_name: Mapped[str | None] = mapped_column(String(96))
    roy_team: Mapped[str | None] = mapped_column(String(3))
    all_nba_json: Mapped[dict | None] = mapped_column(JSON)   # {"first": [...], "second": [...], "third": [...]}


class TeamRecord(Base):
    __tablename__ = "team_records"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    season: Mapped[str] = mapped_column(ForeignKey("seasons.season"), index=True)
    team_tricode: Mapped[str] = mapped_column(ForeignKey("teams.tricode"), index=True)
    wins: Mapped[int] = mapped_column(Integer, default=0)
    losses: Mapped[int] = mapped_column(Integer, default=0)
    seed: Mapped[int | None] = mapped_column(Integer)
    made_playoffs: Mapped[bool] = mapped_column(Boolean, default=False)
    playoff_exit_round: Mapped[str | None] = mapped_column(String(16))  # R1, R2, CONF, FINALS, CHAMP


# ---------------------------------------------------------------------------
# Save state
# ---------------------------------------------------------------------------


class GameSave(Base):
    __tablename__ = "game_saves"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(64))
    user_team_tricode: Mapped[str] = mapped_column(ForeignKey("teams.tricode"))
    current_season: Mapped[str] = mapped_column(String(7))    # e.g. "2026-27"
    current_phase: Mapped[str] = mapped_column(String(32))    # OFFSEASON_PRE_DRAFT, DRAFT, FA_OPEN, REGULAR_SEASON, PLAYOFFS
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# ---------------------------------------------------------------------------
# Draft prospects
# ---------------------------------------------------------------------------


class Prospect(Base):
    __tablename__ = "prospects"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    draft_year: Mapped[int] = mapped_column(Integer, index=True)
    rank: Mapped[int] = mapped_column(Integer)              # mock-draft rank
    name: Mapped[str] = mapped_column(String(96))
    position: Mapped[str | None] = mapped_column(String(8))
    college: Mapped[str | None] = mapped_column(String(96))
    age: Mapped[int | None] = mapped_column(Integer)
    overall: Mapped[int | None] = mapped_column(Integer)
    potential: Mapped[int | None] = mapped_column(Integer)
    drafted_to_team: Mapped[str | None] = mapped_column(ForeignKey("teams.tricode"))
    drafted_at_pick: Mapped[int | None] = mapped_column(Integer)
    created_player_id: Mapped[int | None] = mapped_column(ForeignKey("players.id"))


# ---------------------------------------------------------------------------
# Cap holds: charges against a team's books for own FAs (Bird rights placeholder)
# Set during seed for any player who was on team last year but not under contract
# this year. Renouncing removes the hold AND the Bird rights to re-sign.
# ---------------------------------------------------------------------------


class CapHold(Base):
    __tablename__ = "cap_holds"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id"), index=True)
    team_tricode: Mapped[str] = mapped_column(ForeignKey("teams.tricode"), index=True)
    season: Mapped[str] = mapped_column(String(7), index=True)   # e.g. "2026-27"
    amount: Mapped[int] = mapped_column(Integer)                  # dollars
    renounced: Mapped[bool] = mapped_column(Boolean, default=False)
    notes: Mapped[str | None] = mapped_column(Text)


# ---------------------------------------------------------------------------
# Per-player season stats (populated by the sim engine)
# ---------------------------------------------------------------------------


class PlayerSeasonStats(Base):
    __tablename__ = "player_season_stats"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id"), index=True)
    season: Mapped[str] = mapped_column(String(7), index=True)
    team_tricode: Mapped[str] = mapped_column(ForeignKey("teams.tricode"), index=True)
    games_played: Mapped[int] = mapped_column(Integer, default=0)
    games_started: Mapped[int] = mapped_column(Integer, default=0)
    mpg: Mapped[float] = mapped_column(default=0.0)
    ppg: Mapped[float] = mapped_column(default=0.0)
    rpg: Mapped[float] = mapped_column(default=0.0)
    apg: Mapped[float] = mapped_column(default=0.0)
    spg: Mapped[float] = mapped_column(default=0.0)
    bpg: Mapped[float] = mapped_column(default=0.0)
    fg_pct: Mapped[float] = mapped_column(default=0.0)
    three_pct: Mapped[float] = mapped_column(default=0.0)
    ft_pct: Mapped[float] = mapped_column(default=0.0)
    is_injured: Mapped[bool] = mapped_column(Boolean, default=False)
