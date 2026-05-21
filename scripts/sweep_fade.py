"""Stop-width sweep for the bidirectional OCO fade (long C-sigma OR short
C+sigma, whichever the price reaches first; tp_mult/stop_mult sigma offsets).
Runs on cached 1-min data; for each stop width reports full-sample, in-sample
vs out-of-sample, and a Monte-Carlo of the OOS trades. CLI:
    python scripts/sweep_fade.py data/symbols_min.txt --years 1.5
"""
from __future__ import annotations

import argparse
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from clients import fetch_ohlc, fetch_intraday
from config.settings import DEFAULT_BUY
from backtest.engine import build_day_start, trailing_sigma_by_day
from backtest.optimizer import combo_trades_fade, window_stats, closed_pnls
from backtest.validation import monte_carlo

ORDER = DEFAULT_BUY.order_size_usd
EXCEL_LOOKBACK = 69                       # Excel ~100 calendar -> ~69 trading days
STOP_GRID = (0.2, 0.5, 1.0, 1.5, 2.0)     # the widths to sweep
SIGMA_MULT = 1.0
TP_MULT = 1.0                             # revert ~to the mean


def load_symbols(path: Path) -> list[str]:
    return [s.strip().upper() for s in path.read_text().splitlines()
            if s.strip() and not s.startswith("#")]


def build_data(symbols, daily_sessions, start, end, bar_size) -> dict:
    data = {}
    for sym in symbols:
        try:
            daily = fetch_ohlc(sym, daily_sessions)
            intr = fetch_intraday(sym, start, end, bar_size=bar_size, use_rth=False)
        except Exception as e:
            print(f"[skip] {sym}: {e}")
            continue
        data[sym] = {
            "daily": daily, "intraday": intr,
            "day_start": build_day_start(intr),
            "sigma_by_day": trailing_sigma_by_day(daily, EXCEL_LOOKBACK),
        }
        print(f"  loaded {sym}: {len(daily)} daily, {len(intr)} {bar_size}")
    return data


def main() -> int:
    ap = argparse.ArgumentParser(description="Stop-width sweep for the OCO fade")
    ap.add_argument("symbols_file")
    ap.add_argument("--years", type=float, default=1.5)
    ap.add_argument("--daily-sessions", type=int, default=620)
    ap.add_argument("--bar-size", default="1 min")
    ap.add_argument("--oos-frac", type=float, default=0.7)
    args = ap.parse_args()

    symbols = load_symbols(Path(args.symbols_file))
    end = date.today()
    start = end - timedelta(days=int(args.years * 365))
    print(f"Loading {len(symbols)} symbols, {args.bar_size} {start}..{end} ...")
    data = build_data(symbols, args.daily_sessions, start, end, args.bar_size)
    if not data:
        print("No data.", file=sys.stderr)
        return 1

    print(f"\nOCO fade  entry=+/-{SIGMA_MULT}sigma  tp={TP_MULT}sigma  "
          f"(reward:risk shown per row)\n{'='*88}")
    print(f"{'stop':>5} {'RR':>5} {'trades':>7} {'win%':>6} {'FULL $':>13} "
          f"{'IS $':>12} {'OOS $':>12} {'OOS win%':>8} {'MC p(profit)':>13}")
    for sm in STOP_GRID:
        recs = combo_trades_fade(data, SIGMA_MULT, TP_MULT, sm, ORDER)
        if not recs:
            print(f"{sm:>5} (no trades)")
            continue
        dates = sorted({r.entry_date for r in recs})
        split = dates[int(len(dates) * args.oos_frac)]
        full = window_stats(TP_MULT, sm, recs)
        is_ = window_stats(TP_MULT, sm, recs, start=dates[0], end=split)
        oos = window_stats(TP_MULT, sm, recs, start=split + timedelta(days=1), end=dates[-1])
        mc = monte_carlo(closed_pnls(recs, start=split + timedelta(days=1)))
        rr = TP_MULT / sm
        pp = f"{mc['prob_profit']:.0%}" if mc else "-"
        print(f"{sm:>5} {rr:>5.1f} {full.n_trades:>7} {full.win_rate:>5.0%} "
              f"${full.total_pnl:>+11,.0f} ${is_.total_pnl:>+10,.0f} "
              f"${oos.total_pnl:>+10,.0f} {oos.win_rate:>7.0%} {pp:>13}")
    print("\nReward:risk = tp/stop. Watch for: positive OOS AND high MC prob(profit).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
