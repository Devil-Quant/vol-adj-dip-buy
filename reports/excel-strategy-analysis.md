# Volatility-Adjusted Dip-Buy / Pop-Short — Strategy Analysis & Verdict

Source workbook: `Strategy Relevant/Copy of Stock - Strategy 1 and 2 (share).xlsx`
(originally a Google Sheet — the data cells are `GOOGLEFINANCE()` pulls).
Analysis date: 2026-05-22. Analyst: Claude. Order size assumed: $100,000/trade.

---

## 1. Bottom line (verdict first)

**The strategy has no demonstrated trading edge. The Excel's headline profit is
largely a daily-bar fill-accounting illusion, not a real, executable return.**

- The Excel logic is **internally correct** — our Python re-implementation
  reproduces it tic-for-tic on matched data.
- But the spreadsheet decides fills and same-day take-profits on **daily** bars,
  which silently assumes intraday price *sequencing* that often didn't happen.
  Re-resolving the exact same trades on **5-minute** bars cuts the result by
  **~78%**.
- NVDA Buy is the validation case: Excel shows **+$26,819 (+26.8%)**; our
  faithful daily engine on IBKR data shows **+$19,942 (+19.9%)**; the
  intraday-realistic engine shows **+$4,364 (+4.4%)**. About **half** the
  "same-day winners" never could have filled in the order they were credited.
- Every robustness test (out-of-sample, walk-forward, Monte-Carlo, a TP/SL
  optimizer, and an OCO fade variant) **rejects** the strategy family on the
  liquid names we tested. The win-rate-vs-P&L signature is textbook
  "fading a trend."

**One honest caveat (see §6.7):** the strategy's *intended* universe was
Finviz-screened small-cap **wedge** setups (TIGR, BTAI, SNAP, …), not the
mega-cap tech we backtested. The *mechanical* illusion (§6.2) is universe-
independent, but the screened small-cap universe was never run end-to-end.

---

## 2. What the strategy is (mechanics, from the actual cells)

Two mirror-image mean-reversion strategies, one volatility unit, $100k per trade.

### 2.1 The volatility unit (σ)
σ = **sample standard deviation of the daily High−Low spread** over the lookback
window. In the sheet: column `L = High − Low` (`L5 = K5 − I5`), and
`Buy!L3 = STDEV(L5:L186)`. (A separate O/C-spread stdev `E3` is computed for
reference but is **not** what sizes the orders.)

### 2.2 Strategy 1 — `Buy` (dip-buy)  *(A1: "Use Finviz to find patterns…")*
For each day with prior close `C`:
- **Entry** (limit): `C − sigma_mult·σ`   — sheet `T4 = L3·T3`, `T3 = 1.0`
- **Same-day TP**: `C + limit_mult·σ`      — sheet `W4 = T4/2` → `0.5·σ`
- **Stop**: `entry − stop_mult·σ`           — `3·σ` ("Long stop order")
- **Fill rule**: filled if that day's `Low ≤ entry ≤ High`.
- If TP not hit same day, the position stays open and the next **20 trading
  days** are scanned; whichever of TP / stop is touched first wins.

### 2.3 Strategy 2 — `Short` (pop-short)  *(A1: "Short when VIX above 17 and Tech Ratings are Sell, Strong Sell")*
Mirror of Buy, plus **two discretionary entry filters**:
- **Entry** (limit, short): `C + sigma_mult·σ`
- **Cover/TP**: `entry − limit_mult·σ`      — sheet `W4 = T4·0.75` → `0.75·σ`
- **Stop**: `entry + 3·σ` (`AC` = "Buy Limit Order 3 StdDev")
- **Regime filter: VIX > 17** AND **analyst tech rating ∈ {Sell, Strong Sell}**.
- 20-day resolution is implemented as two explicit grids: `AJ:BC` (does the stop
  `AC` sit below a future high `K6:K25`? → stopped out) and `BE:BX` (does a
  future low `I6:I25` reach the cover target `W5`? → win); `AH`/`AI` count them.

### 2.4 The "day +24" branch is effectively dead
`AG5 = if(AF5="Sell Loss",(D29−T5)·AD5,"")` exits an unresolved position at the
close of day +24. In every case we examined it sums to **$0** — the 20-day scan
resolves or the position is silently dropped. (NVDA Buy `AG3 = 0`.)

### 2.5 Position sizing
Fixed **$100,000** notional per trade (`Buy!AA2 = 100000`). Shares = 100000 /
fill price; P&L is summed in dollars (`AA3 = sum(AA5:AA201)`).

### 2.6 Per-stock tuned parameters (`Variables` tab)
The sheet did **not** use one global parameter set — it used per-name tuning:

