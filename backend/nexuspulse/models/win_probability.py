"""Module B -- per-minute win probability (XGBoost) with TreeSHAP attribution."""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.metrics import brier_score_loss, log_loss, roc_auc_score
from sklearn.model_selection import GroupShuffleSplit

from ..timeline import FEATURE_LABELS, WIN_FEATURES, ParsedMatch, win_feature_frame

log = logging.getLogger(__name__)

# Every differential should only ever help the side that owns it.
MONOTONE = tuple(0 if f == "minute" else 1 for f in WIN_FEATURES)


def _sigmoid(x):
    return 1.0 / (1.0 + np.exp(-x))


def build_dataset(parsed: list[ParsedMatch]) -> tuple[pd.DataFrame, np.ndarray, np.ndarray]:
    xs, ys, groups = [], [], []
    for i, pm in enumerate(parsed):
        if pm.team_minutes.empty:
            continue
        x = win_feature_frame(pm.team_minutes)
        xs.append(x)
        ys.append(np.full(len(x), 1 if pm.winner == "blue" else 0))
        groups.append(np.full(len(x), i))
    return pd.concat(xs, ignore_index=True), np.concatenate(ys), np.concatenate(groups)


class WinProbabilityModel:
    def __init__(self, model: xgb.XGBClassifier, metrics: dict):
        self.model = model
        self.metrics = metrics
        self._explainer = None

    @classmethod
    def train(cls, parsed: list[ParsedMatch], seed: int = 7) -> "WinProbabilityModel":
        x, y, groups = build_dataset(parsed)
        params = dict(
            n_estimators=350, max_depth=3, learning_rate=0.05, subsample=0.8, colsample_bytree=0.9,
            min_child_weight=25, reg_lambda=5.0, monotone_constraints=MONOTONE,
            eval_metric="logloss", random_state=seed, n_jobs=0,
        )
        metrics: dict = {"rows": int(len(x)), "matches": int(len(set(groups)))}
        if len(set(groups)) >= 10:
            tr, te = next(GroupShuffleSplit(n_splits=1, test_size=0.2, random_state=seed).split(x, y, groups))
            holdout = xgb.XGBClassifier(**params).fit(x.iloc[tr], y[tr])
            p = holdout.predict_proba(x.iloc[te])[:, 1]
            if len(set(y[te])) > 1:
                metrics.update(
                    auc=round(float(roc_auc_score(y[te], p)), 4),
                    log_loss=round(float(log_loss(y[te], p)), 4),
                    brier=round(float(brier_score_loss(y[te], p)), 4),
                )
        model = xgb.XGBClassifier(**params).fit(x, y)
        log.info("win-probability model trained: %s", metrics)
        return cls(model, metrics)

    def predict(self, team_minutes: pd.DataFrame) -> np.ndarray:
        return self.model.predict_proba(win_feature_frame(team_minutes))[:, 1]

    def explain(self, team_minutes: pd.DataFrame) -> tuple[np.ndarray, float]:
        """TreeSHAP values in log-odds space: (n_minutes x n_features), base value."""
        x = win_feature_frame(team_minutes)
        try:
            import shap

            if self._explainer is None:
                self._explainer = shap.TreeExplainer(self.model)
            values = np.asarray(self._explainer.shap_values(x))
            base = float(np.ravel(self._explainer.expected_value)[0])
            return values.reshape(len(x), len(WIN_FEATURES)), base
        except Exception as exc:  # noqa: BLE001 -- xgboost's native TreeSHAP is equivalent
            log.debug("shap.TreeExplainer unavailable (%s); using xgboost pred_contribs", exc)
            contribs = self.model.get_booster().predict(xgb.DMatrix(x), pred_contribs=True)
            return contribs[:, :-1], float(contribs[0, -1])

    def __getstate__(self):
        state = self.__dict__.copy()
        state["_explainer"] = None
        return state


def _to_probability(phi: np.ndarray, logit_from: float, logit_to: float) -> np.ndarray:
    """Scale log-odds attributions so they sum to the probability change (sign-preserving)."""
    p_from, p_to = _sigmoid(logit_from), _sigmoid(logit_to)
    d_logit = logit_to - logit_from
    slope = (p_to - p_from) / d_logit if abs(d_logit) > 1e-6 else p_to * (1 - p_to)
    return phi * slope


def top_features(phi_prob: np.ndarray, values: np.ndarray, k: int = 3) -> list[dict]:
    order = np.argsort(-np.abs(phi_prob))[:k]
    out = []
    for j in order:
        if abs(phi_prob[j]) < 1e-4:
            continue
        name = WIN_FEATURES[j]
        out.append({
            "feature": name,
            "label": FEATURE_LABELS[name],
            "value": round(float(values[j]), 4),
            "contribution": round(float(phi_prob[j]), 4),
        })
    return out


def attribution_series(model: WinProbabilityModel, team_minutes: pd.DataFrame, delta: float) -> dict:
    """Win probability per minute, state attribution, and transition attribution at inflections."""
    probs = model.predict(team_minutes)
    phi, base = model.explain(team_minutes)
    logits = base + phi.sum(axis=1)
    values = win_feature_frame(team_minutes).to_numpy()
    minutes = team_minutes["minute"].to_numpy()

    rows, inflections = [], []
    for i in range(len(minutes)):
        state_attr = _to_probability(phi[i], base, logits[i])
        if i == 0:
            d_p = float(probs[0] - _sigmoid(base))
            trans_attr, trans_vals = state_attr, values[0]
        else:
            d_p = float(probs[i] - probs[i - 1])
            trans_attr = _to_probability(phi[i] - phi[i - 1], logits[i - 1], logits[i])
            trans_vals = values[i] - values[i - 1]
        # Minutes 1-2 carry almost no information; swings there are noise, not turning points.
        is_inflection = i > 0 and int(minutes[i]) >= 3 and abs(d_p) >= delta
        rows.append({
            "minute": int(minutes[i]),
            "win_probability_blue": round(float(probs[i]), 4),
            "delta_win_probability": round(d_p, 4),
            "is_inflection_point": bool(is_inflection),
            "shap_summary": top_features(state_attr, values[i]),
        })
        if is_inflection:
            feats = top_features(trans_attr, trans_vals)
            direction = "blue" if d_p > 0 else "red"
            drivers = ", ".join(
                f"{f['label']} ({'+' if (f['contribution'] > 0) == (direction == 'blue') else '-'}"
                f"{abs(f['contribution']) * 100:.0f}%)"
                for f in feats
            )
            inflections.append({
                "minute": int(minutes[i]),
                "delta": round(d_p, 4),
                "direction": direction,
                "top_features": feats,
                "description": f"+{abs(d_p) * 100:.0f}% {direction.title()} win probability at "
                               f"{int(minutes[i])}:00 driven by: {drivers or 'diffuse state change'}",
            })
    return {"rows": rows, "inflections": inflections}
