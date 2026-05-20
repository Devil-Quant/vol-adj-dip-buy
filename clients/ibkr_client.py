"""Daily OHLC fetcher via Interactive Brokers (ib_insync). No business logic.

Python 3.14 note: ib_insync's `eventkit` dependency calls the now-removed
implicit `asyncio.get_event_loop()` at import time, raising RuntimeError.
We install a current event loop BEFORE importing it. See exp-20260519-028.
"""
from __future__ import annotations

import asyncio

try:
    asyncio.get_event_loop()
except RuntimeError:
    asyncio.set_event_loop(asyncio.new_event_loop())

import atexit
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

import pandas as pd
from ib_insync import IB, Stock

from config.settings import IBKR_HOST, IBKR_PORT, IBKR_CLIENT_ID

CACHE_DIR = Path(__file__).resolve().parent.parent / "data" / "cache"
CACHE_TTL_SECONDS = 3_600  # 1 hour for "as of now" requests


@dataclass(frozen=True)
class OhlcBar:
    d: date
    open: float
    high: float
    low: float
    close: float


_ib: IB | None = None


def _get_ib() -> IB:
    """Lazily connect once and reuse the connection across fetches (IBKR has
    pacing limits, so one persistent client beats reconnecting per symbol)."""
    global _ib
    if _ib is not None and _ib.isConnected():
        return _ib
    ib = IB()
    ib.connect(IBKR_HOST, IBKR_PORT, clientId=IBKR_CLIENT_ID, timeout=15)
    _ib = ib
    return ib


def disconnect() -> None:
    global _ib
    if _ib is not None and _ib.isConnected():
        _ib.disconnect()
    _ib = None


atexit.register(disconnect)


def _end_datetime(end_date) -> str:
    """IBKR endDateTime format. '' means 'up to now'."""
    if end_date is None:
        return ""
    if isinstance(end_date, str):
        return f"{end_date.replace('-', '')} 23:59:59"
    return end_date.strftime("%Y%m%d 23:59:59")


def fetch_ohlc(symbol: str, days: int, *, end_date=None, use_cache: bool = True) -> list[OhlcBar]:
    """Fetch the most recent `days` TRADING sessions of daily OHLC for `symbol`.

    IBKR's `'{days} D'` duration returns that many trading sessions (not
    calendar days). `end_date` (str 'YYYY-MM-DD' or datetime.date) anchors the
    window end; None = up to now. Bars are returned chronological.
    """
    symbol = symbol.strip().upper()
    if not symbol:
        raise ValueError("symbol must be non-empty")
    if days < 1:
        raise ValueError(f"days must be >= 1, got {days}")

    end_tag = "now" if end_date is None else str(end_date)
    cache_file = CACHE_DIR / f"{symbol}_{days}d_{end_tag}.parquet"
    if use_cache and cache_file.exists():
        # Explicit end_date is immutable history -> cache forever. "now"
        # requests expire after CACHE_TTL_SECONDS.
        fresh = end_date is not None or (
            datetime.now().timestamp() - cache_file.stat().st_mtime < CACHE_TTL_SECONDS
        )
        if fresh:
            return _df_to_bars(pd.read_parquet(cache_file))

    ib = _get_ib()
    contract = Stock(symbol, "SMART", "USD")
    ib.qualifyContracts(contract)
    bars = ib.reqHistoricalData(
        contract,
        endDateTime=_end_datetime(end_date),
        durationStr=f"{days} D",
        barSizeSetting="1 day",
        whatToShow="TRADES",
        useRTH=True,
        formatDate=1,
    )
    if not bars:
        raise RuntimeError(f"IBKR returned no data for {symbol}")

    df = pd.DataFrame(
        [{"date": b.date, "Open": b.open, "High": b.high, "Low": b.low, "Close": b.close}
         for b in bars]
    )
    if use_cache:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        df.to_parquet(cache_file)
    return _df_to_bars(df)


def _df_to_bars(df: pd.DataFrame) -> list[OhlcBar]:
    bars: list[OhlcBar] = []
    for _, row in df.iterrows():
        raw = row["date"]
        d_val = raw.date() if isinstance(raw, datetime) else raw
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
