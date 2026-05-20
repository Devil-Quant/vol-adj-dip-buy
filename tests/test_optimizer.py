"""Tests for the TP/SL grid optimizer windowing + RR filter (synthetic
TradeRecs — no IBKR needed)."""
from __future__ import annotations

from datetime import date

from backtest.optimizer import TradeRec, rr_ok, window_stats, best_combo, closed_pnls


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
