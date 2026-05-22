---
task: forecast-volume-v2
status: in_progress
session_id: 95d775ad-3191-4acf-ad8a-087d5a3910c9
started_at: 2026-05-22T01:00:00Z
started_at_commit: 4a8b40a2cf6f9fa63533f31f0b812c3478fefd22
---

# Task: forecast-volume-v2

# Goal
v2 of the forecastability harness: add VOLUME to the daily data path and
engineer volume features (prior-day RVOL, volume trend, dollar-volume z-score),
then re-run the walk-forward harness to answer one question honestly: does
volume add signal BEYOND the free EWMA-of-range persistence baseline (range
target) or lift directional AUC above 0.5? Add SPY as a regime comparison.
Volume features must use ONLY prior-day volume (today's volume is unknown at the
open) — no look-ahead.

# Acceptance criteria
- `OhlcBar` gains a `volume: float = 0.0` field (default keeps all existing
  positional/keyword constructions valid). `fetch_ohlc` requests + stores
  Volume; `_df_to_bars` / `read_daily_cache` read Volume (default 0.0 when the
  column is absent, for old caches).
- 10 opt names + SPY re-fetched daily WITH volume (gateway up), cache overwritten.
- `forecast/features.py` adds `VOLUME_COLS` (rvol, vol_trend, dvol_z) computed
  from prior-day volume only (no look-ahead). Base `FEATURE_COLS` unchanged.
- `scripts/forecast_report.py` DUAL-runs each target: price-only feature set vs
  price+volume feature set, prints both + the delta, so we SEE whether volume
  helps. Auto-includes volume cols only when the data actually has volume.
- New test: a volume feature at row t does NOT change when today's volume is
  mutated (proves no look-ahead). `pytest tests/ -q` green. No file > 250 lines.
- Re-run printed: honest verdict on whether volume beats EWMA / lifts AUC.

# Files likely to be touched
- `clients/ibkr_client.py` (OhlcBar +volume, fetch_ohlc Volume, readers)
- `forecast/features.py` (VOLUME_COLS)
- `scripts/forecast_report.py` (dual-run + SPY)
- `tests/test_forecast.py` (volume no-look-ahead test)
- (data/cache parquets overwritten — not source)

# Out of scope
- AGGR order-flow (crypto-only; that's the separate crypto track, different
  instrument).
- Intraday volume / IntradayBar changes (daily harness only).
- Building a trader. Still only MEASURING forecastability.

# Notes
- Look-ahead trap: at day t's OPEN you do NOT know today's volume. rvol/vol_trend
  /dvol_z must use volume_{<=t-1} only (shift by 1). Test enforces this.
- Old cache parquets lack a Volume column -> readers must default it to 0.0;
  re-fetch overwrites with real volume before the volume harness is meaningful.
- Honest expectation: volume may improve range slightly (volume<->vol link) but
  likely won't rescue direction. Report whatever it actually shows.
