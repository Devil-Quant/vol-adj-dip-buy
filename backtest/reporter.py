"""Format BacktestResult into per-trade tables and screened-summary rows."""
from __future__ import annotations

from datetime import date
from typing import Iterable

import pandas as pd

from models.trade import BacktestResult, Trade


SCREENED_SUMMARY_COLUMNS = [
    "date_run",
    "symbol",
    "strategy",
    "strategy_pnl_total",
    "intraday_pnl",
    "stop_pnl",
    "overnight_tp_pnl",
    "day_max_pnl",
    "intraday_count",
    "overnight_count",
    "stop_count",
    "overnight_tp_count",
    "day_max_count",
    "trading_days",
    "buy_and_hold_pct",
    "strategy_pct",
    "diff_pct",
]


def trades_to_dataframe(trades: Iterable[Trade]) -> pd.DataFrame:
    rows = []
    for t in trades:
        rows.append({
            "entry_date": t.entry_date,
            "side": t.side,
            "entry_limit": t.entry_limit,
            "filled": t.filled,
            "intraday_tp": t.intraday_tp,
            "exit_reason": t.exit_reason.value,
            "tp_price": t.tp_price,
            "stop_price": t.stop_price,
            "exit_price": t.exit_price,
            "exit_date": t.exit_date,
            "shares": t.shares,
            "days_held": t.days_held,
            "pnl_usd": t.pnl_usd,
            "still_open": t.still_open,
            "gapped": t.gapped,
        })
    return pd.DataFrame(rows)


def summary_row(result: BacktestResult, *, asof: date | None = None) -> dict:
    """One row matching the spreadsheet's BUY Screened Summary tab."""
    diff = None
    if result.buy_and_hold_pct is not None:
        diff = result.strategy_pct - result.buy_and_hold_pct
    return {
        "date_run": asof.isoformat() if asof else date.today().isoformat(),
        "symbol": result.symbol,
        "strategy": result.side.upper(),
        "strategy_pnl_total": round(result.total_pnl, 2),
        "intraday_pnl": round(result.intraday_pnl, 2),
        "stop_pnl": round(result.stop_pnl, 2),
        "overnight_tp_pnl": round(result.overnight_tp_pnl, 2),
        "day_max_pnl": round(result.day_max_pnl, 2),
        "intraday_count": result.intraday_count,
        "overnight_count": result.overnight_count,
        "stop_count": result.stop_count,
        "overnight_tp_count": result.overnight_tp_count,
        "day_max_count": result.day_max_count,
        "trading_days": result.trading_days,
        "buy_and_hold_pct": round(result.buy_and_hold_pct, 4) if result.buy_and_hold_pct is not None else None,
        "strategy_pct": round(result.strategy_pct, 4),
        "diff_pct": round(diff, 4) if diff is not None else None,
    }


def print_summary(result: BacktestResult) -> None:
    print(f"\n=== {result.symbol} {result.side.upper()} ({result.trading_days} bars) ===")
    print(f"  sigma (H/L spread stdev): {result.sigma:.4f}")
    print(f"  intraday:     {result.intraday_count:>3} fills, ${result.intraday_pnl:>+12,.2f}")
    print(f"  overnight TP: {result.overnight_tp_count:>3} fills, ${result.overnight_tp_pnl:>+12,.2f}")
    print(f"  stop-out:     {result.stop_count:>3} fills, ${result.stop_pnl:>+12,.2f}")
    if result.day_max_count:
        print(f"  day-max:      {result.day_max_count:>3} fills, ${result.day_max_pnl:>+12,.2f}")
    n_gap = sum(1 for t in result.trades if getattr(t, "gapped", False))
    if result.stop_count:
        print(f"    (of which gapped through the stop: {n_gap})")
    print(f"  realized:     {result.intraday_count + result.stop_count + result.overnight_tp_count + result.day_max_count:>3} fills, ${result.realized_pnl:>+12,.2f}")
    if result.open_count:
        print(f"  still OPEN:   {result.open_count:>3} pos,   ${result.open_pnl:>+12,.2f}  (unrealized, marked at last close)")
    print(f"  TOTAL:        {result.intraday_count + result.overnight_count:>3} fills, ${result.total_pnl:>+12,.2f}")
    print(f"  strategy %:   {result.strategy_pct:+.4%}")
    if result.buy_and_hold_pct is not None:
        diff = result.strategy_pct - result.buy_and_hold_pct
        print(f"  buy & hold %: {result.buy_and_hold_pct:+.4%}")
        print(f"  diff:         {diff:+.4%}")
