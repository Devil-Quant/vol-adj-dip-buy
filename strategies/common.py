"""Shared math for dip_buy and pop_short. No I/O."""
from __future__ import annotations

from dataclasses import dataclass
from statistics import stdev
from typing import Sequence


@dataclass(frozen=True)
class OhlcView:
    """Minimal OHLC interface so strategies don't depend on the client.
    Tests pass plain dataclasses; production passes `clients.OhlcBar` (which
    has the same field names)."""
    d: object
    open: float
    high: float
    low: float
    close: float


def hl_spread_stdev(bars: Sequence) -> float:
    """Sample stdev (ddof=1) of daily High-minus-Low — mirrors Excel STDEV
    applied to column L (`H/L Spread`) on the Buy / Short tabs.

    Bars need .high and .low attrs (works with `OhlcBar` or `OhlcView`).
    Raises ValueError if fewer than 2 bars."""
    spreads = [float(b.high) - float(b.low) for b in bars]
    if len(spreads) < 2:
        raise ValueError(f"need >=2 bars for stdev, got {len(spreads)}")
    return stdev(spreads)
