"""VIX implied-vol feature, aligned for 'predict the SPY day at its open'. The
implied input known at SPY's open on day t is the VIX close from t-1, converted
to an implied daily sigma (VIX is annualized %). No look-ahead."""
from __future__ import annotations

from math import sqrt
from typing import Sequence

import pandas as pd

TRADING_DAYS = 252


def build_vix_feature(vix_bars: Sequence) -> pd.DataFrame:
    """Return DataFrame[date, vix_implied] where
    vix_implied_t = VIX_close_{t-1} / 100 / sqrt(252) (prior-day implied daily
    sigma). Row 0 is NaN (no prior). No look-ahead."""
    df = pd.DataFrame([{"date": b.d, "vix_close": b.close} for b in vix_bars])
    df = df.sort_values("date").reset_index(drop=True)
    df["vix_implied"] = df["vix_close"].shift(1) / 100.0 / sqrt(TRADING_DAYS)
    return df[["date", "vix_implied"]]


def merge_vix(spy_frame: pd.DataFrame, vix_bars: Sequence) -> pd.DataFrame:
    """Inner-merge the VIX implied feature onto a SPY feature/target frame by
    date (drops dates without a VIX match)."""
    return spy_frame.merge(build_vix_feature(vix_bars), on="date", how="inner")
