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

## Layout

```
config/        defaults, parameter dataclass
clients/       yfinance OHLC fetcher
models/        Trade, BacktestResult, Signal
strategies/    dip_buy.py, pop_short.py (pure functions of OHLC)
backtest/      engine + reporter
forward/       today's signal generator
scripts/       backtest_one, backtest_many, todays_signals, validate_against_excel
tests/         pytest fixtures + unit tests for each exit path
data/          cached OHLC + run outputs
```

## Quickstart

```powershell
python -m pip install -r requirements.txt
# backtest one symbol over 100 days
python scripts/backtest_one.py NVDA --side buy --days 100
# backtest a list (one symbol per line) with both sides
python scripts/backtest_many.py data/symbols.txt --days 100
# get today's forward-test signals
python scripts/todays_signals.py data/symbols.txt
# sanity-check against the spreadsheet NVDA Buy row
python scripts/validate_against_excel.py
```

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
