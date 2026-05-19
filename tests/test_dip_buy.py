"""Path coverage for the Buy strategy.

We inject a fixed `sigma` so test fixtures don't have to predict the H/L
stdev of the whole bar list. With `sigma=1.0`, entry / TP / stop fall on
crisp integer boundaries which make the OHLC design obvious.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

import pytest

from config.settings import StrategyParams
from models.trade import ExitReason
from strategies.dip_buy import simulate_buy, buy_signal


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
    side="buy", sigma_mult=1.0, limit_mult=0.5, stop_mult=3.0,
    lookback_days=20, holding_window=20, holding_max=24, order_size_usd=100_000.0,
)
SIGMA = 1.0  # injected for all tests
# With prev_close=100 and SIGMA=1:
#   entry_limit = 99
#   tp_price    = 100.5
#   stop_price  = 96


def test_intraday_take_profit():
    """Trade day's range covers BOTH entry_limit (99) and tp_price (100.5)."""
    bars = make_bars(
        (100, 101, 99, 100),     # warmup day t=0; prev_close for trade day below
        (100, 101, 98.5, 100),   # trade day: low=98.5 (<99 entry), high=101 (>100.5 tp) -> intraday TP
    )
    trades = simulate_buy(bars, PARAMS, sigma_override=SIGMA)
    last = trades[-1]
    assert last.filled is True
    assert last.exit_reason == ExitReason.INTRADAY_TP
    assert last.intraday_tp is True
    assert last.days_held == 0
    # PnL = (tp - entry) * shares = (100.5 - 99) * (100000/99) ~ 1515.15
    assert last.pnl_usd is not None and last.pnl_usd == pytest.approx(1515.15, abs=0.1)


def test_overnight_take_profit():
    """Trade day fills but its high stays below tp. Day t+1 crosses tp."""
    bars = make_bars(
        (100, 101, 99, 100),     # warmup
        (100, 100.2, 98.5, 100), # trade day: fills (low<99), high=100.2 < tp=100.5 -> open
        (100, 101.0, 99.5, 100), # day +1: high=101 >= tp=100.5 -> overnight TP
        (100, 100, 99.5, 100),
    )
    trades = simulate_buy(bars, PARAMS, sigma_override=SIGMA)
    entry = trades[0]  # index 0 = bar i=1, which is the trade day
    assert entry.filled is True
    assert entry.intraday_tp is False
    assert entry.exit_reason == ExitReason.OVERNIGHT_TP
    assert entry.days_held == 1
    assert entry.pnl_usd is not None and entry.pnl_usd > 0


def test_overnight_stop_loss():
    """Trade day fills, high stays below tp, day +1 crashes below stop=96."""
    bars = make_bars(
        (100, 101, 99, 100),     # warmup
        (100, 100.2, 98.5, 100), # trade day: fills, open
        (100, 100, 95.5, 96),    # day +1: low=95.5 < stop=96 -> STOP hits
        (100, 100, 95, 95),
    )
    trades = simulate_buy(bars, PARAMS, sigma_override=SIGMA)
    entry = trades[0]
    assert entry.filled is True
    assert entry.exit_reason == ExitReason.STOP
    assert entry.days_held == 1
    assert entry.pnl_usd is not None and entry.pnl_usd < 0
    # PnL = (96 - 99) * shares = -3 * (100000/99) ~ -3030.30
    assert entry.pnl_usd == pytest.approx(-3030.30, abs=0.1)


def test_no_fill():
    bars = make_bars(
        (100, 101, 99, 100),     # warmup
        (100, 101, 99.5, 100),   # trade day: low=99.5 > entry=99 -> miss
    )
    trades = simulate_buy(bars, PARAMS, sigma_override=SIGMA)
    last = trades[-1]
    assert last.filled is False
    assert last.exit_reason == ExitReason.NONE
    assert last.pnl_usd is None


def test_day_max_exit():
    """Neither TP nor stop hits within window; exit at close of day +24."""
    bars = make_bars((100, 101, 99, 100))         # warmup
    bars.append(Bar(date(2026, 1, 6), 100, 100.2, 98.5, 100))  # trade day, opens position
    # 24 future days all staying between stop=96 and tp=100.5
    for i in range(1, 25):
        bars.append(Bar(date(2026, 1, 6) + timedelta(days=i), 99, 100.2, 98, 99.5))
    trades = simulate_buy(bars, PARAMS, sigma_override=SIGMA)
    entry = trades[0]  # the only true entry
    assert entry.filled is True
    assert entry.exit_reason == ExitReason.DAY_MAX
    assert entry.days_held == PARAMS.holding_max
    # exit_price = close of day +24 = 99.5
    assert entry.exit_price == pytest.approx(99.5, abs=0.01)


def test_buy_signal_basic():
    bars = make_bars((100, 101, 99, 100))
    sig = buy_signal(bars, PARAMS, "TEST", sigma_override=SIGMA)
    assert sig.symbol == "TEST"
    assert sig.side == "buy"
    assert sig.prev_close == 100
    assert sig.entry_limit == pytest.approx(99.0, abs=1e-6)
    assert sig.tp_price == pytest.approx(100.5, abs=1e-6)
    assert sig.stop_price == pytest.approx(96.0, abs=1e-6)
    assert sig.shares == pytest.approx(100_000 / 99.0, abs=0.01)


def test_buy_signal_needs_two_bars_for_sigma():
    """Without sigma_override, the signal cannot compute stdev from <2 bars."""
    bars = make_bars((100, 101, 99, 100))  # 1 bar
    with pytest.raises(ValueError):
        buy_signal(bars, PARAMS, "TEST")  # no override -> must fail
