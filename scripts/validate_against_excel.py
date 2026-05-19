"""Sanity-check: run NVDA Buy backtest with spreadsheet defaults and print
the four totals next to the Excel reference. Small drift expected because
yfinance may return slightly different dates than the spreadsheet's snapshot."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backtest.engine import run_backtest
from backtest.reporter import print_summary
from clients.yfinance_client import fetch_ohlc
from config.settings import DEFAULT_BUY


EXCEL_REFERENCE = {
    "symbol": "NVDA",
    "side": "buy",
    "snapshot_date": "2026-05-15",
    "trading_days": 69,
    "intraday_count": 13,
    "intraday_pnl": 23_638.97,
    "overnight_count": 19,
    "overnight_tp_count": 13,
    "overnight_tp_pnl": 24_348.42,
    "stop_count": 6,
    "stop_pnl": -21_168.35,
    "day_max_count": 0,
    "day_max_pnl": 0.0,
    "total_pnl": 26_819.04,
    "buy_and_hold_pct": 0.1699,
    "strategy_pct": 0.2682,
}


def main() -> int:
    sym = EXCEL_REFERENCE["symbol"]
    bars = fetch_ohlc(sym, 100)
    print(f"Fetched {len(bars)} bars for {sym} ({bars[0].d} -> {bars[-1].d})")

    result = run_backtest(sym, bars, DEFAULT_BUY)
    print_summary(result)

    print("\n=== Excel reference (NVDA Buy, snapshot 2026-05-15) ===")
    for k, v in EXCEL_REFERENCE.items():
        print(f"  {k:<20} {v}")

    print("\n=== Comparison ===")
    diffs = {
        "intraday_pnl":       result.intraday_pnl - EXCEL_REFERENCE["intraday_pnl"],
        "overnight_tp_pnl":   result.overnight_tp_pnl - EXCEL_REFERENCE["overnight_tp_pnl"],
        "stop_pnl":           result.stop_pnl - EXCEL_REFERENCE["stop_pnl"],
        "day_max_pnl":        result.day_max_pnl - EXCEL_REFERENCE["day_max_pnl"],
        "total_pnl":          result.total_pnl - EXCEL_REFERENCE["total_pnl"],
    }
    for k, v in diffs.items():
        marker = "OK" if abs(v) < 5_000 else "WARN"
        print(f"  {k:<20} diff = ${v:>+12,.2f}   [{marker}]")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
