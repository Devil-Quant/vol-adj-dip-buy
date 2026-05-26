"""Markov regime model tests: state labelling, no-look-ahead, gate threshold."""
from __future__ import annotations

import math
import random
from datetime import date, timedelta

import pandas as pd

from clients import OhlcBar
from forecast.markov import (build_markov_states, markov_allow_by_day,
                             state_probs_by_day)


def _bars(closes, start=date(2024, 1, 1)):
    return [OhlcBar(d=start + timedelta(days=i), open=c, high=c * 1.005,
                    low=c * 0.995, close=c) for i, c in enumerate(closes)]


def test_states_threshold():
    # Force a 20-day return of exactly +10% (bull) at index 20: close[0]=100,
    # close[20]=110; then a 20-day return of exactly -10% (bear) at index 40:
    # close[20]=110, close[40]=99. Sideways closes in between hold the line.
    closes = [100.0] * 20 + [110.0] * 20 + [99.0] * 20
    df = build_markov_states(_bars(closes), lookback=20,
                             bull_thresh=0.05, bear_thresh=-0.05)
    # The internal state labels happen at every row; we don't expose them
    # directly, but the *predicted-day* state column (= state at row-1) will be
    # populated once warm-up clears. Smoke-test: build does not crash and
    # returns 60 rows.
    assert len(df) == 60
    # Probability vectors that ARE filled should sum to 1.0
    labeled = df.dropna(subset=["p_bull"])
    assert (labeled["p_bull"] + labeled["p_sideways"] + labeled["p_bear"]
            ).round(9).eq(1.0).all()


def test_no_lookahead():
    # Build random-ish bars; mutate close at index t and assert row t's
    # prediction is unchanged (uses only data <= day t-1).
    random.seed(0)
    closes = [100.0]
    for _ in range(199):
        closes.append(closes[-1] * (1.0 + random.gauss(0, 0.01)))
    bars1 = _bars(closes)
    df1 = build_markov_states(bars1, lookback=20)

    t = 100
    closes2 = list(closes)
    closes2[t] = closes2[t] * 1.20  # large mutation of today's close
    bars2 = _bars(closes2)
    df2 = build_markov_states(bars2, lookback=20)

    # Row t in BOTH frames refers to predictions made *before* knowing close_t
    # (uses state at t-1 and transitions through (t-2, t-1)). Must be identical.
    r1 = df1.iloc[t]
    r2 = df2.iloc[t]
    for col in ("state", "p_bull", "p_sideways", "p_bear", "edge"):
        same = r1[col] == r2[col] or (pd.isna(r1[col]) and pd.isna(r2[col]))
        assert same, f"row {t}: column {col} leaked close_t (got {r1[col]} vs {r2[col]})"

    # Row t+1 SHOULD change (uses state at t which depends on close_t)
    n1 = df1.iloc[t + 1]
    n2 = df2.iloc[t + 1]
    differs = any(
        (n1[c] != n2[c]) and not (pd.isna(n1[c]) and pd.isna(n2[c]))
        for c in ("state", "p_bull", "p_sideways", "p_bear", "edge")
    )
    assert differs, "row t+1 should reflect today's close, but is unchanged"


def test_allow_by_day_threshold():
    # Drive a clean bull/bear pattern so the matrix has meaningful entries,
    # then check the gate flips when theta passes the actual edge.
    closes = [100.0]
    for i in range(200):
        # 30-day cycles of trending up vs trending down -> mixed regimes
        delta = 0.005 if (i // 30) % 2 == 0 else -0.005
        closes.append(closes[-1] * (1.0 + delta))
    bars = _bars(closes)
    df = build_markov_states(bars, lookback=20)
    labeled = df.dropna(subset=["edge"])
    assert len(labeled) > 50, "expected meaningful labeled rows"

    # The gate at theta=0 mirrors (edge > 0)
    allow = markov_allow_by_day(bars, lookback=20, theta=0.0)
    expected = {row["date"]: bool(row["edge"] > 0.0) for _, row in labeled.iterrows()}
    assert allow == expected

    # Raising theta strictly reduces the True-set (monotone gate)
    allow_high = markov_allow_by_day(bars, lookback=20, theta=0.5)
    true_low = {d for d, v in allow.items() if v}
    true_high = {d for d, v in allow_high.items() if v}
    assert true_high.issubset(true_low)

    # And state_probs_by_day returns 3-tuples summing to 1.0
    probs = state_probs_by_day(bars, lookback=20)
    for d, (pb, ps, pr) in probs.items():
        assert math.isclose(pb + ps + pr, 1.0, abs_tol=1e-9), f"{d}: {pb}+{ps}+{pr}"
