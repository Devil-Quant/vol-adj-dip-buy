"""Backtest a single symbol. CLI:
    python scripts/backtest_one.py NVDA --side buy --days 100
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# allow running as `python scripts/backtest_one.py ...` from project root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd

from backtest.engine import run_backtest, run_backtest_intraday
from backtest.reporter import print_summary, trades_to_dataframe, summary_row
from clients import fetch_ohlc, fetch_intraday
from config.settings import DEFAULT_BUY, DEFAULT_SHORT, StrategyParams


def main() -> int:
    ap = argparse.ArgumentParser(description="Backtest one symbol")
    ap.add_argument("symbol")
    ap.add_argument("--side", choices=("buy", "short"), default="buy")
    ap.add_argument("--days", type=int, default=100)
    ap.add_argument("--sigma-mult", type=float, default=None)
    ap.add_argument("--limit-mult", type=float, default=None)
    ap.add_argument("--stop-mult", type=float, default=None)
    ap.add_argument("--order-size", type=float, default=None)
    ap.add_argument("--intraday", action="store_true",
                    help="resolve fills/exits on 5-min extended-hours bars (granular, realistic)")
    ap.add_argument("--end-date", default=None, help="anchor window end YYYY-MM-DD (default now)")
    ap.add_argument("--out-dir", default="data")
    args = ap.parse_args()

    base = DEFAULT_BUY if args.side == "buy" else DEFAULT_SHORT
    params = StrategyParams(
        side=args.side,
        sigma_mult=args.sigma_mult if args.sigma_mult is not None else base.sigma_mult,
        limit_mult=args.limit_mult if args.limit_mult is not None else base.limit_mult,
        stop_mult=args.stop_mult if args.stop_mult is not None else base.stop_mult,
        lookback_days=args.days,
        holding_window=base.holding_window,
        holding_max=base.holding_max,
        order_size_usd=args.order_size if args.order_size is not None else base.order_size_usd,
    )

    bars = fetch_ohlc(args.symbol, args.days, end_date=args.end_date)
    print(f"Fetched {len(bars)} daily bars for {args.symbol} ({bars[0].d} -> {bars[-1].d})")

    if args.intraday:
        intraday = fetch_intraday(args.symbol, bars[0].d, bars[-1].d,
                                  bar_size="5 mins", use_rth=False)
        print(f"Fetched {len(intraday)} 5-min bars (extended hours) for resolution")
        result = run_backtest_intraday(args.symbol, bars, intraday, params)
    else:
        result = run_backtest(args.symbol, bars, params)
    print_summary(result)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    trades_df = trades_to_dataframe(result.trades)
    trades_csv = out_dir / f"{args.symbol}_{args.side}_trades.csv"
    trades_df.to_csv(trades_csv, index=False)
    print(f"Wrote {len(trades_df)} trade rows to {trades_csv}")

    summary_csv = out_dir / f"{args.symbol}_{args.side}_summary.csv"
    pd.DataFrame([summary_row(result)]).to_csv(summary_csv, index=False)
    print(f"Wrote summary row to {summary_csv}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
