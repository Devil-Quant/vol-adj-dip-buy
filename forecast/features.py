"""Daily features for 'predict the day at its open'. Every feature for day t
uses ONLY information available at t's OPEN: prior bars (shifted by 1) plus
today's open (the gap). No look-ahead into today's high/low/close."""
from __future__ import annotations

from typing import Sequence

import pandas as pd

FEATURE_COLS = ["gap", "prior_range", "range_ewma", "ret_1", "ret_5",
                "vol_5", "vol_20", "dist_ma20", "dow"]
# volume features (added in v2) — kept separate so the harness can compare
# price-only vs price+volume. All use ONLY prior-day volume (no look-ahead).
VOLUME_COLS = ["rvol", "vol_trend", "dvol_z"]


def _frame(bars: Sequence) -> pd.DataFrame:
    df = pd.DataFrame([{"date": b.d, "open": b.open, "high": b.high,
                        "low": b.low, "close": b.close,
                        "volume": getattr(b, "volume", 0.0)} for b in bars])
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

    # volume features — only prior-day volume is known at today's open, so every
    # term is shift(1). rvol = yesterday's volume vs its 20d average; vol_trend =
    # 5d vs 20d volume; dvol_z = z-score of yesterday's dollar volume.
    v = df["volume"]
    avg20 = v.rolling(20).mean()
    feat["rvol"] = v.shift(1) / avg20.shift(1)
    feat["vol_trend"] = v.rolling(5).mean().shift(1) / avg20.shift(1)
    dollar = c * v
    d_shift = dollar.shift(1)
    feat["dvol_z"] = (d_shift - d_shift.rolling(20).mean()) / d_shift.rolling(20).std()
    return feat
