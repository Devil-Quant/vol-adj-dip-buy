"""Prediction targets for the day, realized AFTER the open. These use today's
high/low/close — they are the OUTCOMES the model predicts, never fed back as
features (features.py only uses data through t-1 + today's open)."""
from __future__ import annotations

from typing import Sequence

import pandas as pd


def build_targets(bars: Sequence) -> pd.DataFrame:
    """Return per-day targets + 'date':
    - range: today's (high-low)/open  -> volatility/range target (regression)
    - up:    1 if today's close > open else 0 -> open->close direction (binary)
    """
    df = pd.DataFrame([{"date": b.d, "open": b.open, "high": b.high,
                        "low": b.low, "close": b.close} for b in bars])
    df = df.sort_values("date").reset_index(drop=True)
    tgt = pd.DataFrame({"date": df["date"]})
    tgt["range"] = (df["high"] - df["low"]) / df["open"]
    tgt["up"] = (df["close"] > df["open"]).astype(int)
    return tgt
