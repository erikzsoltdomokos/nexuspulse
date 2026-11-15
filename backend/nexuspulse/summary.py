"""Match summary: structured, language-neutral story of a match.

Built on top of the ``timeline_dynamics`` payload (so it reuses the cached analysis) plus the
parsed match for per-player data. Every item is a code with numeric/string parameters; the
frontend turns them into Hungarian or English sentences. Everything here is deterministic.

Definitions (P_w(m) = winner's win probability at minute m, P_l = 1 - P_w):

* decisive_moment     -- minute with the largest single-minute increase of P_w.
* point_of_no_return  -- first minute m such that P_w(m') >= 0.5 for every m' >= m.
* loser_peak          -- max P_l and its (earliest) minute; ``could_have_won`` if >= 0.6.
* throw_window        -- loser_peak minute .. point_of_no_return, only when the loser peaked
                         above 50% before the point of no return. ``drops`` are the 3 minutes
                         with the largest P_l decrease inside the window, with SHAP drivers (drops < 5 pp are ignored).
* power_windows       -- each team's theoretical peak window = its power window with the
                         highest mean power index. ``loser_lost_own_window`` is true when the
                         loser's P(win) fell over its own window (sum of P_l deltas < 0).

Player impact rating (0-100)::

    rating = 100 * (0.25 * kda + 0.25 * economy + 0.15 * stability + 0.15 * composure + 0.20 * lane)

    kda       = min((kills + assists) / max(1, deaths) / 6, 1)
    economy   = 0.5 * min(gold_share / 0.30, 1) + 0.5 * min(damage_share / 0.30, 1)
                (shares are of the player's own team total; average is 0.20)
    stability = mean stability score (tilt model) / 100
    composure = max(0, 1 - tilt_weight / 6), tilt_weight = sum over tilt events of
                LOW=1, MEDIUM=2, HIGH=3
    lane      = clip(0.5 + gold_diff_15 / 3000, 0, 1), gold_diff_15 = player's total gold at
                15:00 (or the last minute if shorter) minus the enemy with the same teamPosition;
                0.5 when no opponent can be matched.
"""

from __future__ import annotations

import numpy as np

from .timeline import ParsedMatch

COULD_HAVE_WON = 0.6
MIN_DROP = 0.05  # throw-window drops smaller than 5 percentage points are noise
LANE_MINUTE = 15
SEVERITY_WEIGHT = {"LOW": 1, "MEDIUM": 2, "HIGH": 3}
WEIGHTS = {"kda": 0.25, "economy": 0.25, "stability": 0.15, "composure": 0.15, "lane": 0.20}


def _other(team: str) -> str:
    return "red" if team == "blue" else "blue"


def _drivers(feats: list[dict], toward: str, n: int = 3) -> list[dict]:
    """Top-n features pushing toward ``toward``; contribution re-signed so + = toward that team."""
    sign = 1.0 if toward == "blue" else -1.0
    out = [{"feature": f["feature"], "label": f["label"], "contribution": round(sign * f["contribution"], 4)}
           for f in feats]
    out = [f for f in out if f["contribution"] > 0]
    return sorted(out, key=lambda f: -f["contribution"])[:n]


def _minute_drivers(dyn: dict, minute: int, toward: str) -> list[dict]:
    inf = next((i for i in dyn["inflection_points"] if i["minute"] == minute), None)
    if inf is not None:
        return _drivers(inf["top_features"], toward)
    row = next(r for r in dyn["timeline"] if r["minute"] == minute)
    return _drivers(row["shap_summary"], toward)


def _gold_at(pm: ParsedMatch, pid: int, minute: int) -> int | None:
    pmin = pm.player_minutes
    rows = pmin[(pmin["participant_id"] == pid) & (pmin["minute"] <= minute)]
    if rows.empty:
        return None
    return int(rows.sort_values("minute").iloc[-1]["total_gold"])


