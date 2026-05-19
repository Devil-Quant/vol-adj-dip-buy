---
task: vol-adj-dip-buy
status: verified
session_id: 95d775ad-3191-4acf-ad8a-087d5a3910c9
started_at: 2026-05-19T00:00:00Z
started_at_commit: 199165cb6bc21fca90de40085d79a697d04ff29e
verified_at: 2026-05-19T00:00:00Z
---

# Task: vol-adj-dip-buy

## Goal
Build Python automation of the Excel-based volatility-adjusted dip-buy and
pop-short strategies (defined in `Strategy Relevant/Copy of Stock - Strategy
1 and 2 (share).xlsx`, tabs `Buy` and `Short`) so Jeff can both backtest a
watchlist of stocks and emit forward-test order parameters (entry / TP /
stop / shares) for the next trading day. Today the Excel model runs one
symbol at a time with a 2-second recalc; the Python build replaces that
with a list-driven CLI that targets 50-100 names per run.

## Acceptance criteria
- `pytest tests/ -q` passes (all unit tests green).
- `python scripts/backtest_one.py NVDA --side buy --days 100` runs
  end-to-end, prints a per-trade table + summary, writes a CSV under
  `data/`.
- `python scripts/validate_against_excel.py` fetches NVDA 100-day OHLC and
  prints the four totals (intraday, stop-out, TP, day+24). Result should be
  comparable to the Excel NVDA Buy reference of ~$26,819 strategy total on
  $100k notional; small drift acceptable because yfinance data dates differ
  from the spreadsheet's 2026-05-15 snapshot.
- `python scripts/todays_signals.py data/symbols.txt` runs and prints
  today's `buy_limit / sell_limit / stop / shares` for each symbol.
- `python scripts/backtest_many.py data/symbols.txt --days 100` runs on a
  list of >=5 symbols and emits a screened-summary CSV with the same
  columns as the spreadsheet's `BUY Screened Summary` tab.
- No file exceeds 250 lines.
- `strategies/*.py` does not import `requests` or `yfinance`.
- `clients/*.py` contains no business logic (no entry / TP / stop math).

## Files likely to be touched
- `config/__init__.py` (NEW), `config/settings.py` (NEW)
- `clients/__init__.py` (NEW), `clients/yfinance_client.py` (NEW)
- `models/__init__.py` (NEW), `models/trade.py` (NEW)
- `strategies/__init__.py` (NEW), `strategies/dip_buy.py` (NEW), `strategies/pop_short.py` (NEW)
- `backtest/__init__.py` (NEW), `backtest/engine.py` (NEW), `backtest/reporter.py` (NEW)
- `forward/__init__.py` (NEW), `forward/signals.py` (NEW)
- `scripts/backtest_one.py` (NEW), `scripts/backtest_many.py` (NEW), `scripts/todays_signals.py` (NEW), `scripts/validate_against_excel.py` (NEW)
- `tests/__init__.py` (NEW), `tests/test_dip_buy.py` (NEW), `tests/test_pop_short.py` (NEW)
- `data/symbols.txt` (NEW)

## Out of scope
- Broker / live order placement (Alpaca, IBKR, etc.). Forward signals are
  emitted as numbers; order placement is manual for now.
- Finviz screener integration. The script takes a pre-built symbol list;
  feeding it from a screener is a follow-up task.
- Intraday / sub-daily data. Strategy is daily-bar only, matching Excel.
- Optimization / parameter sweep. The defaults match the spreadsheet's
  hard-coded values; tuning is a follow-up task.

## Notes
- Spreadsheet hard-codes `W4 = T4/2` (Buy) and `W4 = T4*0.75` (Short) — so
  the TP-width multiplier is asymmetric by side. Preserve that.
- Stop is hard-coded `3 * stdev(daily_HL_spread)` in both sheets (column AC).
- Stdev is computed on the daily High-Low spread, not on returns. Replicate
  exactly (Excel `STDEV` = sample stdev, `ddof=1`).
- Day-24 exit (`AG` column) only fires when neither stop nor TP triggers in
  the 20-day window — confirm with the formula trace before coding.
- `Strategy Relevant/Copy of Stock - Strategy 1 and 2 (share).xlsx` is
  ground truth — never modify it. Read-only.
