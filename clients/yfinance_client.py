"""Daily OHLC fetcher. No business logic — pure data access."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd
import yfinance as yf


CACHE_DIR = Path(__file__).resolve().parent.parent / "data" / "cache"


@dataclass(frozen=True)
class OhlcBar:
    d: date
    open: float
    high: float
    low: float
    close: float


def fetch_ohlc(symbol: str, days: int, *, use_cache: bool = True) -> list[OhlcBar]:
    """Fetch the most recent `days` calendar days of daily OHLC for `symbol`.

    Returns bars in chronological order. yfinance returns trading days only,
    so a `days=100` call yields ~69 bars depending on holidays.
    """
    symbol = symbol.strip().upper()
    if not symbol:
        raise ValueError("symbol must be non-empty")
    if days < 1:
        raise ValueError(f"days must be >= 1, got {days}")

    cache_file = CACHE_DIR / f"{symbol}_{days}d.parquet"
    if use_cache and cache_file.exists():
        age = datetime.now().timestamp() - cache_file.stat().st_mtime
        if age < 3_600:  # 1 hour
            df = pd.read_parquet(cache_file)
            return _df_to_bars(df)

    end = datetime.now()
    start = end - timedelta(days=days + 7)  # buffer for weekends / holidays
    df = yf.download(
        symbol,
        start=start.strftime("%Y-%m-%d"),
        end=end.strftime("%Y-%m-%d"),
        interval="1d",
        progress=False,
        auto_adjust=False,
        group_by="column",
    )
    if df is None or df.empty:
        raise RuntimeError(f"yfinance returned no data for {symbol}")
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
    df = df.tail(days)
    if use_cache:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        df.to_parquet(cache_file)
    return _df_to_bars(df)


def _df_to_bars(df: pd.DataFrame) -> list[OhlcBar]:
    bars: list[OhlcBar] = []
    for ts, row in df.iterrows():
        d_val = ts.date() if hasattr(ts, "date") else ts
        bars.append(
            OhlcBar(
                d=d_val,
                open=float(row["Open"]),
                high=float(row["High"]),
                low=float(row["Low"]),
                close=float(row["Close"]),
            )
        )
    return bars
