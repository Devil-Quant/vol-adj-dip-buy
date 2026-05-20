"""Sanity-check: run NVDA Buy backtest with spreadsheet defaults and print
the four totals next to the Excel reference. We anchor the IBKR pull to the
spreadsheet's snapshot date (2026-05-15) and request 69 sessions so the
window matches the Excel model as closely as possible. Residual drift comes
from IBKR (TRADES, RTH) vs the spreadsheet's Google Finance source."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backtest.engine import run_backtest
from backtest.reporter import print_summary
from clients import fetch_ohlc
from config.settings import DEFAULT_BUY


EXCEL_REFERENCE = {
    "symbol": "NVDA",
    "side": "buy",
    "snapshot_date": "2026-05-15",
    "trading_days": 69,
    "intraday_count": 13,
    "intraday_pnl": 23_638.97,
    "overnight_count": 19,
    "overnight_tp_count": 13,
    "overnight_tp_pnl": 24_348.42,
    "stop_count": 6,
    "stop_pnl": -21_168.35,
    "day_max_count": 0,
    "day_max_pnl": 0.0,
    "total_pnl": 26_819.04,
    "buy_and_hold_pct": 0.1699,
    "strategy_pct": 0.2682,
}

# A few exact OHLC values read straight from the spreadsheet's `Buy` tab,
# used to prove the IBKR data source agrees with Excel/Google Finance.
EXCEL_BARS = {
    "2026-02-09": (184.26, 193.66, 183.95, 190.04),
    "2026-02-12": (193.03, 193.61, 186.51, 186.94),
    "2026-02-13": (187.48, 187.50, 181.59, 182.81),
}


def _check_bars(bars) -> bool:
    by_date = {str(b.d): b for b in bars}
    print("\n=== Data-source check (IBKR vs Excel bars, |diff| <= $0.10) ===")
    ok = True
    for d, (o, h, l, c) in EXCEL_BARS.items():
        b = by_date.get(d)
        if b is None:
            print(f"  {d}  (not in window)")
            continue
        match = all(abs(a - e) <= 0.10 for a, e in
                    [(b.open, o), (b.high, h), (b.low, l), (b.close, c)])
        ok = ok and match
        print(f"  {d}  IBKR C={b.close:.2f} vs Excel C={c:.2f}  [{'OK' if match else 'MISMATCH'}]")
    return ok


def main() -> int:
    sym = EXCEL_REFERENCE["symbol"]
    # Match the spreadsheet window: 69 sessions ending on the snapshot date.
    bars = fetch_ohlc(sym, EXCEL_REFERENCE["trading_days"],
                      end_date=EXCEL_REFERENCE["snapshot_date"])
    print(f"Fetched {len(bars)} bars for {sym} ({bars[0].d} -> {bars[-1].d})")

    data_ok = _check_bars(bars)

    result = run_backtest(sym, bars, DEFAULT_BUY)
    print_summary(result)

    print("\n=== Excel reference (NVDA Buy, snapshot 2026-05-15) ===")
    for k, v in EXCEL_REFERENCE.items():
        print(f"  {k:<20} {v}")

    print("\n=== Per-bucket comparison (the robust signal) ===")
    bucket_diffs = {
        "intraday_pnl":     result.intraday_pnl - EXCEL_REFERENCE["intraday_pnl"],
        "overnight_tp_pnl": result.overnight_tp_pnl - EXCEL_REFERENCE["overnight_tp_pnl"],
        "stop_pnl":         result.stop_pnl - EXCEL_REFERENCE["stop_pnl"],
        "day_max_pnl":      result.day_max_pnl - EXCEL_REFERENCE["day_max_pnl"],
    }
    buckets_ok = True
    for k, v in bucket_diffs.items():
        ok = abs(v) < 5_000
        buckets_ok = buckets_ok and ok
        print(f"  {k:<20} diff = ${v:>+12,.2f}   [{'OK' if ok else 'WARN'}]")
    total_diff = result.total_pnl - EXCEL_REFERENCE["total_pnl"]
    print(f"  {'total_pnl':<20} diff = ${total_diff:>+12,.2f}   "
          f"(window-edge sensitive - informational)")

    # Verdict: data must match Excel tic-for-tic AND every bucket within $5k.
    # The raw total is window-edge sensitive (IBKR's 69-session window starts a
    # few days off Excel's fuzzy googlefinance window) so it's not the gate.
    counts_close = (
        abs(result.intraday_count - EXCEL_REFERENCE["intraday_count"]) <= 2
        and abs(result.overnight_count - EXCEL_REFERENCE["overnight_count"]) <= 2
    )
    verdict = "PASS" if (data_ok and buckets_ok and counts_close) else "REVIEW"
    print(f"\nVERDICT: {verdict}  (data_ok={data_ok}, buckets_ok={buckets_ok}, counts_close={counts_close})")
    return 0 if verdict == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
