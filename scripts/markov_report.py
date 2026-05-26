"""Markov 3-state regime report.

For each symbol, loads cached daily bars, builds the rule-based Markov model
(states: bull / sideways / bear via trailing-`lookback` return), and prints:
  - current input state (= state at the most recent labeled day)
  - (P_bull, P_sideways, P_bear) for tomorrow
  - edge = P_bull - P_bear, with gate decision at theta
  - pooled 3x3 transition matrix (rows sum to 1.0 — quick sanity)

Gateway-free: reads the daily parquet cache.

    python scripts/markov_report.py
    python scripts/markov_report.py --symbols NVDA SPY --days 620 --lookback 60
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from clients import read_daily_cache  # noqa: E402
from config.settings import (MARKOV_BEAR_THRESHOLD, MARKOV_BULL_THRESHOLD,  # noqa: E402
                             MARKOV_GATE_THETA, MARKOV_LOOKBACK)
from forecast.markov import STATES, build_markov_states  # noqa: E402

DEFAULT_SYMBOLS = ["NVDA", "AVGO", "TSLA", "MU", "AMD", "INTC", "ORCL",
                   "CRWD", "IONQ", "RKLB"]


def _label_states(df, bull, bear):
    """Re-derive the day-by-day state labels (so we can pool transition counts
    across symbols below). Mirrors the labelling in `forecast.markov`."""
    out = []
    for _, row in df.iterrows():
        s = row["state"]   # state column carries state at row-1 (input state)
        out.append(s)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Markov 3-state regime report")
    ap.add_argument("--symbols", nargs="*", default=DEFAULT_SYMBOLS)
    ap.add_argument("--days", type=int, default=620)
    ap.add_argument("--lookback", type=int, default=MARKOV_LOOKBACK)
    ap.add_argument("--bull", type=float, default=MARKOV_BULL_THRESHOLD)
    ap.add_argument("--bear", type=float, default=MARKOV_BEAR_THRESHOLD)
    ap.add_argument("--theta", type=float, default=MARKOV_GATE_THETA)
    args = ap.parse_args()

    print(f"Markov regime | lookback={args.lookback}d  bull>={args.bull:+.0%}  "
          f"bear<={args.bear:+.0%}  gate theta={args.theta}\n")
    print(f"{'sym':6} {'as-of':10} {'state':9} "
          f"{'P_bull':>7} {'P_side':>7} {'P_bear':>7} {'edge':>7}  gate")
    print("-" * 76)

    # Pool transitions across symbols to print one global 3x3 matrix as a
    # sanity check that rows sum to 1.0.
    pooled = {s: {t: 0 for t in STATES} for s in STATES}

    for s in args.symbols:
        bars = read_daily_cache(s, args.days)
        if not bars or len(bars) < args.lookback + 30:
            print(f"{s:6}  (no usable cache: need >= {args.lookback + 30} daily bars)")
            continue
        df = build_markov_states(bars, lookback=args.lookback,
                                 bull_thresh=args.bull, bear_thresh=args.bear)
        labeled = df.dropna(subset=["edge"])
        if labeled.empty:
            print(f"{s:6}  (no labeled rows after warm-up)")
            continue
        last = labeled.iloc[-1]
        gate = "ALLOW" if last["edge"] > args.theta else "block"
        print(f"{s:6} {str(last['date']):10} {last['state']:9} "
              f"{last['p_bull']:>7.3f} {last['p_sideways']:>7.3f} "
              f"{last['p_bear']:>7.3f} {last['edge']:>+7.3f}  {gate}")

        # Pool the symbol's full transition history for the global matrix
        # (we re-derive raw state labels from each row's "state" column —
        # that's the input state at row-1, so consecutive pairs are transitions).
        states_seq = [r["state"] for _, r in labeled.iterrows()]
        for a, b in zip(states_seq, states_seq[1:]):
            if a in STATES and b in STATES:
                pooled[a][b] += 1

    # Pooled matrix
    print(f"\nPooled 3x3 transition matrix (input state -> next state):")
    print(f"{'from \\ to':12}" + "".join(f"{t:>11}" for t in STATES) + f"{'row sum':>10}")
    for src in STATES:
        row = pooled[src]
        total = sum(row.values())
        cells = ""
        for dst in STATES:
            p = (row[dst] / total) if total else 0.0
            cells += f"{p:>11.3f}"
        print(f"{src:12}{cells}{1.0 if total else 0.0:>10.3f}")
    print("\nRows should sum to 1.0. Diagonal = persistence (the 'stickiness' "
          "the strategy regime model relies on).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
