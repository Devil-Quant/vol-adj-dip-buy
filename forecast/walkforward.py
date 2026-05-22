"""Expanding walk-forward evaluation, pooled across symbols BY DATE so the
train window always precedes the test window (no look-ahead). Range via Ridge
vs an EWMA-of-range persistence baseline; direction via LogisticRegression vs
the train-majority base rate. Simple regularized models on purpose."""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.metrics import mean_absolute_error, r2_score, roc_auc_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler


def _date_folds(df: pd.DataFrame, n_splits: int, min_train_frac: float):
    """Yield (train_dates, test_dates) for expanding walk-forward over the
    sorted unique dates. Train is always strictly earlier than test."""
    udates = np.array(sorted(pd.unique(df["date"])))
    n = len(udates)
    start = max(int(n * min_train_frac), 1)
    bounds = np.linspace(start, n, n_splits + 1).astype(int)
    folds = []
    for k in range(n_splits):
        lo, hi = int(bounds[k]), int(bounds[k + 1])
        if lo >= hi:
            continue
        folds.append((set(udates[:lo].tolist()), set(udates[lo:hi].tolist())))
    return folds


def walk_forward_range(df, feature_cols, *, n_splits=5, min_train_frac=0.4,
                       alpha=1.0):
    """OOS range forecast. Ridge (incl. range_ewma as a feature) vs the
    EWMA-of-range baseline and a constant train-mean baseline."""
    data = df.dropna(subset=list(feature_cols) + ["range", "range_ewma"]).copy()
    yp, yt, b_ewma, b_mean = [], [], [], []
    for train, test in _date_folds(data, n_splits, min_train_frac):
        tr = data[data["date"].isin(train)]
        te = data[data["date"].isin(test)]
        if len(tr) < 50 or len(te) == 0:
            continue
        model = make_pipeline(StandardScaler(), Ridge(alpha=alpha))
        model.fit(tr[feature_cols], tr["range"])
        yp.extend(model.predict(te[feature_cols]).tolist())
        yt.extend(te["range"].tolist())
        b_ewma.extend(te["range_ewma"].tolist())
        b_mean.extend([float(tr["range"].mean())] * len(te))
    yt, yp = np.array(yt), np.array(yp)
    b_ewma, b_mean = np.array(b_ewma), np.array(b_mean)
    if len(yt) == 0:
        return {"n": 0}
    return {
        "n": int(len(yt)),
        "model_mae": float(mean_absolute_error(yt, yp)),
        "model_r2": float(r2_score(yt, yp)),
        "ewma_mae": float(mean_absolute_error(yt, b_ewma)),
        "ewma_r2": float(r2_score(yt, b_ewma)),
        "mean_mae": float(mean_absolute_error(yt, b_mean)),
    }


def walk_forward_direction(df, feature_cols, *, n_splits=5, min_train_frac=0.4,
                           C=1.0):
    """OOS open->close direction. LogisticRegression vs train-majority base
    rate. Reports accuracy, ROC-AUC, and the realized up-rate (base rate)."""
    data = df.dropna(subset=list(feature_cols) + ["up"]).copy()
    p_up, yt, base = [], [], []
    for train, test in _date_folds(data, n_splits, min_train_frac):
        tr = data[data["date"].isin(train)]
        te = data[data["date"].isin(test)]
        if len(tr) < 50 or len(te) == 0 or tr["up"].nunique() < 2:
            continue
        model = make_pipeline(StandardScaler(),
                              LogisticRegression(max_iter=1000, C=C))
        model.fit(tr[feature_cols], tr["up"])
        p_up.extend(model.predict_proba(te[feature_cols])[:, 1].tolist())
        yt.extend(te["up"].tolist())
        base.extend([int(round(float(tr["up"].mean())))] * len(te))
    p_up, yt, base = np.array(p_up), np.array(yt), np.array(base)
    if len(yt) == 0:
        return {"n": 0}
    pred = (p_up >= 0.5).astype(int)
    out = {
        "n": int(len(yt)),
        "model_acc": float((pred == yt).mean()),
        "base_acc": float((base == yt).mean()),
        "up_rate": float(yt.mean()),
        "model_auc": float("nan"),
    }
    if len(set(yt.tolist())) > 1:
        out["model_auc"] = float(roc_auc_score(yt, p_up))
    return out
