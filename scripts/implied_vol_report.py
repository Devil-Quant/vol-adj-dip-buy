"""Horse race: does our SPY range forecast beat / add to VIX implied vol?

"Beats a statistical EWMA" (exp-20260522-013) is not a trading edge. You trade
vol against the market's IMPLIED range. So compare, walk-forward OOS, four range
forecasters on identical rows: EWMA persistence, VIX-only, our price features,
and ours+VIX. The DECISIVE number is (ours+VIX) vs (VIX-only): if our features
improve on VIX out-of-sample, we have signal the market hasn't priced; if not,
the edge is priced in and there's no vol trade.

    python scripts/implied_vol_report.py --days 3780 --splits 5
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from clients import read_daily_cache  # noqa: E402
from forecast.features import FEATURE_COLS, build_features  # noqa: E402
from forecast.implied import merge_vix  # noqa: E402
from forecast.targets import build_targets  # noqa: E402
from forecast.walkforward import walk_forward_range  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="SPY range forecast vs VIX implied")
    ap.add_argument("--days", type=int, default=3780)
    ap.add_argument("--splits", type=int, default=5)
    args = ap.parse_args()

    spy = read_daily_cache("SPY", args.days)
    vix = read_daily_cache("VIX", args.days)
    if not spy or not vix:
        print("Need SPY and VIX daily cache. Fetch them first (gateway up).")
        return 1

    frame = build_features(spy).merge(build_targets(spy), on="date")
    merged = merge_vix(frame, vix)
    # identical rows for every contender -> fair race (same OOS set + EWMA)
    need = list(FEATURE_COLS) + ["vix_implied", "range", "range_ewma"]
    merged = merged.dropna(subset=need).reset_index(drop=True)

    runs = {
        "VIX-only": ["vix_implied"],
        "ours (price)": FEATURE_COLS,
        "ours + VIX": FEATURE_COLS + ["vix_implied"],
    }
    res = {k: walk_forward_range(merged, c, n_splits=args.splits)
           for k, c in runs.items()}
    ref = res["ours (price)"]
    print(f"SPY range vs VIX implied | rows={len(merged)} | "
          f"splits={args.splits} | OOS n={ref['n']}")
    print(f"  EWMA baseline   MAE={ref['ewma_mae']:.5f}  R2={ref['ewma_r2']:+.4f}")
    for k in runs:
        r = res[k]
        print(f"  {k:13}  MAE={r['model_mae']:.5f}  R2={r['model_r2']:+.4f}")

    vix_mae = res["VIX-only"]["model_mae"]
    ours_mae = res["ours (price)"]["model_mae"]
    comb_mae = res["ours + VIX"]["model_mae"]
    g_vix = (ref["ewma_mae"] - vix_mae) / ref["ewma_mae"] * 100
    g_ours = (vix_mae - ours_mae) / vix_mae * 100
    g_comb = (vix_mae - comb_mae) / vix_mae * 100
    print(f"\n  VIX vs EWMA:        {g_vix:+.1f}%  (implied better than persistence?)")
    print(f"  ours vs VIX:        {g_ours:+.1f}%  (our forecast beat implied alone?)")
    print(f"  (ours+VIX) vs VIX:  {g_comb:+.1f}%  (DECISIVE: do we add beyond implied?)")
    if g_comb > 1.0:
        print(f"\n  => our forecast ADDS signal beyond VIX (+{g_comb:.1f}%) "
              "- tradeable vol-edge candidate")
    else:
        print("\n  => VIX subsumes our forecast - the edge is PRICED IN, no vol trade")
    print("\nCaveat: VIX is a 30d implied proxy (not the 1-day ATM straddle), and "
          "this is forecast accuracy, not yet net of option costs.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
