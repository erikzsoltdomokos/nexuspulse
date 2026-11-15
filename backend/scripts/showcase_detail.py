"""Print showcase details from data/eval_riot.json plus per-match context from the DB."""

import json
import sys
from pathlib import Path

from nexuspulse.db import SessionLocal
from nexuspulse.models.registry import load_corpus

data = json.loads((Path(__file__).resolve().parent.parent / "data" / "eval_riot.json").read_text("utf-8"))
recs = {r["match_id"]: r for r in data["matches"]}
ids = sys.argv[1:]
with SessionLocal() as s:
    corpus = {p.match_id: p for p in load_corpus(s, "riot")}

print("user games: id dur winner side champ result n_infl n_anom user_anoms winner_min_wp")
for r in sorted((r for r in recs.values() if r["user_game"]), key=lambda r: r["match_id"]):
    pm = corpus[r["match_id"]]
    me = next(p for p in pm.participants if p["riot_id"].lower() == "luda1060#zsid")
    mine = [a for a in r["anomalies"] if a["champion"] == me["champion"]]
    print(r["match_id"], r["duration"], r["winner"], me["team"], me["champion"], me["role"],
          "WIN" if me["team"] == r["winner"] else "LOSS", r["n_infl"] if "n_infl" in r else r["n_inflections"],
          r["n_anomalies"], [(a["anomaly_type"], a["severity"], a["minute"]) for a in mine], r["winner_min_wp"])

for mid in ids:
    r = recs[mid]
    pm = corpus[mid]
    print("\n==", mid, r["duration"], "winner", r["winner"], "winner_min_wp", r["winner_min_wp"])
    print("  players:", [(p["team"], p["champion"], p["role"]) for p in pm.participants])
    big = sorted(r["inflections"], key=lambda i: -abs(i[1]))[:5]
    print("  biggest inflections:", big)
    for a in r["anomalies"]:
        print("  tilt:", a["champion"], a["anomaly_type"], a["severity"], a["minute"], "|", a["description"][:160])

print("\nwinner_min_wp distribution (EUW1):",
      sorted(r["winner_min_wp"] for r in recs.values() if r["match_id"].startswith("EUW1"))[:8])
