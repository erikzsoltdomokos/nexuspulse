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


def test_summary_contract(client):
    from nexuspulse.summary import WEIGHTS

    assert abs(sum(WEIGHTS.values()) - 1.0) < 1e-9
    for m in client.get("/api/matches").json()["matches"][:8]:
        mid = m["match_id"]
        s = client.get(f"/api/analysis/{mid}/summary").json()
        d = client.get(f"/api/analysis/{mid}/timeline-dynamics").json()
        winner = s["outcome"]["winner"]
        assert winner == m["winner"] and s["outcome"]["loser"] != winner
        p_w = {r["minute"]: (r["win_probability_blue"] if winner == "blue" else 1 - r["win_probability_blue"])
               for r in d["timeline"]}
        dm = s["decisive_moment"]
        swings = [r["delta_win_probability"] * (1 if winner == "blue" else -1) for r in d["timeline"]]
        assert dm["delta"] == pytest.approx(max(swings), abs=1e-4)
        for f in dm["drivers"]:
            assert f["contribution"] > 0
        pnr = s["point_of_no_return"]
        if pnr:
            assert all(p >= 0.5 for minute, p in p_w.items() if minute >= pnr["minute"])
            before = pnr["minute"] - 1
            assert before not in p_w or p_w[before] < 0.5
        lp = s["loser_peak"]
        assert lp["p"] == pytest.approx(max(1 - p for p in p_w.values()), abs=1e-4)
        assert lp["could_have_won"] == (lp["p"] >= 0.6)
        if s["throw_window"]:
            tw = s["throw_window"]
            assert tw["start"] == lp["minute"] and tw["start"] < tw["end"]
            assert all(tw["start"] < x["minute"] <= tw["end"] and x["delta"] < 0 for x in tw["drops"])
        assert len(s["players"]) == 10
        assert all(0 <= p["rating"] <= 100 for p in s["players"])
        mvp = next(p for p in s["players"] if p["participant_id"] == s["mvp"])
        assert mvp["team"] == winner
        assert mvp["rating"] == max(p["rating"] for p in s["players"] if p["team"] == winner)
        shpb = s["should_have_performed_better"]
        worst = min((p for p in s["players"] if p["team"] != winner), key=lambda p: p["rating"])
        assert shpb["rating"] == worst["rating"] and shpb["reasons"]
        # Deterministic.
        assert client.get(f"/api/analysis/{mid}/summary").json() == s


def test_rating_formula():
    from nexuspulse.summary import WEIGHTS

    comp = {"kda": 1.0, "economy": 0.5, "stability": 0.8, "composure": 1.0, "lane": 0.5}
    assert 100 * sum(WEIGHTS[k] * v for k, v in comp.items()) == pytest.approx(25 + 12.5 + 12 + 15 + 10)
