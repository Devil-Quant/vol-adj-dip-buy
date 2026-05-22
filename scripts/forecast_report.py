"""Daily forecastability harness report (v2: price-only vs price+volume).

Reads cached daily bars, builds 'predict-the-day-at-its-open' features +
targets, runs expanding walk-forward (pooled across symbols by date) for the
RANGE (volatility) and DIRECTION targets, and prints each model vs its naive
baseline. v2 dual-runs price-only vs price+volume feature sets so you SEE
whether volume adds anything, and adds an SPY index-regime block.

Gateway-free: reads the daily parquet cache directly.

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
from forecast.features import (FEATURE_COLS, VOLUME_COLS,  # noqa: E402
                               build_features)
from forecast.targets import build_targets  # noqa: E402
from forecast.walkforward import (walk_forward_direction,  # noqa: E402
                                  walk_forward_range)

DEFAULT_SYMBOLS = ["NVDA", "AVGO", "TSLA", "MU", "AMD", "INTC", "ORCL",
                   "CRWD", "IONQ", "RKLB", "SPY"]


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


def _has_volume(pooled):
    return "rvol" in pooled.columns and bool(pooled["rvol"].notna().any())


def _verdict(gain, thresh=1.0):
    return gain > thresh


def _report_range(pooled, splits, has_vol):
    po = walk_forward_range(pooled, FEATURE_COLS, n_splits=splits)
    print("== RANGE (volatility) target: today (H-L)/open ==")
    if not po.get("n"):
        print("  insufficient data")
        return
    print(f"  OOS n={po['n']}")
    print(f"  price-only Ridge  MAE={po['model_mae']:.4f}  R2={po['model_r2']:+.4f}")
    full = None
    if has_vol:
        full = walk_forward_range(pooled, FEATURE_COLS + VOLUME_COLS,
                                  n_splits=splits)
        print(f"  +volume    Ridge  MAE={full['model_mae']:.4f}  R2={full['model_r2']:+.4f}")
    print(f"  EWMA baseline     MAE={po['ewma_mae']:.4f}  R2={po['ewma_r2']:+.4f}")
    print(f"  mean baseline     MAE={po['mean_mae']:.4f}")
    g_po = (po["ewma_mae"] - po["model_mae"]) / po["ewma_mae"] * 100
    if full:
        g_inc = (po["model_mae"] - full["model_mae"]) / po["model_mae"] * 100
        if _verdict(g_inc):
            v = f"volume ADDS signal ({g_inc:+.1f}% MAE over price-only)"
        elif _verdict(g_po):
            v = "price beats EWMA; volume adds ~nothing"
        else:
            v = "persistence only (neither price nor volume beats EWMA)"
        print(f"  -> volume vs price-only: {g_inc:+.1f}% MAE | price vs EWMA: "
              f"{g_po:+.1f}%  => {v}")
    else:
        v = "SIGNAL beyond persistence" if _verdict(g_po) else \
            "persistence only (features add ~nothing)"
        print(f"  -> price vs EWMA: {g_po:+.1f}% MAE  => {v}")


def _report_direction(pooled, splits, has_vol):
    po = walk_forward_direction(pooled, FEATURE_COLS, n_splits=splits)
    print("\n== DIRECTION target: today close > open ==")
    if not po.get("n"):
        print("  insufficient data")
        return
    print(f"  OOS n={po['n']}  up-rate(base)={po['up_rate']:.3f}")
    print(f"  price-only Logit  acc={po['model_acc']:.3f}  AUC={po['model_auc']:.3f}")
    full = None
    if has_vol:
        full = walk_forward_direction(pooled, FEATURE_COLS + VOLUME_COLS,
                                      n_splits=splits)
        print(f"  +volume    Logit  acc={full['model_acc']:.3f}  AUC={full['model_auc']:.3f}")
    print(f"  base-rate         acc={po['base_acc']:.3f}  AUC=0.500")
    best = full if full else po
    has = best["model_acc"] > po["base_acc"] and best["model_auc"] > 0.52
    tag = "+volume" if full else "price-only"
    v = f"SIGNAL ({tag}, AUC {best['model_auc']:.3f})" if has else "NO real signal"
    print(f"  -> best AUC {best['model_auc']:.3f} vs 0.500 => {v}")


def _run_block(pooled, used, splits, title):
    has_vol = _has_volume(pooled)
    cols = "price+volume" if has_vol else "price-only"
    print(f"{title} | symbols={','.join(used)} | rows={len(pooled)} | "
          f"splits={splits} | features={cols}")
    _report_range(pooled, splits, has_vol)
    _report_direction(pooled, splits, has_vol)


def main() -> int:
    ap = argparse.ArgumentParser(description="Daily forecastability harness v2")
    ap.add_argument("--symbols", nargs="*", default=DEFAULT_SYMBOLS)
    ap.add_argument("--days", type=int, default=620)
    ap.add_argument("--splits", type=int, default=5)
    args = ap.parse_args()

    stock_syms = [s for s in args.symbols if s.upper() != "SPY"]
    pooled, used = build_pooled(stock_syms, args.days)
    if pooled is None:
        print("No cached daily data for the requested symbols/days.")
        return 1
    print(f"Features: {', '.join(FEATURE_COLS)}")
    print(f"Volume features: {', '.join(VOLUME_COLS)}\n")
    _run_block(pooled, used, args.splits, "STOCK POOL")

    if any(s.upper() == "SPY" for s in args.symbols):
        spy, spy_used = build_pooled(["SPY"], args.days)
        if spy is not None:
            print("\n----------------------------------------")
            _run_block(spy, spy_used, args.splits, "SPY (index regime)")

    print("\nNote: daily, ~2.5yr. Order-flow (AGGR) is the separate CRYPTO "
          "track — it does not cover these equities.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
