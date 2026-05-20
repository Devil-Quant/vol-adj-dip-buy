"""Anti-overfit validation of a TP/SL grid: out-of-sample split, walk-forward,
and Monte Carlo bootstrap. All operate on the precomputed grid from
optimizer.run_grid (trades tagged by entry-date), so no re-running."""
from __future__ import annotations

import random
from datetime import date, timedelta

from backtest.optimizer import best_combo, window_stats, closed_pnls


def date_axis(grid: dict) -> list[date]:
    ds: set = set()
    for recs in grid.values():
        for r in recs:
            ds.add(r.entry_date)
    return sorted(ds)


def oos_evaluate(grid: dict, frac: float = 0.7) -> dict | None:
    """Optimize on the first `frac` of the date range; test the chosen params
    ONCE on the held-out remainder."""
    dates = date_axis(grid)
    if len(dates) < 20:
        return None
    split = dates[int(len(dates) * frac)]
    is_best, _ = best_combo(grid, start=dates[0], end=split)
    if is_best is None:
        return None
    key = (is_best.limit_mult, is_best.stop_mult)
    oos = window_stats(*key, grid[key], start=_next(split), end=dates[-1])
    return {"split_date": split, "is": is_best, "oos": oos}


def walk_forward(grid: dict, is_days: int = 180, oos_days: int = 60,
                 step_days: int = 60) -> dict | None:
    """Roll IS->OOS windows: pick best params on each IS window, evaluate on the
    following OOS window, and collect the OOS trades (the honest track record)."""
    dates = date_axis(grid)
    if not dates:
        return None
    start, end = dates[0], dates[-1]
    folds = []
    oos_pnls: list[float] = []
    cur = start
    while True:
        is_end = cur + timedelta(days=is_days)
        oos_end = is_end + timedelta(days=oos_days)
        if is_end >= end:
            break
        best, _ = best_combo(grid, start=cur, end=is_end)
        if best is not None:
            key = (best.limit_mult, best.stop_mult)
            oos = window_stats(*key, grid[key], start=_next(is_end), end=oos_end)
            oos_pnls.extend(closed_pnls(grid[key], start=_next(is_end), end=oos_end))
            folds.append({
                "is_start": cur, "is_end": is_end, "oos_end": oos_end,
                "params": key, "is_pnl": best.total_pnl, "oos_pnl": oos.total_pnl,
                "oos_trades": oos.n_trades, "oos_win_rate": oos.win_rate,
            })
        cur = cur + timedelta(days=step_days)
        if cur >= end:
            break
    stitched_total = sum(f["oos_pnl"] for f in folds)
    return {"folds": folds, "oos_pnls": oos_pnls, "stitched_oos_pnl": stitched_total}


def monte_carlo(pnls: list[float], n: int = 2000, seed: int = 42) -> dict | None:
    """Bootstrap-resample the trade P&Ls (with replacement) -> distribution of
    total P&L and max drawdown, plus probability of profit."""
    if not pnls:
        return None
    rng = random.Random(seed)
    k = len(pnls)
    totals, dds = [], []
    for _ in range(n):
        sample = [pnls[rng.randrange(k)] for _ in range(k)]
        totals.append(sum(sample))
        dds.append(_max_drawdown(sample))
    totals.sort()
    dds.sort()
    return {
        "n": n, "trades": k,
        "median_total": _pct(totals, 0.5),
        "p5_total": _pct(totals, 0.05),
        "p95_total": _pct(totals, 0.95),
        "prob_profit": sum(1 for t in totals if t > 0) / n,
        "median_max_drawdown": _pct(dds, 0.5),
        "p95_max_drawdown": _pct(dds, 0.05),  # 5th pct = deepest 5% drawdown
    }


def _next(d: date) -> date:
    return d + timedelta(days=1)


def _pct(sorted_arr: list[float], p: float) -> float:
    if not sorted_arr:
        return 0.0
    return sorted_arr[int(p * (len(sorted_arr) - 1))]


def _max_drawdown(pnls: list[float]) -> float:
    equity = peak = mdd = 0.0
    for p in pnls:
        equity += p
        peak = max(peak, equity)
        mdd = min(mdd, equity - peak)
    return mdd
