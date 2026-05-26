# Volatility Adjusted Dip-Buying System

Python implementation of the Excel "Buy" / "Short" strategies in
`Strategy Relevant/Copy of Stock - Strategy 1 and 2 (share).xlsx`.

## Strategy in one paragraph

For each trading day with prior close `C` and rolling std-dev of daily H/L
spread `sigma`:
- **Buy** places a limit at `C - sigma_mult * sigma` (default 1.0sigma below `C`).
  If the day's low reaches it, take-profit fires at `C + limit_mult * sigma`
  (default 0.5sigma above `C`, i.e. spread = 1.5sigma). Stop sits 3sigma below
  the buy fill. Position is tracked over the next 20 trading days; if neither
  TP nor stop hits, exit at close on day +24.
- **Short** mirrors the Buy: entry `C + sigma_mult * sigma`, cover at
  `entry - limit_mult * sigma` (default 0.75sigma), stop at entry + 3sigma.

Order size is `$100,000` notional per fill.

## Data sources
- **Backtest** = Interactive Brokers (`ib_insync` against the paper Gateway,
  `127.0.0.1:4002`). **yfinance is banned.** `--days N` = N *trading sessions*.
- **Forward test** = TradingView. Load `tradingview/vol_adj_dip_buy.pine` on a
  daily chart (see below).

## Layout

```
config/        defaults, parameter dataclass + IBKR connection settings
clients/       IBKR OHLC fetcher (ib_insync)
models/        Trade, BacktestResult, Signal
strategies/    dip_buy.py, pop_short.py (pure functions of OHLC)
backtest/      engine + reporter
forward/       today's signal generator (Python cross-check of the Pine script)
scripts/       backtest_one, backtest_many, todays_signals, validate_against_excel
tradingview/   vol_adj_dip_buy.pine (Pine v6 forward-test strategy)
tests/         pytest fixtures + unit tests for each exit path
data/          cached OHLC + run outputs
```

## Setup (first time / new collaborator)

This repo is safe to share. **All secrets live in your local `.env`, never in
git.** Each person uses their own IBKR paper credentials — no one ever shares
API keys or broker accounts.

```bash
git clone <this-repo-url>
cd "Volatility Adjusted Dip-Buying System"
python -m venv .venv
.venv\Scripts\activate                # Windows  (use: source .venv/bin/activate on mac/linux)
python -m pip install -r requirements.txt
copy .env.example .env                # Windows  (use: cp .env.example .env on mac/linux)
```

Then open `.env` in an editor and set:

- `IBKR_HOST` / `IBKR_PORT` — your local paper Gateway (defaults: `127.0.0.1` / `4002`)
- `IBKR_CLIENT_ID` — any unused integer (the connection ID for your session)
- (`ORDER_SIZE_USD`, `LOOKBACK_DAYS` are optional; defaults match the Excel sheet)

You need your **own** Interactive Brokers paper account (free, ~15-min signup at
interactivebrokers.com) and your own running IB Gateway. Same rule for any
other broker/API used elsewhere in our wider codebase: **each collaborator brings
their own keys — we share only code.**

Verify the install:

```bash
pytest tests/ -q                          # all 49 should pass
python scripts/validate_against_excel.py  # sanity-checks the engine vs the Excel NVDA Buy row
```

To view the analysis dashboards locally:

```bash
python -m http.server 8753 --bind 127.0.0.1 --directory reports
# then open http://localhost:8753/dashboard.html (and methodology.html, screened-momentum-dashboard.html)
```

## Quickstart

Prereqs: IB Gateway (paper) running and logged in, API enabled, port 4002.

```powershell
python -m pip install -r requirements.txt
# backtest one symbol over the last 100 sessions
python scripts/backtest_one.py NVDA --side buy --days 100
# backtest a list (one symbol per line) with both sides
python scripts/backtest_many.py data/symbols.txt --days 100
# today's forward-test order parameters (Python cross-check)
python scripts/todays_signals.py data/symbols.txt
# sanity-check the engine against the spreadsheet NVDA Buy row
python scripts/validate_against_excel.py
```

## Forward test on TradingView
1. Open TradingView, add a daily (1D) chart for the symbol.
2. Pine Editor -> paste `tradingview/vol_adj_dip_buy.pine` -> Add to chart.
3. Pick **Mode** (Dip-Buy / Pop-Short) and tune the sigma multipliers in
   the strategy settings. The three plotted lines are entry / take-profit /
   stop.
4. The Strategy Tester tab shows the on-chart backtest; create an alert on
   the strategy (or on the "entry touched" conditions) for live signals.
- Caveat: the TV strategy holds **one position at a time**; the Python
  backtest models overlapping positions. Use Python for portfolio research,
  TradingView for live execution/alerts.

## Parameter mapping (Excel -> code)

| Excel | Code | Default |
|---|---|---|
| `T3` (Orig Order StdDev mult)        | `sigma_mult`      | 1.0 |
| `T3/2` for Buy, `T3*0.75` for Short  | `limit_mult`      | 0.5 / 0.75 |
| `3*L3`                               | `stop_mult`       | 3.0 |
| `B3` (Days)                          | `lookback_days`   | 100 |
| `AA2` (order size)                   | `order_size_usd`  | 100_000 |
| 20 days (AJ:BC, BE:BX)               | `holding_window`  | 20 |
| 24 days (`D29-T5`)                   | `holding_max`     | 24 |
