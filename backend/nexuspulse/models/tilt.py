"""Module C -- player stability & tilt anomaly detection (Isolation Forest per role).

Each player-minute is described by a 3-minute sliding window relative to a role/minute
baseline learned from the training corpus. Ratios are capped at ~1 so that only *collapses*
(not over-performance) look anomalous.
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest

from ..timeline import ROLES, ParsedMatch

log = logging.getLogger(__name__)

WINDOW = 3
FEATURES = ["cs_ratio", "xp_ratio", "ward_ratio", "isolated_deaths", "deaths"]
FLAG_CDF = 0.03  # a window in the lowest 3% of the role's training scores is flagged
MAX_MINUTE = 45


def _window_gains(pm: ParsedMatch) -> pd.DataFrame:
    df = pm.player_minutes.sort_values(["participant_id", "minute"]).copy()
    roles = {p["participant_id"]: p["role"] for p in pm.participants}
    df["role"] = df["participant_id"].map(roles)
    g = df.groupby("participant_id")
    for col, out in (("cs", "cs_gain"), ("xp", "xp_gain"), ("wards_placed", "ward_gain")):
        prev = g[col].shift(WINDOW).fillna(0)
        span = np.minimum(df["minute"], WINDOW)
        df[out] = (df[col] - prev) * (WINDOW / span)
    # Deaths inside (minute - WINDOW, minute].
    iso = np.zeros(len(df))
    dth = np.zeros(len(df))
    key = {(r.participant_id, r.minute): i for i, r in enumerate(df[["participant_id", "minute"]].itertuples(index=False))}
    for d in pm.deaths:
        for m in range(int(np.ceil(d["minute"])), int(np.ceil(d["minute"])) + WINDOW):
            i = key.get((d["victim"], m))
            if i is not None:
                dth[i] += 1
                iso[i] += 1 if d.get("isolated") else 0
    df["deaths_window"] = dth
    df["isolated_deaths"] = iso
    return df


class TiltModel:
    def __init__(self, baselines: dict, forests: dict, score_refs: dict, metrics: dict):
        self.baselines = baselines      # role -> {"cs": arr, "xp": arr, "ward": arr} indexed by minute
        self.forests = forests          # role -> IsolationForest
        self.score_refs = score_refs    # role -> sorted training scores (for empirical CDF)
        self.metrics = metrics

    @classmethod
    def train(cls, parsed: list[ParsedMatch], seed: int = 7) -> "TiltModel":
        gains = pd.concat([_window_gains(pm) for pm in parsed], ignore_index=True)
        gains = gains[gains["role"].isin(ROLES)]
        baselines = {}
        for role, grp in gains.groupby("role"):
            med = grp.groupby("minute")[["cs_gain", "xp_gain", "ward_gain"]].median()
            med = med.reindex(range(0, MAX_MINUTE + 1)).ffill().bfill()
            med = med.rolling(3, center=True, min_periods=1).mean()
            baselines[role] = {"cs": med["cs_gain"].to_numpy(), "xp": med["xp_gain"].to_numpy(),
                               "ward": med["ward_gain"].to_numpy()}
        model = cls(baselines, {}, {}, {})
        feats = model._features(gains)
        mask = feats["minute"] >= WINDOW
        for role in ROLES:
            sub = feats[mask & (feats["role"] == role)]
            if len(sub) < 50:
                continue
            forest = IsolationForest(n_estimators=200, contamination="auto", random_state=seed)
            forest.fit(sub[FEATURES].to_numpy())
            model.forests[role] = forest
            model.score_refs[role] = np.sort(forest.score_samples(sub[FEATURES].to_numpy()))
        model.metrics = {"rows": int(mask.sum()), "roles": sorted(model.forests)}
        log.info("tilt model trained: %s", model.metrics)
        return model

    def _features(self, gains: pd.DataFrame) -> pd.DataFrame:
        df = gains.copy()
        minute_idx = df["minute"].clip(upper=MAX_MINUTE).astype(int).to_numpy()
        role_arr = df["role"].to_numpy()
        base_cs = np.array([self.baselines.get(r, self.baselines.get("MIDDLE"))["cs"][m] for r, m in zip(role_arr, minute_idx)])
        base_xp = np.array([self.baselines.get(r, self.baselines.get("MIDDLE"))["xp"][m] for r, m in zip(role_arr, minute_idx)])
        base_wd = np.array([self.baselines.get(r, self.baselines.get("MIDDLE"))["ward"][m] for r, m in zip(role_arr, minute_idx)])
        df["base_cs"], df["base_xp"], df["base_ward"] = base_cs, base_xp, base_wd
        df["cs_ratio"] = ((df["cs_gain"] + 2) / (base_cs + 2)).clip(0, 1.2)
        df["xp_ratio"] = ((df["xp_gain"] + 100) / (base_xp + 100)).clip(0, 1.2)
        df["ward_ratio"] = ((df["ward_gain"] + 0.5) / (base_wd + 0.5)).clip(0, 1.5)
        df["deaths"] = df["deaths_window"]
        return df

    def score_match(self, pm: ParsedMatch) -> pd.DataFrame:
        """Per player-minute features, empirical CDF of the anomaly score, and stability [0, 100]."""
        feats = self._features(_window_gains(pm))
        feats["cdf"] = 1.0
        for role, forest in self.forests.items():
            idx = feats.index[feats["role"] == role]
            if len(idx) == 0:
                continue
            scores = forest.score_samples(feats.loc[idx, FEATURES].to_numpy())
            ref = self.score_refs[role]
            feats.loc[idx, "cdf"] = np.searchsorted(ref, scores, side="right") / len(ref)
        feats.loc[feats["minute"] < WINDOW, "cdf"] = np.maximum(feats.loc[feats["minute"] < WINDOW, "cdf"], 0.5)
        feats["stability"] = (100.0 * feats["cdf"].clip(0, 1) ** 0.35).round(1)
        return feats


def _severity(cdf: float) -> str:
    return "HIGH" if cdf < 0.005 else "MEDIUM" if cdf < 0.015 else "LOW"


def _trigger(pm: ParsedMatch, pid: int, team: str, start: int, end: int) -> str:
    """Most recent macro event before the collapse window: own death or objective loss."""
    lo, hi = start - WINDOW - 2, end
    cands = []
    for d in pm.deaths:
        if d["victim"] == pid and lo <= d["minute"] <= hi:
            solo = "solo " if not d["assisters"] else ""
            cands.append((d["minute"], f"a {solo}death at {_mmss(d['minute'])}"))
    names = {"DRAGON": "dragon", "BARON_NASHOR": "Baron", "RIFTHERALD": "Rift Herald",
             "HORDE": "voidgrub", "TOWER_BUILDING": "tower"}
    for o in pm.objectives:
        if o["team"] != team and o["type"] in names and lo <= o["minute"] <= hi:
            cands.append((o["minute"], f"{names[o['type']]} defeat at {_mmss(o['minute'])}"))
    if not cands:
        return ""
    cands.sort(key=lambda c: (c[0] > start, -c[0]))  # prefer the latest event before the window
    return f" following {cands[0][1]}"


def _mmss(minute: float) -> str:
    total = int(round(minute * 60))
    return f"{total // 60}:{total % 60:02d}"


def detect_anomalies(pm: ParsedMatch, scored: pd.DataFrame) -> list[dict]:
    parts = {p["participant_id"]: p for p in pm.participants}
    flagged = scored[(scored["cdf"] <= FLAG_CDF) & (scored["minute"] >= 4)].sort_values(["participant_id", "minute"])
    anomalies = []
    for pid, grp in flagged.groupby("participant_id"):
        # Merge contiguous minutes into one event, reported at its most unstable minute.
        runs, current = [], [grp.iloc[0]]
        for _, row in grp.iloc[1:].iterrows():
            if row["minute"] - current[-1]["minute"] <= 1:
                current.append(row)
            else:
                runs.append(current)
                current = [row]
        runs.append(current)
        p = parts[pid]
        for run in runs:
            worst = min(run, key=lambda r: r["cdf"])
            start, end = int(run[0]["minute"]), int(run[-1]["minute"])
            anomalies.append(_describe(pm, p, worst, start, end))
    return sorted(anomalies, key=lambda a: a["minute"])


def _describe(pm: ParsedMatch, p: dict, row: pd.Series, start: int, end: int) -> dict:
    role = p["role"]
    cs_drop = 1 - row["cs_ratio"]
    xp_drop = 1 - row["xp_ratio"]
    ward_drop = 1 - min(row["ward_ratio"], 1.0)
    iso = int(row["isolated_deaths"])
    devs = {
        "FARM_COLLAPSE": cs_drop * (0.3 if role == "UTILITY" else 1.0),
        "XP_STALL": xp_drop * 0.9,
        "VISION_DROP": ward_drop * (0.8 if role in ("UTILITY", "JUNGLE") else 0.4),
        "ISOLATED_DEATHS": iso * 0.45,
    }
    kind = "ISOLATED_DEATHS" if iso >= 2 else max(devs, key=devs.get)
    if devs[kind] < 0.35 and iso < 2:
        kind = "GENERAL_DEVIATION"
    details = []
    if cs_drop >= 0.4 and role != "UTILITY":
        details.append(f"CS dropped {cs_drop * 100:.0f}% vs role baseline")
    if xp_drop >= 0.35:
        details.append(f"XP gain down {xp_drop * 100:.0f}%")
    if iso:
        details.append(f"{iso} isolated death{'s' if iso > 1 else ''} logged")
    elif row["deaths"] >= 2:
        details.append(f"{int(row['deaths'])} deaths in 3 minutes")
    if ward_drop >= 0.7 and role in ("UTILITY", "JUNGLE"):
        details.append("vision placement collapsed")
    if not details:
        details.append("multi-metric deviation from normal play")
    minute = int(row["minute"])
    span = f"{start}:00-{end}:00" if end > start else f"{minute}:00"
    desc = f"Tilt event flagged at {minute}:00 ({span}): " + ", ".join(details) + \
        _trigger(pm, p["participant_id"], p["team"], start, end)
    return {
        "puuid": p["puuid"],
        "participant_id": p["participant_id"],
        "champion": p["champion"],
        "team": p["team"],
        "minute": minute,
        "anomaly_type": kind,
        "severity": _severity(float(row["cdf"])),
        "description": desc,
        "score": round(float(row["stability"]), 1),
    }
