"""3-state Markov regime model (bull / sideways / bear) for the dip-buy gate.

State at day k uses the trailing-`lookback` return ending at day k (>= bull
threshold -> bull, <= bear threshold -> bear, else sideways). The probability
vector predicted at row X is conditioned on state_{X-1} and the MLE transition
matrix built from pairs (state_{j-1}, state_j) for j = 1..X-1. So the gate's
decision for day X uses only data known at the close of day X-1 — no look-ahead.

The matrix shape: rows = current state, cols = next state. Probabilities are
row-normalized counts. Warm-up rows (fewer than `lookback + 30` prior labeled
days) return NaN."""
from __future__ import annotations

from typing import Sequence

import pandas as pd

STATES = ("bull", "sideways", "bear")
_MIN_TRANSITIONS = 30  # warm-up: skip until we have at least this many labeled days


def _frame(bars: Sequence) -> pd.DataFrame:
    df = pd.DataFrame([{"date": b.d, "open": b.open, "high": b.high,
                        "low": b.low, "close": b.close} for b in bars])
    return df.sort_values("date").reset_index(drop=True)


def _label(r: float, bull: float, bear: float) -> str | None:
    if pd.isna(r):
        return None
    if r >= bull:
        return "bull"
    if r <= bear:
        return "bear"
    return "sideways"


def build_markov_states(bars: Sequence, lookback: int = 20,
                        bull_thresh: float = 0.05,
                        bear_thresh: float = -0.05) -> pd.DataFrame:
    """Per-day output frame. Row X carries: the *input* state used to predict
    day X (= state at day X-1), and the predicted probabilities for day X."""
    df = _frame(bars)
    c = df["close"]
    ret = (c - c.shift(lookback)) / c.shift(lookback)
    states = [_label(r, bull_thresh, bear_thresh) for r in ret]

    n = len(df)
    out_state = [None] * n
    out_pb = [None] * n
    out_ps = [None] * n
    out_pr = [None] * n
    counts = {s: {t: 0 for t in STATES} for s in STATES}
    seen_transitions = 0
    for x in range(1, n):
        # Predict row x using state_{x-1} and counts of past transitions
        # (j-1 -> j) for j = 1..x-1 — NOT yet including (x-1 -> x).
        prev = states[x - 1]
        if prev is not None and seen_transitions >= _MIN_TRANSITIONS:
            row = counts[prev]
            total = row["bull"] + row["sideways"] + row["bear"]
            if total > 0:
                out_state[x] = prev
                out_pb[x] = row["bull"] / total
                out_ps[x] = row["sideways"] / total
                out_pr[x] = row["bear"] / total
        # Now extend the matrix with the (x-1 -> x) transition, which becomes
        # available at the close of day x (state_x uses close_x).
        curr = states[x]
        if prev is not None and curr is not None:
            counts[prev][curr] += 1
            seen_transitions += 1

    df["state"] = out_state
    df["p_bull"] = out_pb
    df["p_sideways"] = out_ps
    df["p_bear"] = out_pr
    df["edge"] = df["p_bull"] - df["p_bear"]
    return df[["date", "state", "p_bull", "p_sideways", "p_bear", "edge"]]


def state_probs_by_day(bars: Sequence, lookback: int = 20,
                       bull_thresh: float = 0.05,
                       bear_thresh: float = -0.05) -> dict:
    """Dict[date, (p_bull, p_sideways, p_bear)] aligned to the predicted day
    (analog of `backtest.engine.trailing_sigma_by_day`)."""
    df = build_markov_states(bars, lookback, bull_thresh, bear_thresh)
    out: dict = {}
    for _, r in df.iterrows():
        if pd.notna(r["p_bull"]):
            out[r["date"]] = (float(r["p_bull"]), float(r["p_sideways"]),
                              float(r["p_bear"]))
    return out


def markov_allow_by_day(bars: Sequence, lookback: int = 20,
                        bull_thresh: float = 0.05,
                        bear_thresh: float = -0.05,
                        theta: float = 0.0) -> dict:
    """Dict[date, bool] — the gate's primary entry point. allow[date_X] = True
    iff P_bull - P_bear > theta on the matrix as-of close-of-day-(X-1)."""
    df = build_markov_states(bars, lookback, bull_thresh, bear_thresh)
    out: dict = {}
    for _, r in df.iterrows():
        if pd.notna(r["edge"]):
            out[r["date"]] = bool(r["edge"] > theta)
    return out
