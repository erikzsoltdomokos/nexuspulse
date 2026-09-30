"""Assemble API payloads from a parsed match and the trained model bundle."""

from __future__ import annotations

import numpy as np

from .models.power_scaling import power_windows
from .models.registry import ModelBundle
from .models.tilt import detect_anomalies
from .models.win_probability import attribution_series
from .timeline import ParsedMatch

STATE_FIELDS = [
    "gold_blue", "gold_red", "gold_diff", "xp_diff", "kills_blue", "kills_red", "dragons_blue",
    "dragons_red", "barons_blue", "barons_red", "heralds_blue", "heralds_red", "voidgrubs_blue",
    "voidgrubs_red", "towers_blue", "towers_red", "plates_blue", "plates_red",
    "items_completed_blue", "items_completed_red",
]
PUBLIC_PARTICIPANT_FIELDS = [
    "participant_id", "puuid", "riot_id", "champion", "team", "role", "kills", "deaths", "assists",
    "cs", "gold", "damage", "vision_score", "win",
]
CS_REF = {"TOP": 7.5, "JUNGLE": 6.0, "MIDDLE": 8.0, "BOTTOM": 8.5, "UTILITY": 1.5}
VISION_REF = {"UTILITY": 2.5, "JUNGLE": 1.4}


def overview(pm: ParsedMatch) -> dict:
    return {
        "match_id": pm.match_id,
        "duration_min": pm.duration_min,
        "winner": pm.winner,
        "game_version": pm.game_version,
        "queue_id": pm.queue_id,
        "participants": [{k: p[k] for k in PUBLIC_PARTICIPANT_FIELDS} for p in pm.participants],
    }


def _clip100(x: float) -> float:
    return round(float(np.clip(x, 0, 100)), 1)


def _radar(pm: ParsedMatch, stability_mean: dict[int, float]) -> list[dict]:
    out = []
    team_kills = {t: sum(p["kills"] for p in pm.participants if p["team"] == t) or 1 for t in ("blue", "red")}
    team_dmg = {t: sum(p["damage"] for p in pm.participants if p["team"] == t) or 1 for t in ("blue", "red")}
    team_obj = {t: sum(p["damage_to_objectives"] for p in pm.participants if p["team"] == t) or 1
                for t in ("blue", "red")}
    for p in pm.participants:
        minutes = max(1.0, p["duration_min"])
        kp = (p["kills"] + p["assists"]) / team_kills[p["team"]]
        dmg_share = p["damage"] / team_dmg[p["team"]]
        out.append({
            "participant_id": p["participant_id"],
            "metrics": {
                "farming": _clip100(100 * (p["cs"] / minutes) / CS_REF.get(p["role"], 7.0) / 1.3),
                "fighting": _clip100(100 * (0.5 * kp / 0.7 + 0.5 * dmg_share / 0.3)),
                "vision": _clip100(100 * (p["vision_score"] / minutes) / VISION_REF.get(p["role"], 1.0) / 1.3),
                "objectives": _clip100(100 * (p["damage_to_objectives"] / team_obj[p["team"]]) / 0.35),
                "survival": _clip100(100 * (1 - (p["deaths"] / minutes * 10) / 3)),
                "stability": _clip100(stability_mean.get(p["participant_id"], 100.0)),
            },
        })
    return out


def timeline_dynamics(pm: ParsedMatch, bundle: ModelBundle, delta: float) -> dict:
    tm = pm.team_minutes
    series = attribution_series(bundle.win_probability, tm, delta)
    power = bundle.power_scaling.team_index(pm).set_index("minute")
    state_rows = tm.set_index("minute")[STATE_FIELDS]

    timeline = []
    for row in series["rows"]:
        m = row["minute"]
        state = {k: (int(v) if float(v).is_integer() else round(float(v), 3))
                 for k, v in state_rows.loc[m].items()}
        timeline.append({
            "minute": m,
            "team_blue_power_index": float(power.loc[m, "team_blue_power_index"]) if m in power.index else 50.0,
            "team_red_power_index": float(power.loc[m, "team_red_power_index"]) if m in power.index else 50.0,
            **{k: row[k] for k in ("win_probability_blue", "delta_win_probability", "is_inflection_point",
                                    "shap_summary")},
            "state": state,
        })

    scored = bundle.tilt.score_match(pm)
    anomalies = detect_anomalies(pm, scored)
    parts = {p["participant_id"]: p for p in pm.participants}
    stability = []
    stability_mean: dict[int, float] = {}
    for pid, grp in scored.groupby("participant_id"):
        p = parts[pid]
        scores = [{"minute": int(r.minute), "stability": float(r.stability)}
                  for r in grp.sort_values("minute").itertuples()]
        stability_mean[pid] = float(np.mean([s["stability"] for s in scores])) if scores else 100.0
        stability.append({"participant_id": int(pid), "puuid": p["puuid"], "champion": p["champion"],
                          "team": p["team"], "role": p["role"], "scores": scores})

    return {
        "match_id": pm.match_id,
        "duration_min": pm.duration_min,
        "power_windows": power_windows(power.reset_index()),
        "timeline": timeline,
        "inflection_points": series["inflections"],
        "player_anomalies": anomalies,
        "player_stability": stability,
        "player_radar": _radar(pm, stability_mean),
        "model_version": bundle.version,
    }