| Stock | Side | Days | sigma_mult | limit_mult | stop_mult |
|------|------|-----|-----------|-----------|----------|
| TIGR | Buy (wedge-up, 3mo) | 20 | 1.5 | 1.0 | 3.0 |
| BTAI | Short (wedge-down, 3mo) | 50 | 1.25 | 0.75 | 2.5 |
| SNAP | — | 100 | 1.0 | 0.5 | 2.0 |
| FVRR | — | custom | 0.75 | — | — |

The NVDA reference snapshot used the **defaults**: `1.0 / 0.5(buy) / 0.75(short)
/ 3.0`, 100-day lookback.

---

## 3. Screening & universe (`Lookup Table`, 190 names)

Entry candidates come from a **Finviz screener** for "strong wedge-up" (Buy) /
"wedge-down" (Short) chart patterns over a 3-month history. The `Lookup Table`
holds the universe with fundamentals pulled from Finviz/TradingView: price,
**relative volume**, market cap, P/E, EPS growth, **Average daily range %**,
sector, **analyst rating**, and a **SPDR sector-ETF** mapping (`SPDR_ETF`,
`SPDR_Sector`). The intended watchlist (`Variables` A2:A18) is dominated by
**small/mid-cap, high-range, beaten-down names** (TIGR, BTAI, SNAP, FVRR, EPZM,
ETSY, NVTA, IMUX, EGY, LTHM, TDOC, MNKD, IMGN, IMMU, CX) — **not** mega-cap tech.

---

## 4. Dashboard & benchmarking (`BUY Screened Summary`)

Each symbol gets a BUY row and a SHORT row pulling totals from the engine tabs,
then benchmarks the result:
- **Strategy %** `Q = ((100000 + buyP&L + shortP&L)/100000) − 1`
- **Buy-and-hold %** `O` over the same window, and **Diff** `R = Q − O`
- Comparison to **S&P / NASDAQ / DOW** (`AA/AB/AC`) and **sector-ETF
  correlation** (Short tab `CE:` "Correlation % each day", `DK/DL` ETF map).

NVDA reference row (computed values in the sheet):

| | Strategy $ | Intraday exec $ | TP (≤20d) $ | Stop (≤20d) $ | Day+24 $ | Days |
|---|---|---|---|---|---|---|
| NVDA **Buy** | 26,819.04 | 23,638.97 | 24,348.42 | −21,168.35 | 0 | 69 |
| NVDA **Short** | 868.28 | 21,230.63 | 4,643.11 | −25,005.45 | 0 | 69 |

Buy-and-hold over the window = **16.99%**; Buy strategy = **26.82%** (Diff
+9.83%). The Short added almost nothing (**+0.87%**).

---

## 5. Intended automation (`Bots and Scripts`, `Variables` notes)

Jeff's design (not yet built):
- **Bot1** — in the first 3 minutes of the session, scan for stocks that dropped
  1–2σ from the prior close; re-run every 3 min until 10:00. Emit a candidate
  list.
- **Bot2** — run that list through the Buy strategy and rank by win rate +
  intraday execution rate.
- **Today's manual process** (Jeff's own words): type a symbol into the summary
  `B2`, wait ~2 s for recalculation, copy `B2:L2`, paste-as-values into the
  `Database` tab. He notes it is "very manual" and he has only run the Buy side,
  100 days, default params. The goal: **100 stocks/day** from the Finviz
  wedge screen — described as "a multivariable Design of Experiments to find
  correlation."

> This is exactly what the Python automation in this repo replaces:
> `backtest_many.py` (watchlist screening), `todays_signals.py` (next-morning
> order params), and the IBKR data layer — no 2-second-per-symbol manual paste.

---

## 6. Our backtest verdict (what the analysis found)

### 6.1 Fidelity — the Python engine matches Excel tic-for-tic
On matched data the re-implementation reproduces entry/TP/stop and the fill/scan
counts to the penny (NVDA, σ = 2.3334 on the IBKR 69-session window). The Excel
**logic is correct**; differences in grand totals come only from data-date
differences between IBKR and the sheet's GOOGLEFINANCE snapshot.

### 6.2 The daily-model illusion — ~78% of the profit is not executable
Re-resolving the **identical** trades on 5-minute bars (RTH-only entries,
first-touch TP/stop, gap-aware stops, hold-to-resolution):

| NVDA Buy, 69 sessions | Result |
|---|---|
| Excel snapshot | +$26,819 (26.8%) |
| Faithful **daily** engine (IBKR) | +$19,942 (19.9%) |
| **Intraday-realistic** engine | **+$4,364 (4.4%)** |

About **half** of the same-day "wins" were sequencing artifacts: the daily bar
credits both an entry fill *and* a same-day TP without checking whether the low
(entry) actually occurred *before* the high (TP). Stops also **gap through** on
the open intraday but are filled at the exact stop price in the daily model.

