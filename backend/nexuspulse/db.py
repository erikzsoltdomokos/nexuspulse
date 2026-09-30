"""SQLAlchemy storage: raw match/timeline JSON cache and computed-analysis cache."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Iterator

from sqlalchemy import BigInteger, DateTime, Integer, String, Text, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from .config import settings


class Base(DeclarativeBase):
    pass


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Match(Base):
    __tablename__ = "matches"

    match_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    source: Mapped[str] = mapped_column(String(16), default="riot")  # riot | synthetic
    game_creation: Mapped[int] = mapped_column(BigInteger, default=0)
    duration_s: Mapped[int] = mapped_column(Integer, default=0)
    game_version: Mapped[str] = mapped_column(String(40), default="")
    queue_id: Mapped[int] = mapped_column(Integer, default=0)
    winner: Mapped[str] = mapped_column(String(8), default="")  # blue | red
    match_json: Mapped[str] = mapped_column(Text)
    timeline_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    def match_dict(self) -> dict:
        return json.loads(self.match_json)

    def timeline_dict(self) -> dict | None:
        return json.loads(self.timeline_json) if self.timeline_json else None


class AnalysisCache(Base):
    __tablename__ = "analysis_cache"

    match_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    model_version: Mapped[str] = mapped_column(String(40), primary_key=True)
    payload: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


engine = create_engine(
    settings.db_url,
    connect_args={"check_same_thread": False} if settings.db_url.startswith("sqlite") else {},
)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def init_db() -> None:
    Base.metadata.create_all(engine)


def get_session() -> Iterator[Session]:
    with SessionLocal() as session:
        yield session


def upsert_match(
    session: Session, match: dict, timeline: dict | None, source: str = "riot"
) -> Match:
    """Insert or replace a match + timeline in the cache."""
    info = match["info"]
    match_id = match["metadata"]["matchId"]
    winner = ""
    for team in info.get("teams", []):
        if team.get("win"):
            winner = "blue" if team["teamId"] == 100 else "red"
    row = session.get(Match, match_id) or Match(match_id=match_id)
    row.source = source
    row.game_creation = int(info.get("gameCreation", 0))
    row.duration_s = int(info.get("gameDuration", 0))
    row.game_version = str(info.get("gameVersion", ""))
    row.queue_id = int(info.get("queueId", 0))
    row.winner = winner
    row.match_json = json.dumps(match, separators=(",", ":"))
    row.timeline_json = json.dumps(timeline, separators=(",", ":")) if timeline else None
    session.add(row)
    session.commit()
    return row


def iter_matches(session: Session, source: str | None = None) -> Iterator[Match]:
    stmt = select(Match).where(Match.timeline_json.is_not(None))
    if source:
        stmt = stmt.where(Match.source == source)
    yield from session.scalars(stmt.order_by(Match.game_creation))
