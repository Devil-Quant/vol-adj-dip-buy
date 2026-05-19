# Volatility Adjusted Dip-Buying System

## What this project is
Python automation of the Excel-based dip-buy / pop-short strategy in
`Strategy Relevant/Copy of Stock - Strategy 1 and 2 (share).xlsx`. The Excel
model was Jeff's manual research tool — one stock at a time, ~2-second
recalculate per symbol. Goal here: backtest a watchlist of 50-100 names per
day and emit forward-test order parameters (entry / TP / stop) the next
morning.

## Strategy (one paragraph)
For each day `i` with prior close `C_{i-1}` and rolling stdev of daily
high-low spread `sigma`:
- Buy entry limit at `C_{i-1} - sigma_mult * sigma`. Fills if today's
  Low <= entry <= today's High. Same-day TP at `C_{i-1} + limit_mult * sigma`
  (so buy-TP spread = `(sigma_mult + limit_mult) * sigma`). Stop at
  `entry - 3 * sigma`. If still open at close, track next 20 trading days:
  whichever of TP / stop hits first wins. If neither, exit at close of day
  +24 (Excel `AG` column hardcoded to row +24).
- Short mirrors above with `C_{i-1} + sigma_mult * sigma` entry, cover at
  `entry - limit_mult * sigma`, stop at `entry + 3 * sigma`.

## Default parameters (match spreadsheet's NVDA Buy snapshot)
- `sigma_mult = 1.0`, `limit_mult = 0.5` (Buy), `0.75` (Short), `stop_mult = 3.0`
- `lookback_days = 100`, `holding_window = 20`, `holding_max = 24`
- `order_size_usd = 100_000`

## Validation reference
NVDA Buy with these defaults on the spreadsheet's 2026-05-15 snapshot:
- 69 trading days
- 13 intraday fills (`AA3` sum = $23,638.97)
- 19 open positions split 13 TP / 6 stop (`AF3` sum = $24,348.42, `AE3` sum = -$21,168.35)
- 0 day-24 exits (`AG3` sum = 0)
- **Strategy total: $26,819.04** (= 26.82% on $100k)
- Buy-and-hold over the same window: 16.99%, so strategy +9.83% diff.

If my engine outputs differ materially (>$1k on $100k or wrong counts), the
strategy implementation is wrong.

## Current state (2026-05-19)
- Project skeleton created (config / clients / models / strategies / backtest /
  forward / scripts / tests / data)
- git initialised
- Excel decoded; strategy formulas understood end-to-end

## Next steps
- Implement strategy core, backtest engine, forward signal generator
- Validate against NVDA reference number above
- Wire up multi-symbol watchlist scripts

## Task Completer overrides
- Acceptance criterion for any strategy change: validation script
  (`scripts/validate_against_excel.py`) still matches NVDA Buy reference
  within $1,000 on $100k notional.
- Smoke command after edits to strategies/ or backtest/: `pytest tests/ -q`
- The Excel workbook in `Strategy Relevant/` is ground truth — never edit it.
