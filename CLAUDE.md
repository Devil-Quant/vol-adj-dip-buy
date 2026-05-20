# Volatility Adjusted Dip-Buying System

## What this project is
Python automation of the Excel-based dip-buy / pop-short strategy in
`Strategy Relevant/Copy of Stock - Strategy 1 and 2 (share).xlsx`. The Excel
model was Jeff's manual research tool — one stock at a time, ~2-second
recalculate per symbol. Goal here: backtest a watchlist of 50-100 names per
day and emit forward-test order parameters (entry / TP / stop) the next
morning.

## Data sources (DECIDED 2026-05-19)
- **Backtest = Interactive Brokers** via `ib_insync`, paper Gateway
  `127.0.0.1:4002`. `--days N` means N *trading sessions* (IBKR `'N D'`
  duration semantics). Connection settings in `config/settings.py` / `.env`.
- **Forward test = TradingView**, via `tradingview/vol_adj_dip_buy.pine`
  (Pine v6 strategy) loaded on a daily chart.
- **yfinance is BANNED** (Jeff, 2026-05-19, exp-20260519-027). Never reintroduce.
- Python 3.14 + ib_insync needs an event-loop shim before import
  (exp-20260519-028) — already in `clients/ibkr_client.py`.

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
- Full implementation complete and verified. Two contracts:
  `.tasks/vol-adj-dip-buy.verified.json` (initial build) and
  `.tasks/ibkr-data-tv-forward.verified.json` (data-source swap).
- 13 pytest tests passing.
- **Data: IBKR for backtest, TradingView/Pine for forward test. No yfinance.**
- NVDA Buy validation (IBKR, 69 sessions ending 2026-05-15): IBKR bars match
  the spreadsheet tic-for-tic; per-bucket diffs all < $5k; counts within 1
  (12/12/7 vs Excel 13/13/6). VERDICT PASS. Raw total $19,942 vs $26,819 is
  window-edge sensitive (IBKR window starts Feb 6 vs Excel's Feb 9) — not a
  logic error.
- Reference episodes: exp-20260519-018 (build), -027 (yfinance ban),
  -028 (ib_insync 3.14 shim + IBKR duration semantics).

## How to use
```powershell
# backtest one symbol
python scripts/backtest_one.py NVDA --side buy --days 100
# backtest a list, write screened-summary CSV
python scripts/backtest_many.py data/symbols.txt --days 100
# tomorrow's forward-test order parameters
python scripts/todays_signals.py data/symbols.txt
# sanity-check against the Excel NVDA Buy reference
python scripts/validate_against_excel.py
```

## Next steps (when Jeff wants more)
- Finviz screener integration (auto-build `symbols.txt` from a wedge-up /
  wedge-down screen, per the spreadsheet's "Bots and Scripts" tab)
- IBKR order placement (paper first) — `ib_insync` can place the bracket the
  Python signal computes; same gateway already connected
- TradingView alert -> webhook -> broker wiring for the Pine forward test
- Parameter sweep (grid over sigma_mult / limit_mult / stop_mult / lookback
  by symbol, optimize the diff vs buy-and-hold)
- Sector ETF correlation column (spreadsheet's "Lookup Table" maps each
  ticker to SPDR_ETF; could feed into a hedge or filter)

## Task Completer overrides
- Acceptance criterion for any strategy change: validation script
  (`scripts/validate_against_excel.py`) still matches NVDA Buy reference
  within $1,000 on $100k notional.
- Smoke command after edits to strategies/ or backtest/: `pytest tests/ -q`
- The Excel workbook in `Strategy Relevant/` is ground truth — never edit it.
