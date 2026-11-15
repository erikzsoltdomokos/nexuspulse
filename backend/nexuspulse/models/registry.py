"""Model bundle: train all three layers, persist with joblib, load lazily."""

from __future__ import annotations

import hashlib
import json
import logging
import threading
import time
from dataclasses import dataclass, field

import joblib
from sqlalchemy.orm import Session

from ..config import settings
from ..db import iter_matches
from ..static_data import load_items
from ..timeline import ParsedMatch, parse_match
from .power_scaling import PowerScalingModel
from .tilt import TiltModel
from .win_probability import WinProbabilityModel

log = logging.getLogger(__name__)
BUNDLE_PATH = settings.model_dir / "bundle.joblib"
MANIFEST_PATH = settings.model_dir / "manifest.json"


@dataclass
class ModelBundle:
    win_probability: WinProbabilityModel
    power_scaling: PowerScalingModel
    tilt: TiltModel
    version: str
    manifest: dict = field(default_factory=dict)


MIN_TRAINING_DURATION_S = 300


def is_remake(match: dict) -> bool:
    """Remakes / early surrenders carry no real outcome signal and are label noise for training."""
    info = match.get("info", {})
    if int(info.get("gameDuration", 0)) < MIN_TRAINING_DURATION_S:
        return True
    return any(p.get("gameEndedInEarlySurrender") for p in info.get("participants", []))


def load_corpus(session: Session, source: str | None = None, limit: int | None = None) -> list[ParsedMatch]:
    parsed = []
    skipped_remakes = 0
    for row in iter_matches(session, source):
        try:
            match, timeline = row.match_dict(), row.timeline_dict()
            if is_remake(match):
                skipped_remakes += 1
                continue
            parsed.append(parse_match(match, timeline, load_items(row.game_version)))
        except Exception as exc:  # noqa: BLE001 -- skip malformed matches, keep training
            log.warning("skipping %s: %s", row.match_id, exc)
        if limit and len(parsed) >= limit:
            break
    if skipped_remakes:
        log.info("skipped %d remakes / early surrenders", skipped_remakes)
    return parsed


def train_all(session: Session, source: str | None = None) -> ModelBundle:
    """Train every model. With source=None, Riot matches are used alone once >= 200 exist."""
    if source is None:
        riot = load_corpus(session, "riot")
        parsed = riot if len(riot) >= 200 else load_corpus(session)
        used = "riot" if len(riot) >= 200 else "all"
    else:
        parsed, used = load_corpus(session, source), source
    if len(parsed) < 20:
        raise RuntimeError(f"need at least 20 matches with timelines to train, found {len(parsed)}")
    t0 = time.time()
    win = WinProbabilityModel.train(parsed)
    power = PowerScalingModel.train(parsed)
    tilt = TiltModel.train(parsed)
    trained_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    version = hashlib.sha1(f"{trained_at}-{len(parsed)}".encode()).hexdigest()[:12]
    manifest = {
        "version": version, "trained_at": trained_at, "matches": len(parsed), "corpus": used,
        "seconds": round(time.time() - t0, 1),
        "metrics": {"win_probability": win.metrics, "power_scaling": power.metrics, "tilt": tilt.metrics},
    }
    bundle = ModelBundle(win, power, tilt, version, manifest)
    joblib.dump(bundle, BUNDLE_PATH)
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    _set_cached(bundle)
    log.info("models trained: %s", manifest)
    return bundle


_lock = threading.Lock()
_cached: ModelBundle | None = None


def _set_cached(bundle: ModelBundle | None) -> None:
    global _cached
    with _lock:
        _cached = bundle


def get_bundle() -> ModelBundle | None:
    global _cached
    with _lock:
        if _cached is None and BUNDLE_PATH.is_file():
            try:
                _cached = joblib.load(BUNDLE_PATH)
            except Exception as exc:  # noqa: BLE001
                log.error("failed to load model bundle: %s", exc)
        return _cached
