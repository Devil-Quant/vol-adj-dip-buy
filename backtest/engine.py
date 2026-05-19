"""Backtest runner — given bars + params, produce a BacktestResult."""
from __future__ import annotations

from typing import Sequence

from config.settings import StrategyParams
from models.trade import BacktestResult, ExitReason
from strategies.dip_buy import simulate_buy
from strategies.pop_short import simulate_short
from strategies.common import hl_spread_stdev


def run_backtest(symbol: str, bars: Sequence, params: StrategyParams) -> BacktestResult:
    """Run the strategy over `bars` and roll up into the four buckets that
    match the spreadsheet's `BUY Screened Summary` row."""
    if len(bars) < 3:
        raise ValueError(f"{symbol}: need >=3 bars, got {len(bars)}")

    if params.side == "buy":
        trades = simulate_buy(bars, params)
    elif params.side == "short":
        trades = simulate_short(bars, params)
    else:
        raise ValueError(f"unknown side {params.side!r}")

    result = BacktestResult(
        symbol=symbol, side=params.side,
        trading_days=len(bars), sigma=hl_spread_stdev(bars), trades=trades,
    )

    for t in trades:
        if not t.filled or t.pnl_usd is None:
            continue
        if t.exit_reason == ExitReason.INTRADAY_TP:
            result.intraday_pnl += t.pnl_usd
            result.intraday_count += 1
            continue
        # any non-intraday filled trade is an "open till next" position
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

    if len(bars) >= 2:
        first_close = bars[0].close
        last_close = bars[-1].close
        if first_close > 0:
            result.buy_and_hold_pct = (last_close - first_close) / first_close

    return result
