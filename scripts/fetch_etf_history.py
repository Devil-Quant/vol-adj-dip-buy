"""Fetch ~10 years of daily bars for the sector-ETF universe (XLU, XLF, XLK,
XLC, XLE, IWM, DIA) via IBKR. Caches as `data/cache/{SYM}_{days}d_now.parquet`.

**IB Gateway must be up.** This is a one-shot data pull; once cached, the ETF
backtest in `scripts/backtest_etfs.py` runs gateway-free.

    python scripts/fetch_etf_history.py
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from clients.ibkr_client import disconnect, fetch_ohlc  # noqa: E402

DEFAULT_ETFS = ["XLU", "XLF", "XLK", "XLC", "XLE", "IWM", "DIA"]


def main() -> int:
    ap = argparse.ArgumentParser(description="Fetch sector-ETF daily bars")
    ap.add_argument("--symbols", nargs="*", default=DEFAULT_ETFS)
    ap.add_argument("--days", type=int, default=2520,
                    help="~10yr default; 252 trading sessions/yr")
    args = ap.parse_args()

    ok, bad = 0, []
    for s in args.symbols:
        try:
            bars = fetch_ohlc(s, args.days)
            print(f"  {s:5} {len(bars)} bars  {bars[0].d} -> {bars[-1].d}  "
                  f"last close={bars[-1].close:.2f}")
            ok += 1
        except Exception as e:
            print(f"  {s:5} ERROR {str(e)[:80]}")
            bad.append(s)
    disconnect()
    print(f"\nDone: {ok} fetched, {len(bad)} failed{(' ('+','.join(bad)+')') if bad else ''}.")
    return 0 if not bad else 1


if __name__ == "__main__":
    raise SystemExit(main())
