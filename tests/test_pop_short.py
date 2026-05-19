"""Mirror of test_dip_buy for the Short strategy."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from statistics import stdev

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


def _sigma_for(bars):
    return stdev([b.high - b.low for b in bars])


def test_intraday_cover():
    """Today rallies above prev close enough to fill short, then dips back
    through cover (tp) price the same day."""
    warmup = [(100, 101, 100, 100.5)] * 4 + [(100, 103, 100, 100.5)]
    bars = make_bars(*warmup)
    sigma = _sigma_for(bars)
    entry_limit = 100.5 + sigma   # short entry above
    tp_price = entry_limit - 0.75 * sigma
    # Day 6: high crosses entry_limit, low dips below tp_price -> intraday cover
    bars.append(Bar(date(2026, 1, 11), 100.5, entry_limit + 0.10, tp_price - 0.05, 100.5))
    trades = simulate_short(bars, PARAMS)
    last = trades[-1]
    assert last.filled is True
    assert last.exit_reason == ExitReason.INTRADAY_TP
    assert last.days_held == 0
    assert last.pnl_usd is not None and last.pnl_usd > 0


def test_overnight_cover():
    warmup = [(100, 101, 100, 100.5)] * 4 + [(100, 103, 100, 100.5)]
    bars = make_bars(*warmup)
    sigma = _sigma_for(bars)
    entry_limit = 100.5 + sigma
    tp_price = entry_limit - 0.75 * sigma
    stop_price = entry_limit + 3.0 * sigma
    # Day 6 fills short, no intraday cover
    bars.append(Bar(date(2026, 1, 11), 100.5, entry_limit + 0.10, tp_price + 0.10, 100.6))
    # Day 7 dips below tp_price
    bars.append(Bar(date(2026, 1, 12), 100.6, 100.7, tp_price - 0.10, 100.5))
    for i in range(2, 25):
        bars.append(Bar(date(2026, 1, 11) + timedelta(days=i), 100.5, 100.6, 100.4, 100.5))
    trades = simulate_short(bars, PARAMS)
    entry = trades[4]
    assert entry.filled and entry.exit_reason == ExitReason.OVERNIGHT_TP
    assert entry.days_held == 1
    assert entry.pnl_usd is not None and entry.pnl_usd > 0


def test_overnight_stop():
    warmup = [(100, 101, 100, 100.5)] * 4 + [(100, 103, 100, 100.5)]
    bars = make_bars(*warmup)
    sigma = _sigma_for(bars)
    entry_limit = 100.5 + sigma
    tp_price = entry_limit - 0.75 * sigma
    stop_price = entry_limit + 3.0 * sigma
    # Day 6 short fills, no intraday cover
    bars.append(Bar(date(2026, 1, 11), 100.5, entry_limit + 0.10, tp_price + 0.10, 100.6))
    # Day 7 rips through stop
    bars.append(Bar(date(2026, 1, 12), 100.6, stop_price + 0.10, 100.5, stop_price))
    for i in range(2, 25):
        bars.append(Bar(date(2026, 1, 11) + timedelta(days=i), 100.5, 100.6, 100.4, 100.5))
    trades = simulate_short(bars, PARAMS)
    entry = trades[4]
    assert entry.filled and entry.exit_reason == ExitReason.STOP
    assert entry.pnl_usd is not None and entry.pnl_usd < 0


def test_no_fill():
    bars = make_bars(*([(100, 101, 100, 100.5)] * 5))
    sigma = _sigma_for(bars)
    entry_limit = 100.5 + sigma
    bars.append(Bar(date(2026, 1, 11), 100.5, entry_limit - 0.1, 100.0, 100.4))
    trades = simulate_short(bars, PARAMS)
    assert trades[-1].filled is False
    assert trades[-1].exit_reason == ExitReason.NONE


def test_day_max_exit():
    warmup = [(100, 101, 100, 100.5)] * 4 + [(100, 103, 100, 100.5)]
    bars = make_bars(*warmup)
    sigma = _sigma_for(bars)
    entry_limit = 100.5 + sigma
    tp_price = entry_limit - 0.75 * sigma
    stop_price = entry_limit + 3.0 * sigma
    bars.append(Bar(date(2026, 1, 11), 100.5, entry_limit + 0.10, tp_price + 0.10, 100.6))
    for i in range(1, 30):
        d = date(2026, 1, 11) + timedelta(days=i)
        bars.append(Bar(d, 100.6, stop_price - 0.05, tp_price + 0.05, 100.6))
    trades = simulate_short(bars, PARAMS)
    entry = trades[4]
    assert entry.filled and entry.exit_reason == ExitReason.DAY_MAX
    assert entry.days_held == PARAMS.holding_max


def test_short_signal_basic():
    bars = make_bars(*([(100, 101, 100, 100.5)] * 5))
    sig = short_signal(bars, PARAMS, "TEST")
    assert sig.symbol == "TEST"
    assert sig.side == "short"
    assert sig.entry_limit > sig.prev_close
    assert sig.tp_price < sig.entry_limit
    assert sig.stop_price > sig.entry_limit
    assert sig.shares > 0
