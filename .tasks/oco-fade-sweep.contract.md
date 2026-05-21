---
task: oco-fade-sweep
status: verified
session_id: 95d775ad-3191-4acf-ad8a-087d5a3910c9
started_at: 2026-05-21T00:00:00Z
started_at_commit: 324a60f82140cc1c77e516822908a3980ddcfbf5
verified_at: 2026-05-21T00:30:00Z
---

# Task: oco-fade-sweep

## Goal
Add a bidirectional OCO "fade" variant (Jeff's idea): each day place BOTH a
long limit at C-sigma_mult*sigma and a short limit at C+sigma_mult*sigma;
whichever the price reaches FIRST (RTH) opens, the other cancels; resolve with
tp_mult/stop_mult sigma offsets. Test it with a STOP-WIDTH SWEEP on 1-minute
data (so a tight ~0.2sigma stop can be modeled at finer resolution), reporting
full-sample, in-sample vs out-of-sample, and Monte-Carlo per stop width.

## Acceptance criteria
- `intraday_resolver.resolve_oco_fade` picks direction by first-touch (RTH),
  treats a single bar spanning BOTH levels as ambiguous -> no fill, and reuses
  the shared `_resolve_after_fill` for exit (gap-aware, hold-to-resolution).
- `resolve_trade` refactored to use the same `_resolve_after_fill` (behavior
  unchanged — existing resolver tests still pass).
- `engine.oco_fade_trades` + `optimizer.combo_trades_fade` produce entry-date-
  tagged TradeRecs across symbols.
- `scripts/fetch_history.py` gains `--bar-size` + `--chunk-days` (for 1-min).
- `scripts/sweep_fade.py` sweeps stop widths on cached 1-min data and prints
  full / IS / OOS / MC per width.
- New tests cover fade direction-selection (long-first, short-first, ambiguous
  no-fill, no-touch). `pytest tests/ -q` green. No file > 250 lines.

## Files likely to be touched
- `backtest/intraday_resolver.py` (resolve_oco_fade + _resolve_after_fill)
- `backtest/engine.py` (oco_fade_trades)
- `backtest/optimizer.py` (combo_trades_fade)
- `scripts/fetch_history.py` (--bar-size/--chunk-days)
- `scripts/sweep_fade.py` (NEW), `data/symbols_min.txt` (NEW)
- `tests/test_intraday_resolver.py` (fade tests)

## Out of scope
- Full optimizer/OOS/WF integration of the fade (sweep does IS/OOS + MC only).
- Live execution.
- Whether the strategy is GOOD (that's the empirical result, reported separately).

## Notes
- 1-min IBKR history ~18 months deep; "2 W" (~8640 bars) max per request;
  fetch with --bar-size "1 min" --chunk-days 14.
- A 0.2sigma stop (~$0.47 on NVDA) is near 1-min bar resolution; results at
  that width are still approximate (same-bar tie -> stop).
