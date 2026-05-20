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

## Current state (2026-05-20)
- Four /done-verified contracts: vol-adj-dip-buy (build), ibkr-data-tv-forward
  (data swap), intraday-resolution-backtest (5-min realism), optimize-tp-sl
  (optimizer + OOS/walk-forward/Monte-Carlo). 38 pytest tests passing.
- **Data: IBKR (paper 4002) for backtest. yfinance BANNED. Forward exec = Jeff's
  MCP server (details still pending).**
- **Realism finding (NVDA buy, 69d):** daily model +$19,942 (19.9%) vs
  intraday-realistic +$4,364 (4.4%) — ~78% cut; 6 of 12 same-day wins were
  sequencing artifacts; stops gap through. Daily ~matches Excel tic-for-tic.
- **IN PROGRESS — TP/SL optimization:** pipeline built + verified; 10-name
  subset 2yr 5-min data was FETCHING when the session paused (3/10 cached).
  RESUME: re-run `python scripts/fetch_history.py data/symbols_opt.txt --years 2`
  (cached symbols skip), then `python scripts/optimize.py data/symbols_opt.txt
  --years 2`. Optimizes TP/SL per side, reward<=3x risk, with OOS + walk-forward
  + Monte-Carlo verdict. NO RESULTS YET.
- Reference episodes: exp-20260519-018/027/028/033/034/035, exp-20260520-001.

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

## Next steps
1. **Finish the optimization run** (data fetch was interrupted at 3/10) —
   re-fetch then `scripts/optimize.py`; report per-side TP/SL + OOS/WF/MC.
2. **Expand to the full Excel watchlist** (data/symbols.txt) once the subset
   result looks robust.
3. **MCP executor** (forward/executor.py) — BLOCKED on Jeff providing: MCP
   server launch command, broker, and order tools (place / bracket-OCO /
   cancel / positions / balance). Forward test = real orders via MCP.
4. Finviz screener integration (auto-build the watchlist from wedge-up/-down).
5. Sector ETF correlation filter (Lookup Table maps each ticker -> SPDR_ETF).

## Operational notes
- IB Gateway logs out daily; needs re-login + API enabled on 4002 each session.
  My data scripts connect-then-disconnect, so the Gateway showing "no client"
  between runs is normal.
- mem0 (Docker: Qdrant 6333 + Ollama 11434) must be up for semantic memory;
  reconnect a dropped mem0 MCP via `/mcp`.
- Optimization: reward<=3x risk = (sigma_mult+limit_mult) <= 3*stop_mult.
  Trailing sigma (SIGMA_LOOKBACK=100) avoids walk-forward look-ahead.

## Task Completer overrides
- Acceptance criterion for any strategy change: validation script
  (`scripts/validate_against_excel.py`) still matches NVDA Buy reference
  within $1,000 on $100k notional.
- Smoke command after edits to strategies/ or backtest/: `pytest tests/ -q`
- The Excel workbook in `Strategy Relevant/` is ground truth — never edit it.
