---
task: intraday-resolution-backtest
status: verified
session_id: 95d775ad-3191-4acf-ad8a-087d5a3910c9
started_at: 2026-05-19T03:00:00Z
started_at_commit: f649bae
verified_at: 2026-05-19T04:00:00Z
---

# Task: intraday-resolution-backtest

## Goal
Replace the daily-bar fill/exit approximation with a granular 5-min,
extended-hours resolver so the backtest reflects reality before live trading.
Three user-mandated changes (2026-05-19): (1) hold a position past 20 days
until TP or stop actually triggers (no time cap); (2) model stops with
extended-hours fills to reduce gap risk, and fill at the gap-open when price
jumps the level through the closed window; (3) use 5-min bars to verify the
entry actually filled and to determine whether TP or stop is hit FIRST — never
assume a fill or a favorable sequence.

## Acceptance criteria
- `clients/ibkr_client.py` gains `fetch_intraday(symbol, days, *,
  bar_size="5 mins", use_rth=False, end_date=None)` returning chronological
  bars (timestamp, OHLC, is_rth). Chunks requests to cover the window; caches.
- New `backtest/intraday_resolver.py` resolves one daily signal vs the
  intraday bars:
  - Entry fills RTH-only, only if an RTH bar trades to the limit; fill at the
    limit price (conservative).
  - After fill, walk bars forward (RTH + extended) to the FIRST of TP / stop.
  - Stop: fill at stop price if a bar's range crosses it during an open
    period; if a bar OPENS beyond the stop (gap), fill at that open.
  - TP: fill at TP price when a bar's range reaches it (conservative; gap-ups
    not credited above TP).
  - Same bar contains both TP and stop -> assume STOP (adverse) first.
  - Hold to resolution: no 20-day cap. If unresolved at data end, mark the
    trade still-open (mark-to-market at last close), reported separately.
- `backtest/engine.py` gains an intraday backtest path that uses daily bars
  for sigma + per-day levels and intraday bars for resolution.
- `scripts/backtest_one.py --intraday` runs end-to-end on NVDA.
- Tests in `tests/test_intraday_resolver.py` cover: no-fill, intraday TP,
  intraday stop, multi-day TP-first, multi-day stop-first, gap-through-stop
  (fill at open), same-bar tie -> stop, hold-and-resolve-after-20-days,
  never-resolves (open at end), and TP-before-entry -> NOT a same-day win.
- `pytest tests/ -q` green. No file > 250 lines. `strategies/` imports no
  data lib.

## Files likely to be touched
- `clients/ibkr_client.py` (add fetch_intraday + IntradayBar)
- `models/trade.py` (maybe: open/unrealized flag on Trade)
- `config/settings.py` (bar_size, exit_extended_hours, entry_session, tie-break)
- `backtest/intraday_resolver.py` (NEW)
- `backtest/engine.py` (intraday path)
- `scripts/backtest_one.py` (--intraday flag)
- `tests/test_intraday_resolver.py` (NEW)

## Out of scope
- 1-min granularity (5-min chosen; can add later).
- Entry fills in extended hours (entry is RTH-only by decision).
- Live order placement / MCP executor (next task).
- Re-validating the daily engine (kept as a fast approximation).

## Notes
- IBKR intraday confirmed: 5-min useRTH=False covers 04:00-19:55 ET.
- is_rth = 09:30 <= bar_time < 16:00 ET.
- sigma stays daily (stdev of daily High-Low).
- Residual gap risk: 20:00-04:00 ET dead window can't be hedged; model fills
  at next bar open there.
