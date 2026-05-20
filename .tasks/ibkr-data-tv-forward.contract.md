---
task: ibkr-data-tv-forward
status: in_progress
session_id: 95d775ad-3191-4acf-ad8a-087d5a3910c9
started_at: 2026-05-19T01:00:00Z
started_at_commit: 7b58d7141dc6948d26298a1275003435802420b4
---

# Task: ibkr-data-tv-forward

## Goal
Replace the (now-banned) yfinance backtest data source with IBKR
(`ib_insync` against the paper Gateway on 127.0.0.1:4002), and add a
TradingView Pine Script that runs the strategy live for forward testing.
Per Jeff: backtest = IBKR, forward test = TradingView. yfinance is banned
globally (see exp-20260519-027).

## Acceptance criteria
- `clients/ibkr_client.py` exists, exposes `fetch_ohlc(symbol, days, *,
  end_date=None) -> list[OhlcBar]`, connects to the paper Gateway, and
  returns chronological daily TRADES bars. Includes the Python-3.14
  event-loop shim before importing ib_insync.
- `clients/yfinance_client.py` is deleted. No file in the repo imports
  yfinance. `requirements.txt` no longer lists yfinance and lists ib_insync.
- `clients/__init__.py` exports `fetch_ohlc` + `OhlcBar` from ibkr_client.
- All four scripts (`backtest_one`, `backtest_many`, `todays_signals`,
  `validate_against_excel`) import the IBKR `fetch_ohlc` and run end-to-end
  against the live paper gateway.
- `python scripts/validate_against_excel.py` requests ~69 sessions ending on
  the Excel snapshot date (2026-05-15) and prints totals comparable to the
  Excel NVDA Buy reference (~$26,819 on $100k). IBKR data + matched window
  should land at least as close as the yfinance run did ($4,385 drift).
- `tradingview/vol_adj_dip_buy.pine` exists: a Pine v6 `strategy()` that
  computes sigma = sample stdev of daily (high-low) over a lookback input,
  derives entry/tp/stop by mode (Dip-Buy long / Pop-Short short), places a
  limit entry bracketed by limit-TP and stop, force-closes after holdMax
  bars, plots the three levels, and fires alerts. Header comment documents
  the one-position-at-a-time vs Python multi-position difference and the
  Pine population-stdev -> sample-stdev correction.
- `pytest tests/ -q` still green (strategy logic unchanged).
- No file exceeds 250 lines. `strategies/*.py` still imports no data lib.

## Files likely to be touched
- `clients/ibkr_client.py` (NEW)
- `clients/yfinance_client.py` (DELETE)
- `clients/__init__.py`
- `config/settings.py` (add IBKR connection settings)
- `.env.example` (IBKR_HOST / IBKR_PORT / IBKR_CLIENT_ID)
- `requirements.txt` (remove yfinance, add ib_insync)
- `scripts/backtest_one.py`, `scripts/backtest_many.py`,
  `scripts/todays_signals.py`, `scripts/validate_against_excel.py`
- `tradingview/vol_adj_dip_buy.pine` (NEW)
- `README.md`, `CLAUDE.md`

## Out of scope
- Live order execution from Python (forward test is TradingView-driven).
- TradingView webhook -> broker wiring (separate task).
- ib_async migration (the import shim is sufficient for now).
- Multi-position portfolio sim inside Pine (TV strategy holds one at a time).

## Notes
- Event-loop shim is mandatory on Python 3.14 (exp-20260519-028).
- IBKR `'N D'` duration = N trading sessions, not calendar days.
- Pine `ta.stdev` is population stdev; multiply by sqrt(n/(n-1)) for the
  sample stdev Excel/Python use.
- Keep `OhlcBar` dataclass identical so engine/backtest/strategy code is
  untouched — this is a data-source swap, not a logic change.
