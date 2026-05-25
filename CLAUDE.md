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

## Current state (2026-05-25) — STRATEGY FAMILY REJECTED; pivoted to forecasting research
- **The Excel dip-buy / pop-short (and an OCO-fade variant) has NO real edge.** Proven:
  - **Daily-bar fill illusion:** the sheet books fills + same-day TPs on daily bars,
    assuming an intraday order that often didn't happen. NVDA Buy +26.8% (Excel) ->
    +19.9% (faithful daily) -> **+4.4% (realistic 5-min)**, ~78-84% cut.
  - **Diluted beta, not alpha:** realistic P&L is a fraction of buy-and-hold (NVDA
    turned B&H +21.5% into +4.4%; 10-name set realistic +9% vs B&H +58.7%). "All
    symbols positive" = melt-up, not edge.
  - **Optimization (no RR cap) overfits BOTH sides:** buy optimal sigma1.0/TP2.0/stop3.0
    +$486k IS but OOS -$136k, MC OOS 24%; short loses at EVERY param (best -$1.04M, MC
    0%). Entry also optimized (1sigma already optimal; wide 0.25-2.5 grid confirms).
  - Validation audited end-to-end (OOS / walk-forward / Monte-Carlo) in methodology.html.
- **Same-day-win nuance (Jeff-corrected, exp-20260522-053):** of NVDA's 13 claimed
  same-day wins, 8 mislabeled — but held to resolution 7 were still TP-wins (1-3d
  later), 1 stop. Across 18 tickers 30 of 212 (~14%) became losses. It's a TIMING
  error, NOT fabricated profit.
- **Forecasting pivot:** built `forecast/` harness (features/targets/walkforward/implied).
  Daily VOLATILITY is forecastable (SPY range R2~0.61) but ~all EWMA persistence; beats
  30d VIX +11.7% but that's the WRONG benchmark (need VIX1D/0DTE). DIRECTION not
  forecastable (AUC~0.50). Thesis: "predict the cloud, not the dot."
- **Dashboards (`reports/`, served on :8753):** dashboard.html (Excel review),
  screened-momentum-dashboard.html (audited an external ChatGPT backtest of the same
  strategy = same diluted-beta verdict), methodology.html (validation audit + charts).
- 49 pytest tests passing. Data: IBKR cached (daily 620d; 5-min 2yr for 10 opt + 8
  movers; SPY + VIX 15yr daily). yfinance BANNED.
- Reference episodes: exp-20260522-012/013/022/042/044/047/049/053/057/058,
  exp-20260523-003/004.

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
# daily forecastability harness (vol + direction vs naive baselines)
python scripts/forecast_report.py
# SPY range forecast vs VIX implied (horse race)
python scripts/implied_vol_report.py
# serve the dashboards -> open http://localhost:8753/dashboard.html
python -m http.server 8753 --bind 127.0.0.1 --directory reports
```

## Next steps
1. **(Open loop, approved) VIX1D / 0-DTE straddle P&L test** — is the vol forecast a
   real trade? Benchmark vs VIX1D (1-day implied), target |close-open| (what a straddle
   pays), simulate straddle P&L net of bid/ask. Beating a stat baseline isn't alpha;
   must beat the tradeable implied after costs.
2. **(Open loop) Screened small-cap / range-bound universe** — the Finviz-wedge universe
   the dip-buy/fade was actually designed for, never run end-to-end. The one regime where
   a fade could plausibly work.
3. **Aim the vol-forecast machinery where MMs are weak** (crypto vol/DVOL, prediction
   markets), NOT SPX — edges live in inefficient venues, not the most-competed one.
4. **MCP executor** (forward/executor.py) — BLOCKED on Jeff providing MCP server launch
   command, broker, and order tools (place / bracket-OCO / cancel / positions / balance).
5. Finviz screener + sector-ETF filter — lower priority given the strategy rejection.

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
