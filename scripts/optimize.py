"""Optimize TP/SL per side (buy & short) with anti-overfit validation:
out-of-sample, walk-forward, and Monte Carlo. Runs on cached IBKR data (run
scripts/fetch_history.py first). CLI:
    python scripts/optimize.py data/symbols_opt.txt --years 2
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from clients import fetch_ohlc, fetch_intraday
from config.settings import TP_GRID, SL_GRID, MAX_RR, SIGMA_LOOKBACK
from backtest.engine import build_day_start, trailing_sigma_by_day
from backtest.optimizer import run_grid, best_combo
from backtest.validation import oos_evaluate, walk_forward, monte_carlo

ORDER = 100_000.0
SIGMA_MULT = 1.0


def load_symbols(path: Path) -> list[str]:
    return [s.strip().upper() for s in path.read_text().splitlines()
            if s.strip() and not s.startswith("#")]


def build_symbols_data(symbols, daily_sessions, start, end, sigma_lookback) -> dict:
    data = {}
    for sym in symbols:
        try:
            daily = fetch_ohlc(sym, daily_sessions)
            intr = fetch_intraday(sym, start, end, bar_size="5 mins", use_rth=False)
        except Exception as e:
            print(f"[skip] {sym}: {e}")
            continue
        data[sym] = {
            "daily": daily, "intraday": intr,
            "day_start": build_day_start(intr),
            "sigma_by_day": trailing_sigma_by_day(daily, sigma_lookback),
        }
        print(f"  loaded {sym}: {len(daily)} daily, {len(intr)} 5-min")
    return data


def optimize_side(grid: dict) -> dict:
    full_best, ranked = best_combo(grid)
    oos = oos_evaluate(grid)
    wf = walk_forward(grid)
    mc = monte_carlo(wf["oos_pnls"]) if (wf and wf["oos_pnls"]) else None
    return {"full_best": full_best, "ranked": ranked[:5], "oos": oos, "wf": wf, "mc": mc}


def print_side(side: str, res: dict) -> None:
    b = res["full_best"]
    print(f"\n{'='*64}\n{side.upper()}\n{'='*64}")
    if b is None:
        print("  no trades")
        return
    print(f"  IN-SAMPLE BEST (full history): TP={b.limit_mult}sigma SL={b.stop_mult}sigma "
          f"RR={(SIGMA_MULT+b.limit_mult)/b.stop_mult:.2f}")
    print(f"    total ${b.total_pnl:>+12,.0f} | {b.n_trades} trades | win {b.win_rate:.1%} "
          f"| exp ${b.expectancy:>+,.0f}/trade | worst ${b.worst:>+,.0f} | open {b.open_count}")
    print("  top combos (full history):")
    for w in res["ranked"]:
        print(f"    TP={w.limit_mult} SL={w.stop_mult}: ${w.total_pnl:>+11,.0f} "
              f"({w.n_trades} tr, win {w.win_rate:.0%})")

    oos = res["oos"]
    if oos:
        i, o = oos["is"], oos["oos"]
        keep = "HOLDS" if o.total_pnl > 0 else "COLLAPSES"
        print(f"\n  OUT-OF-SAMPLE (optimize<= {oos['split_date']}, test after):")
        print(f"    IS  TP={i.limit_mult} SL={i.stop_mult}: ${i.total_pnl:>+11,.0f} (win {i.win_rate:.0%})")
        print(f"    OOS same params:        ${o.total_pnl:>+11,.0f} (win {o.win_rate:.0%})  -> {keep}")

    wf = res["wf"]
    if wf and wf["folds"]:
        params = [f["params"] for f in wf["folds"]]
        stable = len(set(params)) <= max(2, len(params) // 2)
        print(f"\n  WALK-FORWARD ({len(wf['folds'])} folds): stitched OOS ${wf['stitched_oos_pnl']:>+12,.0f}")
        for f in wf["folds"]:
            print(f"    {f['is_start']}->{f['is_end']} pick TP={f['params'][0]} SL={f['params'][1]}"
                  f" | OOS ${f['oos_pnl']:>+10,.0f} ({f['oos_trades']} tr, win {f['oos_win_rate']:.0%})")
        print(f"    param stability: {'STABLE' if stable else 'UNSTABLE (overfit risk)'}")

    mc = res["mc"]
    if mc:
        print(f"\n  MONTE CARLO ({mc['n']} resamples of {mc['trades']} walk-forward OOS trades):")
        print(f"    total P&L  median ${mc['median_total']:>+11,.0f}  "
              f"[p5 ${mc['p5_total']:>+11,.0f} .. p95 ${mc['p95_total']:>+11,.0f}]")
        print(f"    prob(profit) = {mc['prob_profit']:.1%}   "
              f"median maxDD ${mc['median_max_drawdown']:>+,.0f}  worst5% ${mc['p95_max_drawdown']:>+,.0f}")
        verdict = ("ROBUST" if mc["prob_profit"] >= 0.95 and wf and wf["stitched_oos_pnl"] > 0
                   else "WEAK / likely not tradeable")
        print(f"\n  VERDICT: {verdict}")


def _jsonable(res: dict) -> dict:
    def w(x):
        return None if x is None else {k: getattr(x, k) for k in
                                       ("limit_mult", "stop_mult", "total_pnl", "n_trades",
                                        "win_rate", "expectancy", "worst", "open_count")}
    out = {"full_best": w(res["full_best"]), "mc": res["mc"]}
    if res["oos"]:
        out["oos"] = {"split_date": str(res["oos"]["split_date"]),
                      "is": w(res["oos"]["is"]), "oos": w(res["oos"]["oos"])}
    if res["wf"]:
        out["wf_stitched_oos_pnl"] = res["wf"]["stitched_oos_pnl"]
        out["wf_folds"] = [{**f, "is_start": str(f["is_start"]), "is_end": str(f["is_end"]),
                            "oos_end": str(f["oos_end"]), "params": list(f["params"])}
                           for f in res["wf"]["folds"]]
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Optimize TP/SL with OOS+walk-forward+MC")
    ap.add_argument("symbols_file")
    ap.add_argument("--years", type=float, default=2.0)
    ap.add_argument("--daily-sessions", type=int, default=620)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    symbols = load_symbols(Path(args.symbols_file))
    end = date.today()
    start = end - timedelta(days=int(args.years * 365))
    print(f"Loading {len(symbols)} symbols, 5-min {start}..{end} ...")
    data = build_symbols_data(symbols, args.daily_sessions, start, end, SIGMA_LOOKBACK)
    if not data:
        print("No data loaded.", file=sys.stderr)
        return 1

    report = {}
    for side in ("buy", "short"):
        grid = run_grid(data, side, TP_GRID, SL_GRID, SIGMA_MULT, ORDER, MAX_RR)
        res = optimize_side(grid)
        print_side(side, res)
        report[side] = _jsonable(res)

    out = Path(args.out) if args.out else Path("data") / f"optimization_{end.isoformat()}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, default=str))
    print(f"\nWrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
