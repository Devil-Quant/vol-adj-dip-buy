"""Backtest the Excel-default buy params on the sector-ETF universe (the
strategy's designed-for habitat — mean-reverting baskets) with and without the
Markov regime gate. Daily engine, Excel-faithful.

Per-ETF report: gated strategy P&L / ungated strategy P&L / buy-and-hold P&L
on a $100k slot. The 131k-strategies survey (Video 3) independently found
mean-reversion only survives on sector ETFs — this script tests that on our
exact strategy.

Reads cached daily bars (gateway-free once `fetch_etf_history.py` has run).

    python scripts/backtest_etfs.py
    python scripts/backtest_etfs.py --symbols XLU XLE --lookback 60
"""
from __future__ import annotations

import argparse
import dataclasses
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from clients import read_daily_cache  # noqa: E402
from backtest.engine import run_backtest  # noqa: E402
from config.settings import (DEFAULT_BUY, MARKOV_BEAR_THRESHOLD,  # noqa: E402
                             MARKOV_BULL_THRESHOLD, MARKOV_GATE_THETA,
                             MARKOV_LOOKBACK)
from forecast.markov import markov_allow_by_day  # noqa: E402
from strategies.dip_buy import simulate_buy  # noqa: E402
from strategies.common import hl_spread_stdev  # noqa: E402

DEFAULT_ETFS = ["XLU", "XLF", "XLK", "XLC", "XLE", "IWM", "DIA"]


def _pnl_sum(trades):
    return sum(t.pnl_usd for t in trades if t.filled and t.pnl_usd is not None)


def _count(trades):
    return sum(1 for t in trades if t.filled)


def _bh(bars, order):
    """Buy-and-hold P&L on `order` notional from first close to last."""
    first, last = bars[0].close, bars[-1].close
    return (last - first) / first * order


def main() -> int:
    ap = argparse.ArgumentParser(description="Sector-ETF backtest, gated vs ungated")
    ap.add_argument("--symbols", nargs="*", default=DEFAULT_ETFS)
    ap.add_argument("--days", type=int, default=2520,
                    help="must match what fetch_etf_history.py pulled")
    ap.add_argument("--lookback", type=int, default=MARKOV_LOOKBACK)
    ap.add_argument("--theta", type=float, default=MARKOV_GATE_THETA)
    args = ap.parse_args()

    order = DEFAULT_BUY.order_size_usd
    print(f"Sector-ETF backtest | Excel default buy "
          f"(sigma_mult={DEFAULT_BUY.sigma_mult} TP={DEFAULT_BUY.limit_mult}sigma "
          f"stop={DEFAULT_BUY.stop_mult}sigma) | order=${order:,.0f}")
    print(f"Markov gate: lookback={args.lookback}d theta={args.theta}\n")
    print(f"{'sym':5}  {'window':24}  "
          f"{'B&H $':>12}  {'ungated $':>12}  {'gated $':>12}  "
          f"{'#ung':>5}  {'#gat':>5}")
    print("-" * 92)

    sums = {"bh": 0.0, "ungated": 0.0, "gated": 0.0,
            "ung_n": 0, "gat_n": 0, "tested": 0}
    skipped = []
    for s in args.symbols:
        bars = read_daily_cache(s, args.days)
        if not bars or len(bars) < args.lookback + 50:
            skipped.append(s)
            continue

        bh = _bh(bars, order)
        # ungated daily backtest
        ung_trades = simulate_buy(bars, DEFAULT_BUY)
        ung_pnl = _pnl_sum(ung_trades)
        ung_n = _count(ung_trades)
        # gated
        allow = markov_allow_by_day(bars, lookback=args.lookback,
                                    bull_thresh=MARKOV_BULL_THRESHOLD,
                                    bear_thresh=MARKOV_BEAR_THRESHOLD,
                                    theta=args.theta)
        gat_trades = simulate_buy(bars, DEFAULT_BUY, allow_by_day=allow)
        gat_pnl = _pnl_sum(gat_trades)
        gat_n = _count(gat_trades)

        win = f"{bars[0].d}..{bars[-1].d}"
        print(f"{s:5}  {win:24}  ${bh:>11,.0f}  ${ung_pnl:>11,.0f}  "
              f"${gat_pnl:>11,.0f}  {ung_n:>5}  {gat_n:>5}")
        sums["bh"] += bh
        sums["ungated"] += ung_pnl
        sums["gated"] += gat_pnl
        sums["ung_n"] += ung_n
        sums["gat_n"] += gat_n
        sums["tested"] += 1

    n = sums["tested"]
    if n:
        cap = n * order
        print("-" * 92)
        print(f"TOTAL on {n}x${order/1000:.0f}k = ${cap/1e6:.1f}M slot-capital:")
        print(f"  buy & hold       ${sums['bh']:>11,.0f}  ({sums['bh']/cap*100:+.1f}%)")
        print(f"  strategy ungated ${sums['ungated']:>11,.0f}  "
              f"({sums['ungated']/cap*100:+.1f}%)  trades={sums['ung_n']}")
        print(f"  strategy gated   ${sums['gated']:>11,.0f}  "
              f"({sums['gated']/cap*100:+.1f}%)  trades={sums['gat_n']}")
        if abs(sums["ungated"]) > 0:
            delta_pct = (sums["gated"] - sums["ungated"]) / abs(sums["ungated"]) * 100
            print(f"  gate effect on strategy: {delta_pct:+.1f}% vs ungated")
    if skipped:
        print(f"\nSkipped (no cache, run fetch_etf_history.py first): "
              f"{', '.join(skipped)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
