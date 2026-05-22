"""Daily forecastability harness report.

Reads cached daily bars, builds 'predict-the-day-at-its-open' features +
targets, runs expanding walk-forward (pooled across symbols by date) for the
RANGE (volatility) and DIRECTION targets, and prints each model vs its naive
baseline with a clear SIGNAL / NO-SIGNAL read.

Gateway-free: reads the daily parquet cache directly, so it runs with IBKR down.

    python scripts/forecast_report.py
    python scripts/forecast_report.py --symbols NVDA TSLA --days 620 --splits 5
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd  # noqa: E402

from clients import read_daily_cache  # noqa: E402
from forecast.features import FEATURE_COLS, build_features  # noqa: E402
from forecast.targets import build_targets  # noqa: E402
from forecast.walkforward import (walk_forward_direction,  # noqa: E402
                                  walk_forward_range)

DEFAULT_SYMBOLS = ["NVDA", "AVGO", "TSLA", "MU", "AMD", "INTC", "ORCL",
                   "CRWD", "IONQ", "RKLB"]


def build_pooled(symbols, days):
    """Per-symbol features+targets, merged on date and pooled into one frame."""
    frames, used = [], []
    for s in symbols:
        bars = read_daily_cache(s, days)
        if not bars or len(bars) < 80:
            continue
        merged = build_features(bars).merge(build_targets(bars), on="date")
        merged["symbol"] = s
        frames.append(merged)
        used.append(s)
    if not frames:
        return None, []
    return pd.concat(frames, ignore_index=True), used


def _report_range(pooled, splits):
    r = walk_forward_range(pooled, FEATURE_COLS, n_splits=splits)
    print("== RANGE (volatility) target: today (H-L)/open ==")
    if not r.get("n"):
        print("  insufficient data")
        return
    print(f"  OOS n={r['n']}")
    print(f"  Ridge model     MAE={r['model_mae']:.4f}  R2={r['model_r2']:+.4f}")
    print(f"  EWMA baseline   MAE={r['ewma_mae']:.4f}  R2={r['ewma_r2']:+.4f}")
    print(f"  mean baseline   MAE={r['mean_mae']:.4f}")
    gain = (r["ewma_mae"] - r["model_mae"]) / r["ewma_mae"] * 100
    # vol clusters, so EWMA persistence already explains most range; only call
    # it incremental SIGNAL if features beat persistence by a real margin (>1%).
    verdict = "SIGNAL beyond persistence" if gain > 1.0 \
        else "persistence only (features add ~nothing)"
    print(f"  -> model vs EWMA: {gain:+.1f}% MAE  => {verdict}")


def _report_direction(pooled, splits):
    d = walk_forward_direction(pooled, FEATURE_COLS, n_splits=splits)
    print("\n== DIRECTION target: today close > open ==")
    if not d.get("n"):
        print("  insufficient data")
        return
    print(f"  OOS n={d['n']}  up-rate(base)={d['up_rate']:.3f}")
    print(f"  Logit model     acc={d['model_acc']:.3f}  AUC={d['model_auc']:.3f}")
    print(f"  base-rate       acc={d['base_acc']:.3f}  AUC=0.500")
    edge = (d["model_acc"] - d["base_acc"]) * 100
    has = d["model_acc"] > d["base_acc"] and d["model_auc"] > 0.52
    verdict = "SIGNAL beyond base rate" if has else "NO real signal"
    print(f"  -> acc vs base: {edge:+.1f} pts, AUC {d['model_auc']:.3f} => {verdict}")


def main() -> int:
    ap = argparse.ArgumentParser(description="Daily forecastability harness")
    ap.add_argument("--symbols", nargs="*", default=DEFAULT_SYMBOLS)
    ap.add_argument("--days", type=int, default=620)
    ap.add_argument("--splits", type=int, default=5)
    args = ap.parse_args()

    pooled, used = build_pooled(args.symbols, args.days)
    if pooled is None:
        print("No cached daily data for the requested symbols/days "
              "(need data/cache/{SYM}_{days}d_now.parquet).")
        return 1

    print(f"Forecastability harness | symbols={','.join(used)} | "
          f"rows={len(pooled)} | walk-forward splits={args.splits}")
    print(f"Features: {', '.join(FEATURE_COLS)}\n")
    _report_range(pooled, args.splits)
    _report_direction(pooled, args.splits)
    print("\nNote: price-only features on cached trending-tech daily (~2.5yr). "
          "Volume/RVOL + AGGR order-flow + SPY/long-history are v2 (gateway up).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
