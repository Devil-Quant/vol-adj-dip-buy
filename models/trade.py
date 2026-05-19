"""Dataclasses shared by the strategies, backtest engine, and reporter."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from typing import Optional


class ExitReason(str, Enum):
    INTRADAY_TP = "intraday_tp"      # same-day take-profit fill
    OVERNIGHT_TP = "overnight_tp"    # next-N-day take-profit fill
    STOP = "stop"                    # stop-loss fill within window
    DAY_MAX = "day_max"              # forced exit at close on holding_max day
    NONE = "none"                    # entry never filled


@dataclass
class Trade:
    """One signal-day's outcome. May be a no-fill, intraday round-trip, or
    multi-day position closed by TP / stop / day-max."""
    entry_date: date
    side: str                        # "buy" or "short"
    entry_limit: float               # the price we were trying to fill at
    filled: bool                     # did the day's range cross entry_limit?
    intraday_tp: bool                # did same-day reach TP?
    exit_reason: ExitReason
    tp_price: Optional[float] = None
    stop_price: Optional[float] = None
    exit_price: Optional[float] = None
    exit_date: Optional[date] = None
    shares: Optional[float] = None
    pnl_usd: Optional[float] = None  # realized PnL on the order size
    days_held: Optional[int] = None  # 0 for intraday, N for overnight


@dataclass
class BacktestResult:
    """All trades plus the four aggregate buckets that match the spreadsheet's
    `BUY Screened Summary` columns."""
    symbol: str
    side: str
    trading_days: int
    sigma: float                     # rolling stdev of daily H/L spread
    trades: list[Trade] = field(default_factory=list)

    # buckets matching Excel AA3 / AE3 / AF3 / AG3
    intraday_pnl: float = 0.0
    stop_pnl: float = 0.0
    overnight_tp_pnl: float = 0.0
    day_max_pnl: float = 0.0

    intraday_count: int = 0
    overnight_count: int = 0         # all positions still open at end of day
    stop_count: int = 0
    overnight_tp_count: int = 0
    day_max_count: int = 0

    buy_and_hold_pct: Optional[float] = None  # for the diff column

    @property
    def total_pnl(self) -> float:
        return self.intraday_pnl + self.stop_pnl + self.overnight_tp_pnl + self.day_max_pnl

    @property
    def strategy_pct(self) -> float:
        if not self.trades:
            return 0.0
        # use the order_size from the first filled trade; all trades share it
        for t in self.trades:
            if t.filled and t.shares and t.shares > 0 and t.entry_limit > 0:
                order_size = t.shares * t.entry_limit
                if order_size > 0:
                    return self.total_pnl / order_size
        return 0.0


@dataclass
class Signal:
    """Forward-test: today's actionable order parameters."""
    symbol: str
    side: str                        # "buy" or "short"
    asof_date: date                  # the prior close date these numbers use
    prev_close: float
    sigma: float
    entry_limit: float
    tp_price: float
    stop_price: float
    shares: float
