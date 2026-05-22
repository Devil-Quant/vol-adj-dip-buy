"""Daily features for 'predict the day at its open'. Every feature for day t
uses ONLY information available at t's OPEN: prior bars (shifted by 1) plus
today's open (the gap). No look-ahead into today's high/low/close."""
from __future__ import annotations

from typing import Sequence

import pandas as pd

FEATURE_COLS = ["gap", "prior_range", "range_ewma", "ret_1", "ret_5",
                "vol_5", "vol_20", "dist_ma20", "dow"]


def _frame(bars: Sequence) -> pd.DataFrame:
    df = pd.DataFrame([{"date": b.d, "open": b.open, "high": b.high,
                        "low": b.low, "close": b.close} for b in bars])
    return df.sort_values("date").reset_index(drop=True)


def build_features(bars: Sequence) -> pd.DataFrame:
    """Return a per-day feature frame (FEATURE_COLS) + 'date'. Rows with
    insufficient history have NaNs (drop upstream)."""
    df = _frame(bars)
    c = df["close"]
    prev_close = c.shift(1)                       # close_{t-1}
    ret = c.pct_change()                          # close-to-close return at t
    day_range = (df["high"] - df["low"]) / c      # that day's range %

    feat = pd.DataFrame({"date": df["date"]})
    feat["gap"] = (df["open"] - prev_close) / prev_close          # open_t vs close_{t-1}
    feat["prior_range"] = day_range.shift(1)                      # range of day t-1
    feat["range_ewma"] = day_range.shift(1).ewm(span=10, min_periods=5).mean()
    feat["ret_1"] = ret.shift(1)                                 # return of day t-1
    feat["ret_5"] = (prev_close / c.shift(6)) - 1.0              # 5-day momentum thru t-1
    feat["vol_5"] = ret.shift(1).rolling(5).std()               # vol of returns thru t-1
    feat["vol_20"] = ret.shift(1).rolling(20).std()
    ma20 = c.rolling(20).mean()
    feat["dist_ma20"] = (prev_close - ma20.shift(1)) / ma20.shift(1)
    feat["dow"] = pd.to_datetime(df["date"]).dt.dayofweek.astype(float)
    return feat
