---
task: optimize-tp-sl
status: in_progress
session_id: 95d775ad-3191-4acf-ad8a-087d5a3910c9
started_at: 2026-05-20T00:00:00Z
started_at_commit: 31fe4a5bc989dbcc820bb03aa762cd491b39638e
---

# Task: optimize-tp-sl

## Goal
Optimize take-profit and stop-loss multipliers (separately for buy and short)
on the intraday-realistic engine, then PROVE the result isn't overfit via
out-of-sample, walk-forward, and Monte Carlo. Objective = total realized P&L
with guardrails; constraint = reward <= 3x risk. Optimize on a 10-name diverse
subset of the Excel watchlist over ~2 years of 5-min data; expand to the full
watchlist later. Trades held to resolution; positions still open as of today
stay open (flagged if older than ~1 week).

## Acceptance criteria
- `scripts/fetch_history.py` fetches daily (deep, for trailing sigma) + 2yr
  5-min for a symbol list, caches, logs progress.
- `run_backtest_intraday` supports TRAILING sigma (per-entry sigma from the
  prior N daily bars) so walk-forward has no sigma look-ahead. Whole-window
  sigma remains the default (keeps the Excel-match validation intact).
- `backtest/optimizer.py`: grid-search (limit_mult x stop_mult) for a given
  side over a symbol set, honoring reward<=3x risk; ranks combos by total
  realized P&L; attributes each trade to its entry-date so windows can be
  sliced without re-running.
- `backtest/validation.py`: out-of-sample split, walk-forward folds (optimize
  on IS window -> evaluate on next OOS window -> roll), and Monte Carlo
  bootstrap (>=1000 resamples) returning P&L/drawdown distribution +
  probability-of-profit.
- `scripts/optimize.py`: orchestrates fetch->optimize->OOS->walk-forward->MC
  for buy and short separately; prints a report and writes results CSV/JSON.
- `pytest tests/ -q` green incl. new tests for optimizer + validation
  (windowing, RR filter, walk-forward fold logic, MC stats).
- No file > 250 lines. strategies/ imports no data lib.

## Files likely to be touched
- `scripts/fetch_history.py` (NEW), `data/symbols_opt.txt` (NEW)
- `backtest/engine.py` (trailing-sigma option)
- `backtest/optimizer.py` (NEW), `backtest/validation.py` (NEW)
- `scripts/optimize.py` (NEW)
- `config/settings.py` (grid defaults / sigma_lookback)
- `tests/test_optimizer.py` (NEW), `tests/test_validation.py` (NEW)

## Out of scope
- Full 35-name universe (subset first; expand after the pipeline is proven).
- Databento integration (IBKR for now).
- Live execution / MCP executor (separate task).
- Optimizing the entry sigma_mult (fixed at 1.0 — only TP & SL per user).

## Notes
- RR is sigma-independent: reward/risk = (sigma_mult + limit_mult)/stop_mult.
  reward<=3x risk -> (1 + limit_mult) <= 3*stop_mult.
- Efficiency: run each (combo x symbol) backtest ONCE over full history, tag
  trades by entry_date, then slice by date window for IS/OOS/folds.
- Walk-forward attribution: a trade belongs to the window of its ENTRY date;
  resolution may use later bars (that's what actually happened, not look-ahead
  on the parameter choice).
- Subset: NVDA AVGO TSLA MU AMD INTC ORCL CRWD IONQ RKLB (mega trenders, semis,
  software, speculative — diverse).
