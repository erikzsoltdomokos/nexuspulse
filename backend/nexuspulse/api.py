"""FastAPI application exposing ingestion, inference and SHAP explainability."""

from __future__ import annotations

import json
import logging
import threading
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .analysis import overview, timeline_dynamics
from .config import PROJECT_DIR, settings
from .db import AnalysisCache, Match, SessionLocal, get_session, init_db
from .ingest import collect_match, collect_player, seed_synthetic
from .models.registry import get_bundle, train_all
from .riot_client import RiotApiError, RiotClient
from .static_data import load_items
from .timeline import parse_match

log = logging.getLogger("nexuspulse")
_riot = RiotClient()
_bootstrap_state = {"status": "idle", "detail": ""}


def _bootstrap() -> None:
    """First run: seed a synthetic corpus and train, so the dashboard works without a Riot key."""
    if get_bundle() is not None:
        _warm_up()
        _bootstrap_state.update(status="ready", detail="models loaded")
        return
    _bootstrap_state.update(status="training", detail="seeding synthetic corpus and training models")
    try:
        with SessionLocal() as session:
            if session.scalar(select(func.count()).select_from(Match)) < 50:
                seed_synthetic(session, 1000)
            train_all(session)
        _warm_up()
        _bootstrap_state.update(status="ready", detail="models trained")
    except Exception as exc:  # noqa: BLE001
        log.exception("bootstrap failed")
        _bootstrap_state.update(status="error", detail=str(exc))


def _warm_up() -> None:
    """Build the SHAP explainer once so the first dashboard request is fast."""
    bundle = get_bundle()
    if bundle is None:
        return
    import pandas as pd

    from .timeline import WIN_FEATURES

    bundle.win_probability.explain(pd.DataFrame([[0.0] * len(WIN_FEATURES)], columns=WIN_FEATURES))


@asynccontextmanager
async def lifespan(_: FastAPI):
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    init_db()
    if settings.auto_bootstrap:
        threading.Thread(target=_bootstrap, daemon=True).start()
    yield


app = FastAPI(title="NexusPulse", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


class CollectMatchRequest(BaseModel):
    match_id: str = Field(min_length=6, max_length=40)


class CollectPlayerRequest(BaseModel):
    game_name: str = Field(min_length=1, max_length=64)
    tag_line: str = Field(min_length=1, max_length=16)
    count: int = Field(default=10, ge=1, le=50)


def _load_parsed(session: Session, match_id: str):
    row = session.get(Match, match_id.upper())
    if row is None or not row.timeline_json:
        raise HTTPException(404, f"match {match_id} not in cache; POST /api/collect-match first")
    return parse_match(row.match_dict(), row.timeline_dict(), load_items(row.game_version))


@app.get("/api/health")
def health():
    bundle = get_bundle()
    return {
        "status": "ok",
        "models": {"win_probability": bundle is not None, "power_scaling": bundle is not None,
                   "tilt": bundle is not None},
        "riot_key_configured": _riot.configured,
        "bootstrap": _bootstrap_state,
        "model_manifest": bundle.manifest if bundle else None,
    }


@app.get("/api/matches")
def list_matches(session: Session = Depends(get_session), limit: int = Query(200, ge=1, le=2000),
                 source: str | None = Query(None, pattern="^(riot|synthetic)$")):
    stmt = select(Match).where(Match.timeline_json.is_not(None))
    if source:
        stmt = stmt.where(Match.source == source)
    # Real matches first, newest first.
    stmt = stmt.order_by(Match.source.asc(), Match.game_creation.desc()).limit(limit)
    return {"matches": [
        {"match_id": m.match_id, "game_creation": m.game_creation, "duration_min": round(m.duration_s / 60),
         "winner": m.winner, "source": m.source}
        for m in session.scalars(stmt)
    ]}


@app.post("/api/collect-match")
def api_collect_match(req: CollectMatchRequest, session: Session = Depends(get_session)):
    if not _riot.configured:
        raise HTTPException(503, "RIOT_API_KEY is not configured on the server")
    return collect_match(session, _riot, req.match_id)


@app.post("/api/collect-player")
def api_collect_player(req: CollectPlayerRequest, session: Session = Depends(get_session)):
    if not _riot.configured:
        raise HTTPException(503, "RIOT_API_KEY is not configured on the server")
    try:
        return collect_player(session, _riot, req.game_name, req.tag_line, req.count)
    except RiotApiError as exc:
        raise HTTPException(502 if exc.status >= 500 or exc.status == 0 else 400, str(exc)) from exc


@app.get("/api/analysis/{match_id}/overview")
def api_overview(match_id: str, session: Session = Depends(get_session)):
    return overview(_load_parsed(session, match_id))


@app.get("/api/analysis/{match_id}/timeline-dynamics")
def api_timeline_dynamics(
    match_id: str,
    delta: float | None = Query(None, ge=0.01, le=0.5, description="inflection threshold |dP(win)|"),
    session: Session = Depends(get_session),
):
    bundle = get_bundle()
    if bundle is None:
        raise HTTPException(503, f"models not ready ({_bootstrap_state['status']}): {_bootstrap_state['detail']}")
    delta = delta or settings.inflection_delta
    cache_key = f"{bundle.version}:{delta:.3f}"
    cached = session.get(AnalysisCache, (match_id.upper(), cache_key))
    if cached is not None:
        return json.loads(cached.payload)
    payload = timeline_dynamics(_load_parsed(session, match_id), bundle, delta)
    session.merge(AnalysisCache(match_id=match_id.upper(), model_version=cache_key,
                                payload=json.dumps(payload, separators=(",", ":"))))
    session.commit()
    return payload


# Serve the built dashboard (frontend/dist) from the same origin when present.
_dist = PROJECT_DIR / "frontend" / "dist"
if _dist.is_dir():
    app.mount("/", StaticFiles(directory=_dist, html=True), name="dashboard")
