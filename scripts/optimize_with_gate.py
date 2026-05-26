"""Compare the buy optimum (sigma1.0 / TP2.0 / stop3.0) with vs. without the
Markov regime gate on the 10 opt names, using realistic 5-min fills.

Sweeps `MARKOV_LOOKBACK` in {20, 60, 120} (per the plan's pre-mortem — 20 may
be jittery relative to typical regime lengths). For each lookback, reports:
  - ungated vs gated total realized P&L, trade count, win rate
  - oos_evaluate (held-out test of the gated combo)
  - monte_carlo over full + OOS-only
  - walk_forward stitched OOS P&L (gated vs ungated)

Gateway-free: reads cached daily (`read_daily_cache`) and cached 5-min
(`fetch_intraday` with use_cache=True).

    python scripts/optimize_with_gate.py
    python scripts/optimize_with_gate.py --lookbacks 20 60 120
"""
from __future__ import annotations

import argparse
import datetime as dt
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from clients import fetch_intraday, read_daily_cache  # noqa: E402
from backtest.engine import (build_day_start,  # noqa: E402
                             trailing_sigma_by_day)
from backtest.optimizer import (closed_pnls, combo_trades,  # noqa: E402
                                window_stats)
from backtest.validation import (date_axis, monte_carlo,  # noqa: E402
                                 walk_forward)
from config.settings import (MARKOV_BEAR_THRESHOLD, MARKOV_BULL_THRESHOLD,  # noqa: E402
                             MARKOV_GATE_THETA, SIGMA_LOOKBACK)
from forecast.markov import markov_allow_by_day  # noqa: E402

DEFAULT_SYMBOLS = ["NVDA", "AVGO", "TSLA", "MU", "AMD", "INTC", "ORCL",
                   "CRWD", "IONQ", "RKLB"]
OPT_SIGMA, OPT_TP, OPT_STOP = 1.0, 2.0, 3.0   # the buy optimum
ORDER = 100_000.0


def _load(syms):
    sd = {}
    for s in syms:
        d = read_daily_cache(s, 620)
        if not d:
            continue
        i = fetch_intraday(s, date(2024, 5, 20), date(2026, 5, 20),
                           bar_size="5 mins", use_cache=True)
        sd[s] = {
            "daily": d, "intraday": i,
            "sigma_by_day": trailing_sigma_by_day(d, SIGMA_LOOKBACK),
            "day_start": build_day_start(i),
        }
    return sd


def _gate_per_symbol(symbols_data, lookback, theta):
    """Build allow_by_day for each symbol from its own daily history."""
    out = {}
    for s, sd in symbols_data.items():
        out[s] = markov_allow_by_day(
            sd["daily"], lookback=lookback,
            bull_thresh=MARKOV_BULL_THRESHOLD, bear_thresh=MARKOV_BEAR_THRESHOLD,
            theta=theta,
        )
    return out


def _summary(recs):
    w = window_stats(OPT_TP, OPT_STOP, recs)
    return w


def _row(label, w, mc):
    pp = (mc["prob_profit"] * 100) if mc else float("nan")
    print(f"  {label:18} ${w.total_pnl:>11,.0f}  n={w.n_trades:>4}  "
          f"win={w.win_rate*100:>4.0f}%  MC(profit)={pp:>3.0f}%")


def _run(symbols_data, label, lookback, theta):
    """For one lookback: compute ungated + gated recs, print comparison."""
    # Ungated: clear allow_by_day on all symbols
    for sd in symbols_data.values():
        sd.pop("allow_by_day", None)
    ung = combo_trades(symbols_data, "buy", OPT_SIGMA, OPT_TP, OPT_STOP, ORDER)

    # Gated: per-symbol allow_by_day
    gates = _gate_per_symbol(symbols_data, lookback, theta)
    for s, sd in symbols_data.items():
        sd["allow_by_day"] = gates[s]
    gat = combo_trades(symbols_data, "buy", OPT_SIGMA, OPT_TP, OPT_STOP, ORDER)

    print(f"\n=== {label} ===")
    print(f"  {'config':18} {'total $':>13}  {'#tr':>6}  {'win':>5}  {'MC p(profit)':>13}")
    _row("ungated",
         _summary(ung), monte_carlo(closed_pnls(ung)))
    _row("gated (Markov)",
         _summary(gat), monte_carlo(closed_pnls(gat)))

    # OOS slice on gated (where the gate is supposed to add the most value)
    dates = sorted(date_axis({(OPT_TP, OPT_STOP): gat}))
    if len(dates) >= 20:
        split = dates[int(len(dates) * 0.7)]
        nxt = split + dt.timedelta(days=1)
        isw = window_stats(OPT_TP, OPT_STOP, gat, start=dates[0], end=split)
        oosw = window_stats(OPT_TP, OPT_STOP, gat, start=nxt, end=dates[-1])
        print(f"  gated IS  ${isw.total_pnl:>11,.0f}  -> OOS ${oosw.total_pnl:>11,.0f}"
              f"  ({oosw.n_trades}tr, win {oosw.win_rate*100:.0f}%)")

    # Walk-forward (re-pick combo each IS window, but at fixed sigma_mult=1.0 +
    # this single (TP, stop). The grid is single-cell, so wf effectively tests
    # the same combo on rolling OOS windows.)
    wf_ung = walk_forward({(OPT_TP, OPT_STOP): ung})
    wf_gat = walk_forward({(OPT_TP, OPT_STOP): gat})
    if wf_ung and wf_gat:
        print(f"  walk-forward stitched OOS: "
              f"ungated ${wf_ung['stitched_oos_pnl']:>11,.0f}  "
              f"gated ${wf_gat['stitched_oos_pnl']:>11,.0f}")


def main() -> int:
    ap = argparse.ArgumentParser(description="Markov-gated buy optimum comparison")
    ap.add_argument("--symbols", nargs="*", default=DEFAULT_SYMBOLS)
    ap.add_argument("--lookbacks", nargs="*", type=int, default=[20, 60, 120],
                    help="MARKOV_LOOKBACK sweep")
    ap.add_argument("--theta", type=float, default=MARKOV_GATE_THETA)
    args = ap.parse_args()

    print(f"Loading {len(args.symbols)} symbols ...", flush=True)
    sd = _load(args.symbols)
    if not sd:
        print("No cached data found for the symbols requested.")
        return 1
    print(f"Loaded {len(sd)} symbols (used: {','.join(sd)})")
    print(f"Buy optimum: sigma_mult={OPT_SIGMA} TP={OPT_TP}sigma stop={OPT_STOP}sigma "
          f"order=${ORDER:,.0f}")
    print(f"Gate threshold theta={args.theta}")

    for lb in args.lookbacks:
        _run(sd, f"MARKOV_LOOKBACK = {lb}", lb, args.theta)

    print("\n(Reminder: 2-year window covers a sustained bull tape for these "
          "names, so the gate's main effect is trimming days in the rare bear "
          "stretches. P&L will move less than win-rate / MC stats.)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