### 6.3 Ablation — fills, not σ or code, drive the "edge"
Swapping our trailing σ for the Excel whole-window σ, and isolating each
component, leaves the daily result robust and the intraday result poor. The
**fill model** is the single variable that explains the gap — i.e. the profit is
a fill-accounting artifact, not alpha.

### 6.4 Optimization — OOS / walk-forward / Monte-Carlo all reject
A TP/SL grid optimizer (reward ≤ 3× risk) on 10 names, 2 yr of 5-min data:
in-sample Buy looked great (+$659k) but **OOS −$100k, walk-forward −$245k,
Monte-Carlo prob(profit) ≈ 21%**; the Short side showed **0%**. No robust
parameter set exists.

### 6.5 OCO fade variant — loses at every stop width
A bidirectional fade (long −σ / short +σ, OCO) swept across stop widths on
1-minute data loses at **every** width; win rate climbs 13%→57% while P&L gets
**worse** (−$755k → −$979k), all OOS negative, MC 0%. That win-rate-up /
P&L-down inversion is the diagnostic fingerprint of **fading a trend**.

### 6.6 Follow-on (after rejecting the strategy)
- **Direction** (daily up/down) is **not** forecastable from price (OOS AUC
  ≈ 0.50; the always-up base rate beats the model).
- **Volatility/range** *is* forecastable, but on single names it's ~entirely
  free EWMA persistence; only the **index (SPY)** shows real incremental skill
  (R² 0.50→0.61). That skill is not a trade unless it beats the **option-implied**
  vol after costs — untested, and SPX is the worst arena to try (see the
  forecast reports / episodes exp-20260522-012/013/022).

### 6.7 Honest caveat — the intended universe was not the test universe
We rejected the strategy on **liquid mega/large-cap tech** (NVDA, AVGO, TSLA,
MU, AMD, INTC, ORCL, CRWD, IONQ, RKLB). The sheet's intended universe was
**Finviz-screened high-range small-caps with wedge patterns**. The §6.2
mechanical illusion is universe-independent (it's about fill sequencing), so the
core verdict holds. But whether a *screened* small-cap wedge universe behaves
differently — more genuine mean reversion, less trend — was **not** run
end-to-end. That is the one open loop if a final, fair test is wanted.

---

## 7. Why it doesn't work (root cause)

1. **It fades, and the test names trend.** Mean-reversion entries get
   adverse-selected: you're filled precisely when price keeps going (the dip
   that becomes a downtrend), so winners are capped at TP while losers run to the
   3σ stop. Expectancy is negative regardless of stop width.
2. **The daily model fabricates same-day wins** it can't sequence (§6.2).
3. **No edge at the ±σ/daily scale** on liquid instruments — the easy
   mean-reversion was arbitraged away long ago.

---

## 8. What's salvageable

- **The automation is the real deliverable** and it's built: watchlist
  backtesting, next-morning signal generation, an IBKR data layer, an optimizer,
  and an honest validation harness (OOS/WF/MC). The 2-second manual paste loop is
  gone.
- **Volatility forecasting** is the one genuine skill found — but monetizing it
  requires beating market-maker implied vol, which is implausible in SPX. The
  same machinery aimed where MMs are weak (illiquid options, crypto vol,
  prediction markets) is the productive direction.
- **If the strategy itself deserves a final fair trial:** run it on the
  *screened small-cap wedge* universe (§6.7) with the intraday-realistic engine —
  the only environment it was designed for that we never tested.

---

## Appendix — engine cell map (per-day row, Buy/Short)

| Col | Meaning | Formula (row 5) |
|---|---|---|
| B / D / I / K | Open / Close / Low / High | `GOOGLEFINANCE` |
| E | O/C spread | `=D5−B5` |
| F | Up / Down | `=IF(E5>0,"Up","Down")` |
| L | **H/L spread** (σ basis) | `=K5−I5` |
| L3 | **σ** | `=STDEV(L5:L186)` |
| T4 | entry offset | `=L3·T3` (T3=sigma_mult) |
| W4 | TP offset | `=T4/2` (Buy) / `=T4·0.75` (Short) |
| AC | 3σ stop level | "Sell/Buy Limit Order 3 StdDev" |
| AD | shares open | `100000 / fill` |
| AE / AF | stop-out / TP within 20d | counted via `AH`/`AI` |
| AG | day +24 exit (dead) | `=if(AF="Sell Loss",(D29−T5)·AD5,"")` |
| AA3 | **strategy total $** | `=sum(AA5:AA201)` |
| AJ:BC (Short) | stop-hit grid vs future highs | `=if(AC5<K6,"YES","NO")` … |
| BE:BX (Short) | TP-hit grid vs future lows | `=if(I6<W5,"YES","NO")` … |
