---
task: forecast-harness
status: verified
session_id: 95d775ad-3191-4acf-ad8a-087d5a3910c9
started_at: 2026-05-22T00:00:00Z
started_at_commit: a79f5d155f7008c353eb13c9e3cb2561d2ad50f5
verified_at: 2026-05-22T00:30:00Z
---

# Task: forecast-harness

# Goal
Build an honest daily forecastability harness: predict TRACTABLE targets
(today's realized RANGE/volatility, and today's open->close DIRECTION) from
features known at the OPEN (gap, prior range, trailing vol, momentum, trend,
day-of-week), using simple regularized sklearn models, validated WALK-FORWARD
out-of-sample against naive BASELINES. The point is a truth-detector: does any
feature signal beat the baseline OOS, or is it hindsight? No look-ahead.

# Acceptance criteria
- `forecast/features.py` builds a per-day feature frame using ONLY data
  available at day t's open (prior bars shifted + today's open/gap). No leakage.
- `forecast/targets.py` builds: range target (today (H-L)/open) and direction
  target (today close > open).
- `forecast/walkforward.py` runs expanding walk-forward: train on past, predict
  the next block, pooled across symbols BY DATE (time-ordered, no leakage);
  range via Ridge (report MAE + R2 vs baselines = yesterday's range and
  EWMA-of-range); direction via LogisticRegression (report accuracy + ROC-AUC
  vs base-rate). Standardize features.
- `scripts/forecast_report.py` loads cached daily for a symbol list, runs both,
  prints a report: model-vs-baseline per target + a clear "signal / no signal"
  read.
- New tests verify: features have no look-ahead (a feature at row t doesn't use
  bar t's H/L/close), walk-forward train indices precede test indices, baseline
  computation. `pytest tests/ -q` green. No file > 250 lines.

# Files likely to be touched
- `forecast/__init__.py` (exists), `forecast/features.py` (NEW),
  `forecast/targets.py` (NEW), `forecast/walkforward.py` (NEW)
- `scripts/forecast_report.py` (NEW)
- `tests/test_forecast.py` (NEW)

# Out of scope
- Volume / RVOL features and AGGR order-flow (need a re-fetch WITH volume +
  gateway up) — v2.
- SPY / long-history (gateway down; first read on cached 5-stock daily ~2.5yr).
- Turning a signal into a trader (this only MEASURES forecastability).
- Complex ML (deliberately simple/regularized to avoid the overfit trap).

# Notes
- Targets are "predict the day at its open": features <= open_t, target uses
  H_t/L_t/close_t. Rigorously avoid look-ahead (shift prior-bar features by 1).
- Range/vol is the high-signal target; direction will likely barely beat base
  rate (report honestly either way).
- Baseline to BEAT for range = EWMA-of-prior-range (vol persistence), not just
  yesterday's range.
