"""Evaluate the Riot-trained bundle: holdout AUC by minute, tilt rates, showcase candidates.

Writes backend/data/eval_riot.json (gitignored).
"""

import json
from pathlib import Path

import numpy as np
import xgboost as xgb
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import GroupShuffleSplit

from nexuspulse.analysis import timeline_dynamics
from nexuspulse.config import settings
from nexuspulse.db import SessionLocal
from nexuspulse.models.registry import get_bundle, load_corpus
from nexuspulse.models.win_probability import build_dataset
from nexuspulse.timeline import WIN_FEATURES

OUT = Path(__file__).resolve().parent.parent / "data" / "eval_riot.json"
USER = "luda1060#zsid"

bundle = get_bundle()
with SessionLocal() as session:
    corpus = load_corpus(session, "riot")
print("bundle", bundle.version, "corpus", len(corpus))

# Holdout AUC by minute, using the same GroupShuffleSplit as training (seed 7).
model_params = bundle.win_probability.model.get_params()
x, y, groups = build_dataset(corpus)
tr, te = next(GroupShuffleSplit(n_splits=1, test_size=0.2, random_state=7).split(x, y, groups))
hold = xgb.XGBClassifier(**model_params).fit(x.iloc[tr], y[tr])
p = hold.predict_proba(x.iloc[te])[:, 1]
mins = x.iloc[te]["minute"].to_numpy()
auc_by_min = {}
for m in (3, 5, 10, 15, 20, 25, 30):
    mask = mins == m
    if mask.sum() > 20 and len(set(y[te][mask])) > 1:
        auc_by_min[m] = {"auc": round(float(roc_auc_score(y[te][mask], p[mask])), 3), "n": int(mask.sum())}
print("holdout auc by minute", auc_by_min)
imp = dict(sorted(zip(WIN_FEATURES, map(float, bundle.win_probability.model.feature_importances_)),
                  key=lambda kv: -kv[1]))
print("feature importance", {k: round(v, 3) for k, v in imp.items()})

# Per-match dynamics over the whole riot corpus.
records = []
for pm in corpus:
    d = timeline_dynamics(pm, bundle, settings.inflection_delta)
    wp = [r["win_probability_blue"] for r in d["timeline"]]
    winner_blue = pm.winner == "blue"
    # Comeback depth: lowest win probability the eventual winner had after minute 5.
    after5 = [w for r, w in zip(d["timeline"], wp) if r["minute"] >= 5] or wp
    winner_min = min(after5) if winner_blue else min(1 - w for w in after5)
    names = {q["riot_id"].lower() for q in pm.participants}
    records.append({
        "match_id": pm.match_id,
        "duration": round(pm.duration_min, 1),
        "winner": pm.winner,
        "user_game": USER in names,
        "n_inflections": len(d["inflection_points"]),
        "inflections": [(i["minute"], i["delta"], [f["feature"] for f in i["top_features"]])
                        for i in d["inflection_points"]],
        "n_anomalies": len(d["player_anomalies"]),
        "anomalies": [{k: a.get(k) for k in ("champion", "riot_id", "anomaly_type", "severity", "minute",
                                             "start_minute", "description") if k in a}
                      for a in d["player_anomalies"]],
        "winner_min_wp": round(float(winner_min), 3),
    })

n_anom = np.array([r["n_anomalies"] for r in records])
n_infl = np.array([r["n_inflections"] for r in records])
types = {}
for r in records:
    for a in r["anomalies"]:
        types[a.get("anomaly_type")] = types.get(a.get("anomaly_type"), 0) + 1
summary = {
    "auc_by_minute_holdout": auc_by_min,
    "feature_importance": imp,
    "anomalies_per_game_mean": round(float(n_anom.mean()), 2),
    "anomalies_per_game_median": float(np.median(n_anom)),
    "games_with_any_anomaly": round(float((n_anom > 0).mean()), 3),
    "anomaly_types": types,
    "inflections_per_game_mean": round(float(n_infl.mean()), 2),
    "games_with_any_inflection": round(float((n_infl > 0).mean()), 3),
    "comebacks_winner_below_25pct": int(sum(r["winner_min_wp"] < 0.25 for r in records)),
    "user_games": sum(r["user_game"] for r in records),
}
print(json.dumps({k: v for k, v in summary.items() if k != "feature_importance"}, indent=1))

user = sorted([r for r in records if r["user_game"]], key=lambda r: -(r["n_inflections"] + r["n_anomalies"]))
print("\nUSER GAMES (top 5)")
for r in user[:5]:
    print(json.dumps(r)[:900])
comebacks = sorted([r for r in records if not r["user_game"] and r["match_id"].startswith("EUW1")],
                   key=lambda r: r["winner_min_wp"])
print("\nCOMEBACKS (top 5)")
for r in comebacks[:5]:
    print(json.dumps(r)[:900])

OUT.write_text(json.dumps({"summary": summary, "matches": records}, indent=1), encoding="utf-8")
