"""Sanity checks on the real corpus: remakes, early surrenders, one match's win-prob curve."""

import json
import sys
from pathlib import Path

from nexuspulse.db import SessionLocal, iter_matches

data = json.loads((Path(__file__).resolve().parent.parent / "data" / "eval_riot.json").read_text("utf-8"))
with SessionLocal() as s:
    rows = list(iter_matches(s, "riot"))
    durs = [r.duration_s for r in rows]
    ends = {}
    for r in rows:
        info = r.match_dict()["info"]
        p0 = info["participants"][0]
        key = ("remake" if p0.get("gameEndedInEarlySurrender") else
               "surrender" if p0.get("gameEndedInSurrender") else "nexus")
        ends[key] = ends.get(key, 0) + 1
    print("matches", len(rows), "under 5 min", sum(d < 300 for d in durs), "under 16 min", sum(d < 960 for d in durs))
    print("end types", ends)
    patches = {}
    for r in rows:
        v = ".".join(r.game_version.split(".")[:2])
        patches[v] = patches.get(v, 0) + 1
    print("patches", patches)

if sys.argv[1:]:
    from nexuspulse.analysis import timeline_dynamics
    from nexuspulse.models.registry import get_bundle, load_corpus

    bundle = get_bundle()
    with SessionLocal() as s:
        corpus = {p.match_id: p for p in load_corpus(s, "riot")}
    for mid in sys.argv[1:]:
        d = timeline_dynamics(corpus[mid], bundle, 0.08)
        print(mid, "P(blue) by minute:",
              [(r["minute"], round(r["win_probability_blue"], 2), r["state"].get("alive_diff")) for r in d["timeline"]])
