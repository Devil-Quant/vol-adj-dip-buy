"""Backtest runners + shared intraday trade generation.

`run_backtest` = daily-bar approximation (spreadsheet-equivalent).
`run_backtest_intraday` = granular 5-min resolution; supports TRAILING sigma
(per-entry sigma from the prior N daily bars) so walk-forward optimization has
no sigma look-ahead. The `intraday_trades` / `trailing_sigma_by_day` /
`build_day_start` helpers let the optimizer precompute sigma once and vary only
the TP/SL grid."""
from __future__ import annotations

from typing import Sequence

from config.settings import StrategyParams
from models.trade import BacktestResult, ExitReason
from strategies.dip_buy import simulate_buy
from strategies.pop_short import simulate_short
from strategies.common import hl_spread_stdev, compute_levels
from backtest.intraday_resolver import resolve_trade


def build_day_start(intraday_bars: Sequence) -> dict:
    """date -> first index in the chronological intraday stream."""
    out: dict = {}
    for idx, b in enumerate(intraday_bars):
        out.setdefault(b.d, idx)
    return out


def trailing_sigma_by_day(daily_bars: Sequence, lookback: int) -> dict:
    """Per-entry-day sigma from the prior `lookback` daily H-L spreads (no
    look-ahead): day i (i>=lookback) -> stdev over daily_bars[i-lookback:i]."""
    out: dict = {}
    for i in range(lookback, len(daily_bars)):
        out[daily_bars[i].d] = hl_spread_stdev(daily_bars[i - lookback:i])
    return out


def intraday_trades(daily_bars, intraday_bars, side, sigma_mult, limit_mult,
                    stop_mult, order_size, *, sigma_by_day, day_start) -> list:
    """Generate one Trade per signal day using precomputed sigma_by_day +
    day_start (so the optimizer can reuse them across the TP/SL grid)."""
    trades = []
    for i in range(1, len(daily_bars)):
        entry_date = daily_bars[i].d
        if entry_date not in day_start:
            continue
        sig = sigma_by_day.get(entry_date)
        if sig is None or sig <= 0:
            continue
        entry, tp, stop = compute_levels(side, daily_bars[i - 1].close, sig,
                                         sigma_mult, limit_mult, stop_mult)
        trades.append(resolve_trade(
            entry_date=entry_date, side=side, entry_limit=entry, tp_price=tp,
            stop_price=stop, shares=order_size / entry,
            bars=intraday_bars, start_idx=day_start[entry_date],
        ))
    return trades


def _new_result(symbol: str, params: StrategyParams, n_days: int,
                sigma: float, daily_bars: Sequence) -> BacktestResult:
    result = BacktestResult(symbol=symbol, side=params.side,
                            trading_days=n_days, sigma=sigma)
    if len(daily_bars) >= 2 and daily_bars[0].close > 0:
        result.buy_and_hold_pct = (daily_bars[-1].close - daily_bars[0].close) / daily_bars[0].close
    return result


def _tally(result: BacktestResult, trades) -> None:
    result.trades = trades
    for t in trades:
        if not t.filled or t.pnl_usd is None:
            continue
        if t.exit_reason == ExitReason.INTRADAY_TP:
            result.intraday_pnl += t.pnl_usd
            result.intraday_count += 1
            continue
        result.overnight_count += 1
        if t.exit_reason == ExitReason.STOP:
            result.stop_pnl += t.pnl_usd
            result.stop_count += 1
        elif t.exit_reason == ExitReason.OVERNIGHT_TP:
            result.overnight_tp_pnl += t.pnl_usd
            result.overnight_tp_count += 1
        elif t.exit_reason == ExitReason.DAY_MAX:
            result.day_max_pnl += t.pnl_usd
            result.day_max_count += 1
        elif t.exit_reason == ExitReason.OPEN:
            result.open_pnl += t.pnl_usd
            result.open_count += 1


def run_backtest(symbol: str, bars: Sequence, params: StrategyParams) -> BacktestResult:
    """Daily-bar backtest (spreadsheet-equivalent)."""
    if len(bars) < 3:
        raise ValueError(f"{symbol}: need >=3 bars, got {len(bars)}")
    if params.side == "buy":
        trades = simulate_buy(bars, params)
    elif params.side == "short":
        trades = simulate_short(bars, params)
    else:
        raise ValueError(f"unknown side {params.side!r}")
    result = _new_result(symbol, params, len(bars), hl_spread_stdev(bars), bars)
    _tally(result, trades)
    return result


def run_backtest_intraday(symbol: str, daily_bars: Sequence, intraday_bars: Sequence,
                          params: StrategyParams, *, sigma_lookback=None) -> BacktestResult:
    """Granular 5-min backtest. `sigma_lookback=None` -> whole-window sigma;
    an int -> trailing sigma over that many prior daily bars (walk-forward safe)."""
    if len(daily_bars) < 3:
        raise ValueError(f"{symbol}: need >=3 daily bars, got {len(daily_bars)}")
    if not intraday_bars:
        raise ValueError(f"{symbol}: no intraday bars supplied")

    whole_sigma = hl_spread_stdev(daily_bars)
    day_start = build_day_start(intraday_bars)
    if sigma_lookback is not None:
        sigma_by_day = trailing_sigma_by_day(daily_bars, sigma_lookback)
    else:
        sigma_by_day = {b.d: whole_sigma for b in daily_bars}

    trades = intraday_trades(
        daily_bars, intraday_bars, params.side, params.sigma_mult,
        params.limit_mult, params.stop_mult, params.order_size_usd,
        sigma_by_day=sigma_by_day, day_start=day_start,
    )
    result = _new_result(symbol, params, len(daily_bars), whole_sigma, daily_bars)
    _tally(result, trades)
    return result
