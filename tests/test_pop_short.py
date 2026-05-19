"""Path coverage for the Short strategy. Same sigma-injection technique as
test_dip_buy. With prev_close=100 and SIGMA=1:
  entry_limit = 101
  tp_price    = 100.25  (= 101 - 0.75 * 1)
  stop_price  = 104     (= 101 + 3 * 1)
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

import pytest

from config.settings import StrategyParams
from models.trade import ExitReason
from strategies.pop_short import simulate_short, short_signal


@dataclass
class Bar:
    d: date
    open: float
    high: float
    low: float
    close: float


def make_bars(*ohlc: tuple) -> list[Bar]:
    start = date(2026, 1, 5)
    return [Bar(d=start + timedelta(days=i), open=o, high=h, low=l, close=c)
            for i, (o, h, l, c) in enumerate(ohlc)]


PARAMS = StrategyParams(
    side="short", sigma_mult=1.0, limit_mult=0.75, stop_mult=3.0,
    lookback_days=20, holding_window=20, holding_max=24, order_size_usd=100_000.0,
)
SIGMA = 1.0


def test_intraday_cover():
    """Trade day high crosses entry (101); low dips below tp (100.25)."""
    bars = make_bars(
        (100, 101, 99, 100),
        (100, 101.5, 100.0, 100),  # high=101.5 > 101 entry; low=100 < 100.25 tp
    )
    trades = simulate_short(bars, PARAMS, sigma_override=SIGMA)
    last = trades[-1]
    assert last.filled is True
    assert last.exit_reason == ExitReason.INTRADAY_TP
    assert last.days_held == 0
    assert last.pnl_usd is not None and last.pnl_usd > 0


def test_overnight_cover():
    """Short fills day 1, no intraday cover, day +1 dips below tp."""
    bars = make_bars(
        (100, 101, 99, 100),
        (100, 101.5, 100.5, 100.8),  # fills; low=100.5 > 100.25 tp -> open
        (100, 101.0, 100.0, 100),    # day +1 dips below tp
        (100, 100, 99.5, 100),
    )
    trades = simulate_short(bars, PARAMS, sigma_override=SIGMA)
    entry = trades[0]
    assert entry.filled is True
    assert entry.exit_reason == ExitReason.OVERNIGHT_TP
    assert entry.days_held == 1
    assert entry.pnl_usd is not None and entry.pnl_usd > 0


def test_overnight_stop():
    """Short fills day 1, no intraday cover, day +1 rips through stop (104)."""
    bars = make_bars(
        (100, 101, 99, 100),
        (100, 101.5, 100.5, 100.8),  # short fills; high=101.5 < 104 stop -> open
        (100, 104.5, 101, 104),      # day +1 high=104.5 > 104 stop -> STOP hits
        (100, 105, 104, 104),
    )
    trades = simulate_short(bars, PARAMS, sigma_override=SIGMA)
    entry = trades[0]
    assert entry.filled is True
    assert entry.exit_reason == ExitReason.STOP
    assert entry.days_held == 1
    assert entry.pnl_usd is not None and entry.pnl_usd < 0


def test_no_fill():
    """Trade day high stays below entry."""
    bars = make_bars(
        (100, 101, 99, 100),
        (100, 100.5, 99.5, 100),
    )
    trades = simulate_short(bars, PARAMS, sigma_override=SIGMA)
    last = trades[-1]
    assert last.filled is False
    assert last.exit_reason == ExitReason.NONE


def test_day_max_exit():
    bars = make_bars((100, 101, 99, 100))
    bars.append(Bar(date(2026, 1, 6), 100, 101.5, 100.5, 100.8))  # short fills
    # 24 days in [100.30 .. 103.95] — above tp, below stop
    for i in range(1, 25):
        bars.append(Bar(date(2026, 1, 6) + timedelta(days=i), 101, 103.5, 100.30, 101))
    trades = simulate_short(bars, PARAMS, sigma_override=SIGMA)
    entry = trades[0]
    assert entry.filled is True
    assert entry.exit_reason == ExitReason.DAY_MAX
    assert entry.days_held == PARAMS.holding_max


def test_short_signal_basic():
    bars = make_bars((100, 101, 99, 100))
    sig = short_signal(bars, PARAMS, "TEST", sigma_override=SIGMA)
    assert sig.symbol == "TEST"
    assert sig.side == "short"
    assert sig.prev_close == 100
    assert sig.entry_limit == pytest.approx(101.0, abs=1e-6)
    assert sig.tp_price == pytest.approx(100.25, abs=1e-6)
    assert sig.stop_price == pytest.approx(104.0, abs=1e-6)
    assert sig.shares == pytest.approx(100_000 / 101.0, abs=0.01)
