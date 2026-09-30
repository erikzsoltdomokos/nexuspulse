"""Ingestion: Riot API -> local cache, apex crawler for training data, synthetic seeding."""

from __future__ import annotations

import logging
import re
from collections import deque

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .db import Match, upsert_match
from .riot_client import RiotApiError, RiotClient
from .synthetic import generate_match

log = logging.getLogger(__name__)
MATCH_ID_RE = re.compile(r"^[A-Z0-9]{2,5}_\d{5,15}$")


def collect_match(session: Session, client: RiotClient, match_id: str, force: bool = False) -> dict:
    match_id = match_id.strip().upper()
    if not MATCH_ID_RE.match(match_id):
        return {"match_id": match_id, "state": "error", "detail": "invalid match id (expected e.g. EUW1_1234567890)"}
    existing = session.get(Match, match_id)
    if existing is not None and existing.timeline_json and not force:
        return {"match_id": match_id, "state": "cached", "detail": "already in local cache"}
    try:
        match = client.get_match(match_id)
        timeline = client.get_timeline(match_id)
    except RiotApiError as exc:
        return {"match_id": match_id, "state": "error", "detail": str(exc)}
    upsert_match(session, match, timeline, source="riot")
    return {"match_id": match_id, "state": "ingested", "detail": "match and timeline cached"}


def collect_player(session: Session, client: RiotClient, game_name: str, tag_line: str,
                   count: int = 10, queue: int | None = 420) -> dict:
    account = client.get_account_by_riot_id(game_name, tag_line)
    puuid = account["puuid"]
    ids = client.get_match_ids(puuid, count=count, queue=queue)
    results = [collect_match(session, client, mid) for mid in ids]
    return {"puuid": puuid, "results": results}


def crawl(session: Session, client: RiotClient, max_matches: int, tier: str = "challenger",
          per_player: int = 20, seed_puuids: list[str] | None = None) -> int:
    """Snowball crawl from apex-league players (high-tier ranked solo queue) until max_matches."""
    queue: deque[str] = deque(seed_puuids or [])
    if not queue:
        league = client.get_apex_league(tier)
        queue.extend(e["puuid"] for e in league.get("entries", []) if e.get("puuid"))
    seen_players: set[str] = set()
    existing = set(session.scalars(select(Match.match_id)))
    added = 0
    while queue and added < max_matches:
        puuid = queue.popleft()
        if puuid in seen_players:
            continue
        seen_players.add(puuid)
        try:
            ids = client.get_match_ids(puuid, count=per_player, queue=420)
        except RiotApiError as exc:
            log.warning("match list failed for %s: %s", puuid[:8], exc)
            continue
        for mid in ids:
            if mid in existing or added >= max_matches:
                continue
            res = collect_match(session, client, mid)
            existing.add(mid)
            if res["state"] == "ingested":
                added += 1
                log.info("crawl %d/%d %s", added, max_matches, mid)
                row = session.get(Match, mid)
                if row is not None and not seed_puuids and tier in ("challenger", "grandmaster", "master"):
                    queue.extend(row.match_dict()["metadata"]["participants"])
    return added


def seed_synthetic(session: Session, n: int, seed: int = 42) -> int:
    """Append n synthetic matches (ids continue after the existing synthetic ones)."""
    start = session.scalar(select(func.count()).select_from(Match).where(Match.source == "synthetic")) or 0
    for i in range(start, start + n):
        match, timeline = generate_match(seed + i, index=i)
        upsert_match(session, match, timeline, source="synthetic")
    return n
