---
task: forecast-implied-vol
status: verified
session_id: 95d775ad-3191-4acf-ad8a-087d5a3910c9
started_at: 2026-05-22T02:00:00Z
started_at_commit: 0cb8e161eac72efc4a2e0e8958d585fe91d36083
verified_at: 2026-05-22T02:30:00Z
---

# Task: forecast-implied-vol

# Goal
Decide whether the confirmed SPY range-forecast edge (+10.7% over EWMA, R2 0.61,
exp-20260522-013) is a TRADING edge or already priced in. "Beats a statistical
EWMA" is not the same as "beats the OPTION-IMPLIED range." So horse-race our
forecast against VIX (the market's implied vol) out-of-sample: does our forecast
add information BEYOND VIX for predicting SPY's realized daily range? If
(ours+VIX) beats (VIX-only) OOS, there is orthogonal signal = tradeable. If VIX
subsumes ours, it's priced in = no trade. Honest, ex-ante.

# Acceptance criteria
- `fetch_ohlc` gains a `sec_type="STK"` param (and exchange handling) so it can
  fetch the VIX index (Index('VIX','CBOE'), whatToShow TRADES) as well as stocks.
  Existing stock calls unchanged (default STK).
- VIX daily (~15yr, match SPY 3780d) fetched + cached.
- `forecast/implied.py` builds a VIX implied-range feature aligned to SPY dates
  using ONLY VIX_{t-1} (vix_daily = VIX_close_{t-1}/100/sqrt(252)) — no
  look-ahead — merged into the SPY feature/target frame.
- `scripts/implied_vol_report.py` runs the horse race via walk_forward_range:
  EWMA baseline vs VIX-only vs our-features-only vs our+VIX. Prints OOS MAE/R2
  for each + a clear verdict: does our forecast beat implied / add beyond it?
- New test: the VIX feature at row t uses VIX_{t-1} not VIX_t (no look-ahead);
  alignment drops unmatched dates. `pytest tests/ -q` green. No file > 250 lines.

# Files likely to be touched
- `clients/ibkr_client.py` (sec_type / Index support)
- `forecast/implied.py` (NEW — VIX feature builder)
- `scripts/implied_vol_report.py` (NEW — horse race)
- `tests/test_forecast.py` (VIX no-look-ahead + alignment test)

# Out of scope
- Building a vol trader / options execution.
- ATM-straddle-implied range (VIX is the proxy for now; straddle is a refinement).
- Intraday. AGGR/crypto.

# Notes
- Encompassing test is the point: combined(ours+VIX) vs VIX-only OOS MAE is the
  decisive number. ours-only vs VIX-only is secondary.
- VIX_{t-1} close is the clean no-look-ahead implied input known at SPY open t.
- Reuse walk_forward_range by passing different feature_col sets; the VIX feature
  is just another column in the pooled frame.
- VIX fetch confirmed working: Index('VIX','CBOE'), TRADES, useRTH (probe got
  501 bars/2Y, last 16.73).
