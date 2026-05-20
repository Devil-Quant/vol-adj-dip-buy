"""Backtest runners. `run_backtest` = daily-bar approximation (matches the
spreadsheet). `run_backtest_intraday` = granular 5-min resolution: daily bars
give sigma + per-day entry/TP/stop levels, intraday bars resolve fills/exits
with no look-ahead optimism and hold-to-resolution."""
from __future__ import annotations

from typing import Sequence

from config.settings import StrategyParams
from models.trade import BacktestResult, ExitReason
from strategies.dip_buy import simulate_buy
from strategies.pop_short import simulate_short
from strategies.common import hl_spread_stdev, compute_levels
from backtest.intraday_resolver import resolve_trade


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
        result.overnight_count += 1  # any filled non-intraday position
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
                          params: StrategyParams) -> BacktestResult:
    """Granular backtest: daily bars set sigma + per-day levels; intraday bars
    resolve each trade via `resolve_trade` (RTH entry, gap-aware exits, held to
    resolution)."""
    if len(daily_bars) < 3:
        raise ValueError(f"{symbol}: need >=3 daily bars, got {len(daily_bars)}")
    if not intraday_bars:
        raise ValueError(f"{symbol}: no intraday bars supplied")

    sigma = hl_spread_stdev(daily_bars)
    # date -> first index in the intraday stream (bars are chronological)
    day_start: dict = {}
    for idx, b in enumerate(intraday_bars):
        day_start.setdefault(b.d, idx)

    trades = []
    for i in range(1, len(daily_bars)):
        entry_date = daily_bars[i].d
        if entry_date not in day_start:
            continue  # no intraday coverage for this session
        prev_close = daily_bars[i - 1].close
        entry, tp, stop = compute_levels(
            params.side, prev_close, sigma,
            params.sigma_mult, params.limit_mult, params.stop_mult,
        )
        shares = params.order_size_usd / entry
        slice_bars = intraday_bars[day_start[entry_date]:]
        trades.append(resolve_trade(
            entry_date=entry_date, side=params.side, entry_limit=entry,
            tp_price=tp, stop_price=stop, shares=shares, bars=slice_bars,
        ))

    result = _new_result(symbol, params, len(daily_bars), sigma, daily_bars)
    _tally(result, trades)
    return result
