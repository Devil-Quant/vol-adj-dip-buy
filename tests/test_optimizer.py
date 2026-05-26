"""Tests for the TP/SL grid optimizer windowing + RR filter (synthetic
TradeRecs — no IBKR needed)."""
from __future__ import annotations

from datetime import date, timedelta

from backtest.optimizer import (TradeRec, best_combo, closed_pnls,
                                combo_trades_daily, rr_ok, window_stats)
from clients import OhlcBar


def test_rr_ok_boundary():
    # reward/risk = (sigma_mult + limit) / stop <= max_rr
    assert rr_ok(1.0, 0.5, 1.0, 3.0)        # 1.5/1.0 = 1.5
    assert rr_ok(1.0, 2.0, 1.0, 3.0)        # 3.0/1.0 = 3.0 (boundary, allowed)
    assert not rr_ok(1.0, 2.5, 1.0, 3.0)    # 3.5/1.0 = 3.5 > 3
    assert rr_ok(1.0, 2.5, 1.5, 3.0)        # 3.5/1.5 = 2.33


def test_window_stats_totals_and_filters():
    recs = [
        TradeRec("A", date(2026, 1, 5), 100.0, True, False),
        TradeRec("A", date(2026, 1, 6), -50.0, False, False),
        TradeRec("A", date(2026, 2, 1), 200.0, True, False),
        TradeRec("A", date(2026, 2, 2), 0.0, False, True),   # still open -> excluded from total
    ]
    w = window_stats(0.5, 1.0, recs)
    assert w.n_trades == 3                  # closed only
    assert w.total_pnl == 250.0
    assert w.open_count == 1
    assert abs(w.win_rate - 2 / 3) < 1e-9
    assert w.worst == -50.0
    assert abs(w.expectancy - 250.0 / 3) < 1e-9


def test_window_stats_date_window():
    recs = [
        TradeRec("A", date(2026, 1, 5), 100.0, True, False),
        TradeRec("A", date(2026, 2, 1), 200.0, True, False),
    ]
    w = window_stats(0.5, 1.0, recs, start=date(2026, 1, 20))
    assert w.n_trades == 1 and w.total_pnl == 200.0


def test_best_combo_picks_max_total():
    grid = {
        (0.5, 1.0): [TradeRec("A", date(2026, 1, 5), 100.0, True, False)],
        (1.0, 1.0): [TradeRec("A", date(2026, 1, 5), 300.0, True, False)],
        (2.0, 1.0): [TradeRec("A", date(2026, 1, 5), -100.0, False, False)],
    }
    best, ranked = best_combo(grid)
    assert (best.limit_mult, best.stop_mult) == (1.0, 1.0)
    assert ranked[0].total_pnl == 300.0 and ranked[-1].total_pnl == -100.0


def test_closed_pnls_excludes_open():
    recs = [
        TradeRec("A", date(2026, 1, 5), 10.0, True, False),
        TradeRec("A", date(2026, 1, 6), 5.0, True, True),   # open
    ]
    assert closed_pnls(recs) == [10.0]


def test_combo_trades_daily_honors_allow_by_day():
    """sd['allow_by_day'] must be read by combo_trades_daily and passed through
    to simulate_buy, so disallowed days produce zero filled trades for that
    symbol."""
    # Build a 30-day series for two symbols where every day is a clean
    # intraday-TP setup: each day's low dips below prev_close-1*sigma and high
    # exceeds prev_close+0.5*sigma. With sigma=1.0 and prev_close=100:
    #   entry_limit=99, tp=100.5 — bar (open=100, high=101, low=98.5, close=100)
    def mk(start_d):
        bars = []
        for i in range(30):
            bars.append(OhlcBar(d=start_d + timedelta(days=i),
                                open=100.0, high=101.0, low=98.5, close=100.0))
        return bars

    bars_A = mk(date(2026, 1, 5))
    bars_B = mk(date(2026, 1, 5))
    # Symbol B's gate blocks everything; A's is unset (default = allow all).
    sd = {
        "A": {"daily": bars_A, "sigma_by_day": {b.d: 1.0 for b in bars_A}},
        "B": {"daily": bars_B, "sigma_by_day": {b.d: 1.0 for b in bars_B},
              "allow_by_day": {b.d: False for b in bars_B}},
    }
    recs = combo_trades_daily(sd, "buy", sigma_mult=1.0, limit_mult=0.5,
                              stop_mult=3.0, order_size=100_000.0, trailing=True)
    syms = {r.sym for r in recs}
    assert "A" in syms, "A should produce trades"
    assert "B" not in syms, "B should be fully gated out"