def player_ratings(pm: ParsedMatch, dyn: dict) -> list[dict]:
    stab = {s["participant_id"]: (float(np.mean([x["stability"] for x in s["scores"]])) if s["scores"] else 100.0)
            for s in dyn["player_stability"]}
    tilt: dict[int, list[dict]] = {}
    for a in dyn["player_anomalies"]:
        tilt.setdefault(a["participant_id"], []).append(a)
    team_gold = {t: sum(p["gold"] for p in pm.participants if p["team"] == t) or 1 for t in ("blue", "red")}
    team_dmg = {t: sum(p["damage"] for p in pm.participants if p["team"] == t) or 1 for t in ("blue", "red")}
    lane_min = min(LANE_MINUTE, pm.duration_min)

    out = []
    for p in pm.participants:
        pid, team = p["participant_id"], p["team"]
        opp = next((o for o in pm.participants
                    if o["team"] != team and o["role"] == p["role"] and p["role"] != "UNKNOWN"), None)
        gold_diff = None
        if opp is not None:
            g_me, g_opp = _gold_at(pm, pid, lane_min), _gold_at(pm, opp["participant_id"], lane_min)
            if g_me is not None and g_opp is not None:
                gold_diff = g_me - g_opp
        events = tilt.get(pid, [])
        tilt_weight = sum(SEVERITY_WEIGHT.get(e["severity"], 1) for e in events)
        gold_share = p["gold"] / team_gold[team]
        dmg_share = p["damage"] / team_dmg[team]
        comp = {
            "kda": min((p["kills"] + p["assists"]) / max(1, p["deaths"]) / 6.0, 1.0),
            "economy": 0.5 * min(gold_share / 0.30, 1.0) + 0.5 * min(dmg_share / 0.30, 1.0),
            "stability": stab.get(pid, 100.0) / 100.0,
            "composure": max(0.0, 1.0 - tilt_weight / 6.0),
            "lane": float(np.clip(0.5 + gold_diff / 3000.0, 0, 1)) if gold_diff is not None else 0.5,
        }
        rating = 100.0 * sum(WEIGHTS[k] * v for k, v in comp.items())
        out.append({
            "participant_id": pid,
            "riot_id": p["riot_id"],
            "champion": p["champion"],
            "team": team,
            "role": p["role"],
            "rating": round(rating, 1),
            "components": {k: round(v, 3) for k, v in comp.items()},
            "kills": p["kills"], "deaths": p["deaths"], "assists": p["assists"],
            "gold_share": round(gold_share, 3),
            "damage_share": round(dmg_share, 3),
            "mean_stability": round(stab.get(pid, 100.0), 1),
            "tilt_minutes": sorted({e["minute"] for e in events}),
            "tilt_severity": max((e["severity"] for e in events), key=lambda s: SEVERITY_WEIGHT.get(s, 1),
                                 default=None),
            "lane_minute": lane_min,
            "lane_gold_diff": gold_diff,
            "lane_opponent": opp["champion"] if opp else None,
        })
    return out


def _reasons(pl: dict, team_players: list[dict]) -> list[dict]:
    reasons = []
    max_deaths = max(p["deaths"] for p in team_players)
    if pl["deaths"] >= 6 or (pl["deaths"] >= 4 and pl["deaths"] == max_deaths):
        reasons.append({"code": "DEATHS", "deaths": pl["deaths"]})
    if pl["lane_gold_diff"] is not None and pl["lane_gold_diff"] <= -500:
        reasons.append({"code": "LANE_GOLD", "diff": pl["lane_gold_diff"], "minute": pl["lane_minute"],
                        "opponent": pl["lane_opponent"]})
    if pl["tilt_minutes"]:
        reasons.append({"code": "TILT", "minutes": pl["tilt_minutes"], "severity": pl["tilt_severity"]})
    if pl["mean_stability"] < 75:
        reasons.append({"code": "LOW_STABILITY", "mean": pl["mean_stability"]})
    if pl["role"] != "UTILITY" and pl["damage_share"] < 0.15:
        reasons.append({"code": "LOW_DAMAGE", "share": pl["damage_share"]})
    if not reasons:
        weakest = min(pl["components"], key=pl["components"].get)
        reasons.append({"code": "WEAKEST_COMPONENT", "component": weakest,
                        "value": pl["components"][weakest]})
    return reasons


