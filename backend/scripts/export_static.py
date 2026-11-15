"""Precompute the JSON the dashboard needs, for the static GitHub Pages demo.

Usage (from backend/):
    .\\.venv\\Scripts\\python.exe scripts\\export_static.py --out ..\\frontend\\dist-static

Selects the author's games (Riot ID Luda1060#ZSID) plus the most interesting other real
games from data/eval_riot.json (biggest comebacks / most inflection points), then calls the
real FastAPI endpoints in-process and writes each response to a file that mirrors its URL:
    <out>/api/health.json
    <out>/api/matches.json                        (only the exported matches)
    <out>/api/analysis/<id>/overview.json
    <out>/api/analysis/<id>/timeline-dynamics.json
    <out>/api/analysis/<id>/summary.json
No secrets are exported: the health payload is rebuilt with riot_key_configured=false and the
output is scanned for the Riot key prefix before the script exits.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

os.environ.setdefault("NEXUSPULSE_AUTO_BOOTSTRAP", "0")
BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import select  # noqa: E402

from nexuspulse.api import app  # noqa: E402
from nexuspulse.config import settings  # noqa: E402
from nexuspulse.db import Match, SessionLocal  # noqa: E402

AUTHOR = ("Luda1060", "ZSID")
SHOWCASE = ["EUN1_4025052100", "EUW1_8040176757"]
ENDPOINTS = ["overview", "timeline-dynamics", "summary"]


def author_matches(session) -> list[str]:
    ids = []
    rows = session.scalars(select(Match).where(Match.source == "riot", Match.timeline_json.is_not(None),
                                               Match.match_json.contains(AUTHOR[0])))
    for m in rows:
        parts = m.match_dict()["info"]["participants"]
        if any(p.get("riotIdGameName") == AUTHOR[0] and (p.get("riotIdTagline") or "").upper() == AUTHOR[1]
               for p in parts):
            ids.append(m.match_id)
    return ids


def interesting_matches(n: int, exclude: set[str]) -> list[str]:
    """Rank by comeback size (1 - winner's minimum P(win)) plus number of inflection points."""
    evals = json.loads((BACKEND / "data" / "eval_riot.json").read_text(encoding="utf-8"))["matches"]
    cands = [m for m in evals if m["match_id"] not in exclude and not m.get("user_game") and m["duration"] >= 20]
    cands.sort(key=lambda m: -((1 - m["winner_min_wp"]) * 2 + m["n_inflections"] / 10))
    return [m["match_id"] for m in cands[:n]]


def write(out: Path, rel: str, payload) -> int:
    path = out / "api" / f"{rel}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    path.write_text(data, encoding="utf-8")
    return len(data.encode("utf-8"))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=BACKEND.parent / "frontend" / "dist-static")
    ap.add_argument("--extra", type=int, default=25, help="number of non-author interesting matches")
    args = ap.parse_args()
    out: Path = args.out.resolve()

    with SessionLocal() as session:
        mine = author_matches(session)
        ids = list(dict.fromkeys(SHOWCASE + mine))
        ids += interesting_matches(args.extra, set(ids))
        rows = {m.match_id: m for m in session.scalars(select(Match).where(Match.match_id.in_(ids)))}
    ids = [i for i in ids if i in rows]

    total = 0
    exported = []
    with TestClient(app) as client:
        health = client.get("/api/health").json()
        health["riot_key_configured"] = False
        health["bootstrap"] = {"status": "ready", "detail": "static export"}
        total += write(out, "health", health)
        for mid in ids:
            payloads = {}
            for ep in ENDPOINTS:
                r = client.get(f"/api/analysis/{mid}/{ep}")
                if r.status_code != 200:
                    print(f"skip {mid}: {ep} -> {r.status_code}", flush=True)
                    break
                payloads[ep] = r.json()
            else:
                for ep, payload in payloads.items():
                    total += write(out, f"analysis/{mid}/{ep}", payload)
                exported.append(mid)
                print(f"exported {mid}", flush=True)
    matches = [{"match_id": m.match_id, "game_creation": m.game_creation, "duration_min": round(m.duration_s / 60),
                "winner": m.winner, "source": m.source} for m in (rows[i] for i in exported)]
    total += write(out, "matches", {"matches": matches})

    key = settings.riot_api_key
    for f in (out / "api").rglob("*.json"):
        text = f.read_text(encoding="utf-8")
        if "RGAPI-" in text or (key and key in text):
            raise SystemExit(f"refusing to publish: secret-looking content in {f}")
    print(f"{len(exported)} matches ({len(mine)} by {AUTHOR[0]}#{AUTHOR[1]}), {total / 1e6:.1f} MB -> {out / 'api'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
