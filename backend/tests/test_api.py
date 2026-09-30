"""End-to-end: seed synthetic data, train all models, exercise the REST API."""

import pytest
from fastapi.testclient import TestClient

from nexuspulse.api import app
from nexuspulse.db import SessionLocal, init_db
from nexuspulse.ingest import seed_synthetic
from nexuspulse.models.registry import train_all


@pytest.fixture(scope="module")
def client():
    init_db()
    with SessionLocal() as session:
        seed_synthetic(session, 60)
        train_all(session)
    with TestClient(app) as c:
        yield c


def test_health(client):
    body = client.get("/api/health").json()
    assert body["status"] == "ok"
    assert all(body["models"].values())
    assert body["riot_key_configured"] is False


def test_matches_and_overview(client):
    matches = client.get("/api/matches").json()["matches"]
    assert len(matches) == 60
    mid = matches[0]["match_id"]
    ov = client.get(f"/api/analysis/{mid}/overview").json()
    assert len(ov["participants"]) == 10
    assert ov["winner"] in ("blue", "red")


def test_timeline_dynamics_contract(client):
    mid = client.get("/api/matches").json()["matches"][0]["match_id"]
    d = client.get(f"/api/analysis/{mid}/timeline-dynamics").json()
    assert len(d["timeline"]) == d["duration_min"]
    row = d["timeline"][5]
    for key in ("minute", "team_blue_power_index", "team_red_power_index", "win_probability_blue",
                "delta_win_probability", "is_inflection_point", "shap_summary", "state"):
        assert key in row
    assert 0 <= row["win_probability_blue"] <= 1
    assert abs(row["team_blue_power_index"] + row["team_red_power_index"] - 100) < 0.2
    assert len(d["player_stability"]) == 10 and len(d["player_radar"]) == 10
    for inf in d["inflection_points"]:
        assert abs(inf["delta"]) >= 0.08 and inf["direction"] in ("blue", "red")
        total = sum(f["contribution"] for f in inf["top_features"])
        assert (total > 0) == (inf["delta"] > 0) or abs(total) < 0.02
    # Cached second call returns the identical payload.
    assert client.get(f"/api/analysis/{mid}/timeline-dynamics").json() == d


def test_collect_requires_key(client):
    assert client.post("/api/collect-match", json={"match_id": "EUW1_123456"}).status_code == 503


def test_unknown_match_404(client):
    assert client.get("/api/analysis/EUW1_999999/overview").status_code == 404