def match_summary(pm: ParsedMatch, dyn: dict) -> dict:
    winner, loser = pm.winner, _other(pm.winner)
    tl = dyn["timeline"]
    minutes = [r["minute"] for r in tl]
    p_w = np.array([r["win_probability_blue"] if winner == "blue" else 1 - r["win_probability_blue"] for r in tl])
    d_w = np.array([r["delta_win_probability"] * (1 if winner == "blue" else -1) for r in tl])

    decisive = None
    if len(tl):
        i = int(np.argmax(d_w))
        decisive = {"minute": minutes[i], "delta": round(float(d_w[i]), 4),
                    "p_before": round(float(p_w[i] - d_w[i]), 4), "p_after": round(float(p_w[i]), 4),
                    "drivers": _minute_drivers(dyn, minutes[i], winner)}

    pnr = None
    if len(tl) and p_w[-1] >= 0.5:
        j = len(tl) - 1
        while j > 0 and p_w[j - 1] >= 0.5:
            j -= 1
        pnr = {"minute": minutes[j], "p": round(float(p_w[j]), 4)}

    loser_peak, throw = None, None
    if len(tl):
        p_l = 1 - p_w
        k = int(np.argmax(p_l))
        loser_peak = {"team": loser, "p": round(float(p_l[k]), 4), "minute": minutes[k],
                      "could_have_won": bool(p_l[k] >= COULD_HAVE_WON)}
        end_idx = minutes.index(pnr["minute"]) if pnr else len(tl) - 1
        if p_l[k] > 0.5 and end_idx > k:
            idx = range(k + 1, end_idx + 1)
            drops = sorted(idx, key=lambda x: -d_w[x])[:3]
            throw = {"start": minutes[k], "end": minutes[end_idx],
                     "p_start": round(float(p_l[k]), 4), "p_end": round(float(p_l[end_idx]), 4),
                     "drops": [{"minute": minutes[x], "delta": round(float(-d_w[x]), 4),
                                "drivers": _minute_drivers(dyn, minutes[x], winner)}
                               for x in sorted(drops) if d_w[x] >= MIN_DROP]}

    power_idx = {r["minute"]: r for r in tl}
    windows: dict = {}
    for side in ("blue", "red"):
        best = None
        for w in dyn["power_windows"].get(side, []):
            vals = [power_idx[m][f"team_{side}_power_index"] for m in range(w["start"], w["end"] + 1) if m in power_idx]
            if not vals:
                continue
            mean = float(np.mean(vals))
            if best is None or mean > best["mean_index"]:
                best = {"start": w["start"], "end": w["end"], "mean_index": round(mean, 1)}
        windows[side] = best
    lw = windows[loser]
    loser_window = None
    if lw:
        delta_l = -sum(float(d_w[minutes.index(m)]) for m in range(lw["start"], lw["end"] + 1) if m in minutes)
        loser_window = {"delta": round(delta_l, 4), "lost": bool(delta_l < 0)}

    ratings = player_ratings(pm, dyn)
    winners = sorted([r for r in ratings if r["team"] == winner], key=lambda r: -r["rating"])
    losers = sorted([r for r in ratings if r["team"] == loser], key=lambda r: -r["rating"])
    shpb = None
    if losers:
        worst = losers[-1]
        shpb = {"participant_id": worst["participant_id"], "rating": worst["rating"],
                "reasons": _reasons(worst, losers)}

    return {
        "match_id": pm.match_id,
        "outcome": {"winner": winner, "loser": loser, "duration_min": pm.duration_min},
        "decisive_moment": decisive,
        "point_of_no_return": pnr,
        "loser_peak": loser_peak,
        "throw_window": throw,
        "power_windows": {"blue": windows["blue"], "red": windows["red"], "loser_window": loser_window},
        "players": ratings,
        "mvp": winners[0]["participant_id"] if winners else None,
        "loser_best": losers[0]["participant_id"] if losers else None,
        "should_have_performed_better": shpb,
        "model_version": dyn.get("model_version"),
    }
