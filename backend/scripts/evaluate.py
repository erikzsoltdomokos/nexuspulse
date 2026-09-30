"""Evaluate trained models on the local corpus: per-minute AUC and sample analyses."""

import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score

from nexuspulse.analysis import timeline_dynamics
from nexuspulse.db import SessionLocal
from nexuspulse.models.registry import get_bundle, load_corpus

bundle = get_bundle()
with SessionLocal() as session:
    corpus = load_corpus(session)

for minute in (5, 10, 15, 20, 25):
    rows = [(p.team_minutes[p.team_minutes.minute == minute], p.winner == "blue")
            for p in corpus if p.duration_min > minute]
    tm = pd.concat([r[0] for r in rows])
    y = [r[1] for r in rows]
    print(minute, "auc", round(roc_auc_score(y, bundle.win_probability.predict(tm)), 3))

counts = []
for i, p in enumerate(corpus[3:40]):
    d = timeline_dynamics(p, bundle, 0.08)
    counts.append(len(d["player_anomalies"]))
    if i < 3:
        print(p.match_id, p.duration_min, p.winner, "wp",
              [x["win_probability_blue"] for x in d["timeline"]][::3])
        print("  windows", d["power_windows"], "infl", [(x["minute"], x["delta"]) for x in d["inflection_points"]])
        for x in d["inflection_points"][:3]:
            print("   ", x["description"])
        for a in d["player_anomalies"][:3]:
            print("   ", a["champion"], a["anomaly_type"], a["severity"], a["description"])
print("anomalies per match", np.mean(counts))
