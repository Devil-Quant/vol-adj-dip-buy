"""Tests for the forecastability harness: no look-ahead in features,
walk-forward train precedes test, targets sane, and the evaluators run."""
from __future__ import annotations

import math
import random
from datetime import date, timedelta

import pandas as pd

from clients import OhlcBar
from forecast.features import FEATURE_COLS, VOLUME_COLS, build_features
from forecast.implied import build_vix_feature, merge_vix
from forecast.targets import build_targets
from forecast.walkforward import (_date_folds, walk_forward_direction,
                                  walk_forward_range)


def mk_bars(n=300, seed=0):
    random.seed(seed)
    bars, px, d0 = [], 100.0, date(2024, 1, 1)
    for i in range(n):
        o = px
        h = o + abs(random.gauss(0, 1)) + 0.5
        low = o - abs(random.gauss(0, 1)) - 0.5
        c = low + (h - low) * random.random()
        bars.append(OhlcBar(d=d0 + timedelta(days=i), open=round(o, 2),
                            high=round(h, 2), low=round(low, 2),
                            close=round(c, 2),
                            volume=round(random.uniform(1e6, 5e6))))
        px = c
    return bars


def test_features_no_lookahead():
    bars = mk_bars()
    t = 25
    feat1 = build_features(bars)
    b = bars[t]
    bars2 = list(bars)
    # mutate today's high/low/close (keep open+volume) — must NOT change row t
    bars2[t] = OhlcBar(d=b.d, open=b.open, high=b.high + 10,
                       low=b.low - 10, close=b.close + 5, volume=b.volume)
    feat2 = build_features(bars2)
    r1 = feat1[feat1["date"] == b.d].iloc[0]
    r2 = feat2[feat2["date"] == b.d].iloc[0]
    for col in FEATURE_COLS:
        same = r1[col] == r2[col] or (pd.isna(r1[col]) and pd.isna(r2[col]))
        assert same, f"feature {col} leaked today's H/L/C"
    # next day SHOULD reflect today's close (gap/ret/prior_range change)
    nd = bars[t + 1].d
    n1 = feat1[feat1["date"] == nd].iloc[0]
    n2 = feat2[feat2["date"] == nd].iloc[0]
    changed = any(n1[c] != n2[c] for c in FEATURE_COLS if not pd.isna(n1[c]))
    assert changed, "next-day features should use today's close"


def test_volume_features_no_lookahead():
    bars = mk_bars()
    t = 25
    feat1 = build_features(bars)
    b = bars[t]
    bars2 = list(bars)
    # mutate ONLY today's volume — must NOT change row t's volume features
    bars2[t] = OhlcBar(d=b.d, open=b.open, high=b.high, low=b.low,
                       close=b.close, volume=b.volume * 5)
    feat2 = build_features(bars2)
    r1 = feat1[feat1["date"] == b.d].iloc[0]
    r2 = feat2[feat2["date"] == b.d].iloc[0]
    for col in VOLUME_COLS:
        same = r1[col] == r2[col] or (pd.isna(r1[col]) and pd.isna(r2[col]))
        assert same, f"volume feature {col} leaked today's volume"
    # next day SHOULD reflect today's volume
    nd = bars[t + 1].d
    n1 = feat1[feat1["date"] == nd].iloc[0]
    n2 = feat2[feat2["date"] == nd].iloc[0]
    changed = any(n1[c] != n2[c] for c in VOLUME_COLS if not pd.isna(n1[c]))
    assert changed, "next-day volume features should use today's volume"


def test_date_folds_train_precedes_test():
    df = pd.DataFrame({"date": [date(2024, 1, 1) + timedelta(days=i)
                                for i in range(100)]})
    folds = _date_folds(df, n_splits=5, min_train_frac=0.4)
    assert folds
    for train, test in folds:
        assert max(train) < min(test)


def test_targets_sane():
    tgt = build_targets(mk_bars(n=50))
    assert {"date", "range", "up"}.issubset(tgt.columns)
    assert (tgt["range"] >= 0).all()
    assert tgt["up"].isin([0, 1]).all()


def test_vix_feature_no_lookahead():
    vb = [OhlcBar(d=date(2024, 1, 1) + timedelta(days=i), open=15.0, high=16.0,
                  low=14.0, close=10.0 + i) for i in range(10)]
    f = build_vix_feature(vb)
    assert pd.isna(f.iloc[0]["vix_implied"])           # row 0 has no prior VIX
    # row t uses VIX close from t-1 (here close_0 = 10.0), not today's close
    expected = 10.0 / 100.0 / math.sqrt(252)
    assert abs(f.iloc[1]["vix_implied"] - expected) < 1e-12


def test_merge_vix_aligns_and_drops_unmatched():
    bars = mk_bars(n=60)
    frame = build_features(bars).merge(build_targets(bars), on="date")
    # VIX covers only the first 30 dates -> inner-merge keeps the overlap only
    vb = [OhlcBar(d=bars[i].d, open=15.0, high=16.0, low=14.0, close=15.0)
          for i in range(30)]
    merged = merge_vix(frame, vb)
    assert "vix_implied" in merged.columns
    assert len(merged) == 30


def test_walk_forward_runs():
    bars = mk_bars(n=300)
    pooled = build_features(bars).merge(build_targets(bars), on="date")
    r = walk_forward_range(pooled, FEATURE_COLS, n_splits=3)
    assert r["n"] > 0 and "model_mae" in r and "ewma_mae" in r
    d = walk_forward_direction(pooled, FEATURE_COLS, n_splits=3)
    assert d["n"] > 0 and "model_acc" in d and "base_acc" in d
