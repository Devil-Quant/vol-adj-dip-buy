"""Pre-fetch + cache daily and 5-min history for a symbol list, so the
optimizer can run repeatedly on cached bars. Logs progress (this can take a
while on IBKR pacing). CLI:
    python scripts/fetch_history.py data/symbols_opt.txt --years 2
"""
from __future__ import annotations

import argparse
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from clients import fetch_ohlc, fetch_intraday

LOG = Path(__file__).resolve().parent.parent / "data" / "fetch_history.log"


def log(msg: str) -> None:
    line = f"{datetime.now():%H:%M:%S}  {msg}"
    print(line, flush=True)
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def load_symbols(path: Path) -> list[str]:
    return [s.strip().upper() for s in path.read_text().splitlines()
            if s.strip() and not s.startswith("#")]


def main() -> int:
    ap = argparse.ArgumentParser(description="Pre-fetch daily + 5-min history")
    ap.add_argument("symbols_file")
    ap.add_argument("--years", type=float, default=2.0)
    ap.add_argument("--daily-sessions", type=int, default=620,
                    help="daily sessions to pull (2yr + sigma-lookback buffer)")
    args = ap.parse_args()

    symbols = load_symbols(Path(args.symbols_file))
    end = date.today()
    start = end - timedelta(days=int(args.years * 365))
    log(f"=== fetch start: {len(symbols)} symbols, 5-min {start}..{end}, "
        f"daily {args.daily_sessions} sessions ===")

    for i, sym in enumerate(symbols, 1):
        try:
            d = fetch_ohlc(sym, args.daily_sessions)
            log(f"[{i}/{len(symbols)}] {sym} daily: {len(d)} bars ({d[0].d}..{d[-1].d})")
        except Exception as e:
            log(f"[{i}/{len(symbols)}] {sym} daily FAILED: {e}")
            continue
        try:
            intr = fetch_intraday(sym, start, end, bar_size="5 mins", use_rth=False)
            log(f"[{i}/{len(symbols)}] {sym} 5-min: {len(intr)} bars ({intr[0].d}..{intr[-1].d})")
        except Exception as e:
            log(f"[{i}/{len(symbols)}] {sym} 5-min FAILED: {e}")

    log("=== fetch complete ===")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
