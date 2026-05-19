"""Path coverage for the Buy strategy. We feed synthetic OHLC so we can
predict the exit outcome day-by-day, then assert the trade list matches."""
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


def _sigma_for(bars):
    # daily H/L spreads of our fixtures, sample stdev
    from statistics import stdev
    return stdev([b.high - b.low for b in bars])


def test_intraday_take_profit():
    """Today opens dipping below prev close enough to hit entry_limit and
    rallies through tp_price the same day."""
    # 5 warmup bars give a known sigma. Then day 6 is the trade day.
    # Use spreads that produce sigma = 1.0 exactly.
    # spreads = [0, 2, 0, 2, 0] -> stdev = 1.0954... rather messy. Easier:
    # spreads = [1, 1, 1, 3, 1] -> stdev exists. Let's compute it then use it.
    warmup = [
        (100, 101, 100, 100.5),  # spread 1
        (100, 101, 100, 100.5),  # spread 1
        (100, 101, 100, 100.5),  # spread 1
        (100, 103, 100, 100.5),  # spread 3
        (100, 101, 100, 100.5),  # spread 1
    ]
    bars = make_bars(*warmup)
    sigma = _sigma_for(bars)
    # entry_limit = prev_close - 1*sigma = 100.5 - sigma
    # tp_price    = prev_close + 0.5*sigma
    entry_limit = 100.5 - sigma
    tp_price = 100.5 + 0.5 * sigma
    # Day 6 must: low <= entry_limit AND high >= tp_price
    day6 = (100.5, tp_price + 0.10, entry_limit - 0.05, 100.5)
    bars.append(Bar(date(2026, 1, 11), *day6))

    trades = simulate_buy(bars, PARAMS)
    fills = [t for t in trades if t.filled]
    assert len(fills) >= 1
    # the last fill (day 6) should be intraday TP
    last = fills[-1]
    assert last.exit_reason == ExitReason.INTRADAY_TP
    assert last.intraday_tp is True
    assert last.days_held == 0
    assert last.pnl_usd is not None and last.pnl_usd > 0


def test_overnight_take_profit():
    """Entry fills day 6, no same-day TP, then day 7 high crosses tp_price."""
    warmup = [(100, 101, 100, 100.5)] * 4 + [(100, 103, 100, 100.5)]
    bars = make_bars(*warmup)
    sigma = _sigma_for(bars)
    entry_limit = 100.5 - sigma
    tp_price = 100.5 + 0.5 * sigma
    stop_price = entry_limit - 3.0 * sigma

    # Day 6: dips to fill, but high stays below tp -> Open
    bars.append(Bar(date(2026, 1, 11), 100.4, tp_price - 0.5, entry_limit - 0.05, 100.4))
    # Day 7: high crosses tp_price
    bars.append(Bar(date(2026, 1, 12), 100.5, tp_price + 0.10, 100.0, 100.6))
    # Pad more days so window scan doesn't hit end-of-bars
    for i in range(2, 25):
        bars.append(Bar(date(2026, 1, 11) + timedelta(days=i), 100.5, 101.0, 99.0, 100.5))

    trades = simulate_buy(bars, PARAMS)
    # the trade entered on day index 5 (the new day 6 we added)
    entry = trades[4]  # trades start at i=1 -> index 0 is for bar idx 1; bar idx 5 -> trades[4]
    assert entry.filled
    assert entry.exit_reason == ExitReason.OVERNIGHT_TP
    assert entry.days_held == 1
    assert entry.pnl_usd is not None and entry.pnl_usd > 0


def test_overnight_stop_loss():
    warmup = [(100, 101, 100, 100.5)] * 4 + [(100, 103, 100, 100.5)]
    bars = make_bars(*warmup)
    sigma = _sigma_for(bars)
    entry_limit = 100.5 - sigma
    stop_price = entry_limit - 3.0 * sigma

    # Day 6 entry fills, no intraday TP
    bars.append(Bar(date(2026, 1, 11), 100.4, 100.45, entry_limit - 0.05, 100.4))
    # Day 7: low crashes through stop_price
    bars.append(Bar(date(2026, 1, 12), 100.4, 100.5, stop_price - 0.10, 99.0))
    for i in range(2, 25):
        bars.append(Bar(date(2026, 1, 11) + timedelta(days=i), 100.5, 100.6, 100.4, 100.5))

    trades = simulate_buy(bars, PARAMS)
    entry = trades[4]
    assert entry.filled
    assert entry.exit_reason == ExitReason.STOP
    assert entry.days_held == 1
    assert entry.pnl_usd is not None and entry.pnl_usd < 0


def test_no_fill():
    """Day's range never touches entry_limit -> no trade."""
    bars = make_bars(*([(100, 101, 100, 100.5)] * 5))
    sigma = _sigma_for(bars)
    entry_limit = 100.5 - sigma
    bars.append(Bar(date(2026, 1, 11), 100.5, 101.0, entry_limit + 0.5, 100.7))
    trades = simulate_buy(bars, PARAMS)
    assert trades[-1].filled is False
    assert trades[-1].exit_reason == ExitReason.NONE
    assert trades[-1].pnl_usd is None


def test_day_max_exit():
    """Neither TP nor stop hits within window; exits at close of day +24."""
    warmup = [(100, 101, 100, 100.5)] * 4 + [(100, 103, 100, 100.5)]
    bars = make_bars(*warmup)
    sigma = _sigma_for(bars)
    entry_limit = 100.5 - sigma
    tp_price = 100.5 + 0.5 * sigma
    stop_price = entry_limit - 3.0 * sigma
    # Entry on day 6
    bars.append(Bar(date(2026, 1, 11), 100.4, 100.45, entry_limit - 0.05, 100.4))
    # 24+ flat-ish days that stay between stop and TP
    for i in range(1, 30):
        d = date(2026, 1, 11) + timedelta(days=i)
        bars.append(Bar(d, 100.4, tp_price - 0.05, stop_price + 0.05, 100.4))

    trades = simulate_buy(bars, PARAMS)
    entry = trades[4]
    assert entry.filled
    assert entry.exit_reason == ExitReason.DAY_MAX
    assert entry.days_held == PARAMS.holding_max


def test_buy_signal_basic():
    bars = make_bars(*([(100, 101, 100, 100.5)] * 5))
    sig = buy_signal(bars, PARAMS, "TEST")
    assert sig.symbol == "TEST"
    assert sig.side == "buy"
    assert sig.entry_limit < sig.prev_close
    assert sig.tp_price > sig.prev_close
    assert sig.stop_price < sig.entry_limit
    assert sig.shares > 0


def test_buy_signal_needs_two_bars():
    bars = make_bars((100, 101, 100, 100.5))
    with pytest.raises(ValueError):
        buy_signal(bars, PARAMS, "TEST")
