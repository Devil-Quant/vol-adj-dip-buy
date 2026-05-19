"""Forward-test signal generator. CLI:
    python scripts/todays_signals.py data/symbols.txt
Reads symbols file, fetches most-recent bars, emits today's order parameters
(buy_limit / sell_limit / stop / shares) per symbol per side."""
from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from clients.yfinance_client import fetch_ohlc
from config.settings import DEFAULT_BUY, DEFAULT_SHORT
from forward.signals import generate_signal, signals_to_dataframe


def load_symbols(path: Path) -> list[str]:
    out: list[str] = []
    for line in path.read_text().splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        out.append(s.upper())
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Emit today's forward-test order parameters")
    ap.add_argument("symbols_file")
    ap.add_argument("--days", type=int, default=100)
    ap.add_argument("--sides", default="buy,short")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    symbols = load_symbols(Path(args.symbols_file))
    if not symbols:
        print(f"No symbols in {args.symbols_file}", file=sys.stderr)
        return 1

    sides = [s.strip() for s in args.sides.split(",") if s.strip()]
    signals = []
    for sym in symbols:
        try:
            bars = fetch_ohlc(sym, args.days)
        except Exception as e:
            print(f"[skip] {sym}: {e}")
            continue
        for side in sides:
            base = DEFAULT_BUY if side == "buy" else DEFAULT_SHORT
            try:
                sig = generate_signal(sym, bars, base)
            except Exception as e:
                print(f"[err] {sym} {side}: {e}")
                continue
            signals.append(sig)
            print(
                f"  {sym:<6} {side:<5} entry={sig.entry_limit:>9.2f}  "
                f"tp={sig.tp_price:>9.2f}  stop={sig.stop_price:>9.2f}  "
                f"shares={sig.shares:>8.2f}  (prev_close={sig.prev_close:.2f} sigma={sig.sigma:.3f})"
            )

    if not signals:
        return 1
    df = signals_to_dataframe(signals)
    out = Path(args.out) if args.out else Path("data") / f"signals_{date.today().isoformat()}.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out, index=False)
    print(f"\nWrote signals -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
