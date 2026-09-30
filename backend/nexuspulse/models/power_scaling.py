"""Module A -- non-linear compositional power spikes (GAM with cubic splines).

Fits expected damage output per player-minute as smooth functions of level, item gold,
item stats and a tier-specific time curve, then aggregates to a team share index [0, 100].
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from ..timeline import ParsedMatch

log = logging.getLogger(__name__)

FEATURES = ["level", "item_cost", "item_stat", "minute", "tier"]
WINDOW_THRESHOLD = 52.0  # team index above which a minute counts toward a power window
WINDOW_MIN_LEN = 3


def _player_frame(pm: ParsedMatch) -> pd.DataFrame:
    df = pm.player_minutes.copy()
    tiers = {p["participant_id"]: p["tier"] for p in pm.participants}
    df["tier"] = df["participant_id"].map(tiers).fillna(1).astype(int)
    df["item_stat"] = df["item_ad"] + 0.6 * df["item_ap"] + df["item_hp"] / 12.0
    return df


def build_dataset(parsed: list[ParsedMatch]) -> pd.DataFrame:
    frames = []
    for pm in parsed:
        df = _player_frame(pm).sort_values(["participant_id", "minute"])
        # Target: damage to champions per minute over the next 2 minutes (forward-looking output).
        future = df.groupby("participant_id")["damage_to_champions"].shift(-2)
        df["target"] = (future - df["damage_to_champions"]) / 2.0
        frames.append(df.dropna(subset=["target"]))
    return pd.concat(frames, ignore_index=True)


class PowerScalingModel:
    def __init__(self, model, kind: str, metrics: dict):
        self.model = model
        self.kind = kind  # "pygam" or "spline_ridge"
        self.metrics = metrics

    @classmethod
    def train(cls, parsed: list[ParsedMatch], max_rows: int = 40000, seed: int = 7) -> "PowerScalingModel":
        data = build_dataset(parsed)
        if len(data) > max_rows:
            data = data.sample(max_rows, random_state=seed)
        x = data[FEATURES].to_numpy(dtype=float)
        y = data["target"].clip(lower=0).to_numpy(dtype=float)
        try:
            from pygam import LinearGAM, s, te

            gam = LinearGAM(
                s(0, n_splines=10) + s(1, n_splines=10) + s(2, n_splines=8)
                + te(3, 4, n_splines=[10, 3], spline_order=[3, 0], dtype=["numerical", "categorical"])
            )
            gam.gridsearch(x, y, lam=np.logspace(-1, 3, 5), progress=False)
            r2 = float(gam.statistics_["pseudo_r2"]["explained_deviance"])
            model, kind = gam, "pygam"
        except Exception as exc:  # noqa: BLE001 -- spec allows polynomial/spline regression
            log.warning("pygam unavailable (%s); falling back to spline ridge regression", exc)
            model, kind, r2 = cls._fit_spline_ridge(x, y)
        metrics = {"rows": int(len(data)), "r2": round(r2, 4), "kind": kind}
        log.info("power-scaling model trained: %s", metrics)
        return cls(model, kind, metrics)

    @staticmethod
    def _fit_spline_ridge(x: np.ndarray, y: np.ndarray):
        from sklearn.compose import ColumnTransformer
        from sklearn.linear_model import RidgeCV
        from sklearn.pipeline import Pipeline
        from sklearn.preprocessing import OneHotEncoder, PolynomialFeatures, SplineTransformer

        pre = ColumnTransformer([
            ("splines", SplineTransformer(n_knots=8, degree=3), [0, 1, 2, 3]),
            ("tier", OneHotEncoder(handle_unknown="ignore"), [4]),
        ])
        pipe = Pipeline([("pre", pre), ("inter", PolynomialFeatures(2, interaction_only=True)),
                         ("ridge", RidgeCV(alphas=np.logspace(-2, 3, 8)))])
        pipe.fit(x, y)
        return pipe, "spline_ridge", float(pipe.score(x, y))

    def predict_player(self, df: pd.DataFrame) -> np.ndarray:
        x = df[FEATURES].to_numpy(dtype=float)
        return np.clip(self.model.predict(x), 1.0, None)

    def team_index(self, pm: ParsedMatch) -> pd.DataFrame:
        df = _player_frame(pm)
        df["power"] = self.predict_player(df)
        team = df.pivot_table(index="minute", columns="team", values="power", aggfunc="sum").fillna(1.0)
        blue = team.get("blue", pd.Series(1.0, index=team.index))
        red = team.get("red", pd.Series(1.0, index=team.index))
        index_blue = 100.0 * blue / (blue + red)
        return pd.DataFrame({"minute": team.index.astype(int),
                             "team_blue_power_index": index_blue.round(1).to_numpy(),
                             "team_red_power_index": (100.0 - index_blue).round(1).to_numpy()})


def power_windows(index_df: pd.DataFrame) -> dict[str, list[dict]]:
    """Contiguous spans (>= WINDOW_MIN_LEN minutes) where a team is both ahead on theoretical power
    and near its own in-game peak (>= its 60th percentile), e.g. blue peak window 18-26."""
    out: dict[str, list[dict]] = {"blue": [], "red": []}
    for side in ("blue", "red"):
        col = f"team_{side}_power_index"
        threshold = max(WINDOW_THRESHOLD - 1.0, float(index_df[col].quantile(0.6))) if len(index_df) else 100
        start = None
        rows = list(index_df[["minute", col]].itertuples(index=False))
        for i, (minute, value) in enumerate(rows):
            if value >= threshold and start is None:
                start = minute
            last = i == len(rows) - 1
            if start is not None and (value < threshold or last):
                end = minute if value >= threshold else rows[i - 1][0]
                if end - start + 1 >= WINDOW_MIN_LEN:
                    out[side].append({"start": int(start), "end": int(end)})
                start = None
    return out
