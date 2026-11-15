"""Count cached matches by source and platform prefix."""

import sqlite3
from pathlib import Path

db = Path(__file__).resolve().parent.parent / "data" / "nexuspulse.db"
con = sqlite3.connect(db)
rows = con.execute(
    "SELECT source, substr(match_id, 1, instr(match_id, '_') - 1) AS plat, "
    "count(*), sum(timeline_json IS NOT NULL), avg(duration_s), "
    "sum(winner='blue') FROM matches GROUP BY source, plat"
).fetchall()
for src, plat, n, with_tl, dur, blue in rows:
    print(f"{src:10} {plat:8} n={n:5} with_timeline={with_tl:5} avg_dur={dur/60:.1f}m blue_win={blue/n:.3f}")
print("queues:", con.execute("SELECT queue_id, count(*) FROM matches WHERE source='riot' GROUP BY queue_id").fetchall())
