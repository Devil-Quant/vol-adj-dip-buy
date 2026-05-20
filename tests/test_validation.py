"""Tests for OOS / walk-forward / Monte Carlo validation (synthetic grids)."""
from __future__ import annotations

from datetime import date, timedelta

from backtest.optimizer import TradeRec
from backtest.validation import oos_evaluate, walk_forward, monte_carlo, _max_drawdown


def _daily_dates(n: int, d0=date(2026, 1, 1)) -> list[date]:
    return [d0 + timedelta(days=i) for i in range(n)]


def test_max_drawdown():
    # equity: 10, 5, 0, 20 ; peak 10 ; deepest trough at 0 -> -10
    assert _max_drawdown([10, -5, -5, 20]) == -10
    assert _max_drawdown([5, 5, 5]) == 0
    assert _max_drawdown([-3, -2]) == -5


def test_monte_carlo_stats_and_determinism():
    pnls = [100.0, -50.0, 100.0, -50.0, 100.0]   # net +200
    mc = monte_carlo(pnls, n=1000, seed=1)
    assert mc["trades"] == 5
    assert 0.0 <= mc["prob_profit"] <= 1.0
    assert mc["p5_total"] <= mc["median_total"] <= mc["p95_total"]
    again = monte_carlo(pnls, n=1000, seed=1)
    assert again["median_total"] == mc["median_total"]    # deterministic with seed


def test_oos_holds_for_genuinely_good_combo():
    dates = _daily_dates(400)
    good = [TradeRec("A", d, 10.0, True, False) for d in dates]
    bad = [TradeRec("A", d, -1.0, False, False) for d in dates]
    grid = {(1.0, 1.0): good, (0.5, 1.0): bad}
    oos = oos_evaluate(grid, frac=0.7)
    assert oos is not None
    assert (oos["is"].limit_mult, oos["is"].stop_mult) == (1.0, 1.0)
    assert oos["oos"].total_pnl > 0          # the good combo holds out-of-sample


def test_walk_forward_picks_stable_good_combo():
    dates = _daily_dates(400)
    good = [TradeRec("A", d, 10.0, True, False) for d in dates]
    bad = [TradeRec("A", d, -1.0, False, False) for d in dates]
    grid = {(1.0, 1.0): good, (0.5, 1.0): bad}
    wf = walk_forward(grid, is_days=120, oos_days=40, step_days=40)
    assert wf is not None and len(wf["folds"]) >= 2
    assert all(f["params"] == (1.0, 1.0) for f in wf["folds"])   # stable choice
    assert wf["stitched_oos_pnl"] > 0
    assert len(wf["oos_pnls"]) > 0


def test_walk_forward_none_on_empty():
    assert walk_forward({}) is None
    assert oos_evaluate({}) is None
    assert monte_carlo([]) is None
