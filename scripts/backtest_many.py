"""Backtest a watchlist. CLI:
    python scripts/backtest_many.py data/symbols.txt --days 100
The symbols file is one ticker per line, blank / `#` lines ignored.
"""
from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd

from backtest.engine import run_backtest
from backtest.reporter import summary_row, SCREENED_SUMMARY_COLUMNS
from clients.yfinance_client import fetch_ohlc
from config.settings import DEFAULT_BUY, DEFAULT_SHORT


def load_symbols(path: Path) -> list[str]:
    out: list[str] = []
    for line in path.read_text().splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        out.append(s.upper())
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Backtest a list of symbols on both sides")
    ap.add_argument("symbols_file")
    ap.add_argument("--days", type=int, default=100)
    ap.add_argument("--sides", default="buy,short", help="comma-separated subset of buy,short")
    ap.add_argument("--out", default=None, help="output CSV path; default data/screened_summary_<date>.csv")
    args = ap.parse_args()

    symbols = load_symbols(Path(args.symbols_file))
    if not symbols:
        print(f"No symbols in {args.symbols_file}", file=sys.stderr)
        return 1
    print(f"Loaded {len(symbols)} symbols from {args.symbols_file}")

    sides = [s.strip() for s in args.sides.split(",") if s.strip()]
    rows: list[dict] = []
    today = date.today()

    for sym in symbols:
        try:
            bars = fetch_ohlc(sym, args.days)
        except Exception as e:
            print(f"[skip] {sym}: {e}")
            continue
        for side in sides:
            params = DEFAULT_BUY if side == "buy" else DEFAULT_SHORT
            params_with_days = type(params)(
                side=params.side,
                sigma_mult=params.sigma_mult, limit_mult=params.limit_mult,
                stop_mult=params.stop_mult, lookback_days=args.days,
                holding_window=params.holding_window, holding_max=params.holding_max,
                order_size_usd=params.order_size_usd,
            )
            try:
                result = run_backtest(sym, bars, params_with_days)
            except Exception as e:
                print(f"[err] {sym} {side}: {e}")
                continue
            row = summary_row(result, asof=today)
            rows.append(row)
            print(
                f"  {sym:<6} {side:<5} total=${row['strategy_pnl_total']:>+10,.2f} "
                f"intraday={row['intraday_count']:>2} overnight={row['overnight_count']:>2} "
                f"(TP={row['overnight_tp_count']} stop={row['stop_count']} day_max={row['day_max_count']})"
            )

    if not rows:
        print("No rows produced.", file=sys.stderr)
        return 1
    df = pd.DataFrame(rows, columns=SCREENED_SUMMARY_COLUMNS)
    out = Path(args.out) if args.out else Path("data") / f"screened_summary_{today.isoformat()}.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out, index=False)
    print(f"\nWrote screened summary -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
