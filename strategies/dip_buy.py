"""Dip-buy strategy — mirrors Excel `Buy` tab logic exactly.

For each day i with prior close C and rolling H/L stdev `sigma`:
  entry_limit = C - sigma_mult * sigma            (T column)
  tp_price    = C + limit_mult * sigma            (W column)
  stop_price  = entry_limit - stop_mult * sigma   (AC column)

Fill rules (column V `BUY`):
  - "miss" if entry_limit is NOT inside today's [low, high]
  - "Exec" if today.low < entry_limit AND today.high > entry_limit
    (low <= entry crosses the limit on the way down)

Same-day TP (X `Exec Sell Order`):
  - "Exec" if today.high >= tp_price -> intraday round-trip
  - else "Open" -> tracked over next holding_window days

Window scan (AJ:BC stop, BE:BX TP):
  - first day t where low_t < stop_price = stop hit (AH = pos)
  - first day t where high_t > tp_price  = TP hit   (AI = pos)
  - whichever is earlier wins; tie not possible per Excel's `<` strict order

Day-max exit (AG `Loss Sale after 21 days`):
  - if neither stop nor TP hits in the window, exit at close of day
    entry_index + holding_max (Excel uses `D{row+24}` for `T5`).
"""
from __future__ import annotations

from typing import Sequence

from config.settings import StrategyParams
from models.trade import Trade, ExitReason, Signal
from strategies.common import hl_spread_stdev


def simulate_buy(bars: Sequence, params: StrategyParams) -> list[Trade]:
    """Walk the bar series and produce a Trade per day that had a valid
    signal. Bars must be in chronological order. `bars` length should
    be >= params.lookback_days; the engine slices accordingly upstream."""
    if params.side != "buy":
        raise ValueError("simulate_buy needs side='buy'")
    if len(bars) < 2:
        return []

    sigma = hl_spread_stdev(bars)
    sigma_off = params.sigma_mult * sigma
    limit_off = params.limit_mult * sigma
    stop_off = params.stop_mult * sigma

    trades: list[Trade] = []
    # i starts at 1 because we need prior close (bars[i-1]) for entry
    for i in range(1, len(bars)):
        prev_close = bars[i - 1].close
        today = bars[i]

        entry_limit = prev_close - sigma_off
        tp_price = prev_close + limit_off
        stop_price = entry_limit - stop_off

        in_range = today.low < entry_limit < today.high
        filled = in_range and today.low < entry_limit
        if not filled:
            trades.append(Trade(
                entry_date=today.d, side="buy", entry_limit=entry_limit,
                filled=False, intraday_tp=False, exit_reason=ExitReason.NONE,
            ))
            continue

        shares = params.order_size_usd / entry_limit

        # same-day TP?
        if today.high >= tp_price:
            pnl = (tp_price - entry_limit) * shares
            trades.append(Trade(
                entry_date=today.d, side="buy", entry_limit=entry_limit,
                filled=True, intraday_tp=True, exit_reason=ExitReason.INTRADAY_TP,
                tp_price=tp_price, stop_price=stop_price,
                exit_price=tp_price, exit_date=today.d,
                shares=shares, pnl_usd=pnl, days_held=0,
            ))
            continue

        # window scan: which hits first?
        outcome = _scan_window_buy(
            bars=bars, entry_idx=i, tp=tp_price, stop=stop_price,
            window=params.holding_window, max_hold=params.holding_max,
        )
        exit_reason, exit_price, exit_date, days_held = outcome
        pnl = (exit_price - entry_limit) * shares
        trades.append(Trade(
            entry_date=today.d, side="buy", entry_limit=entry_limit,
            filled=True, intraday_tp=False, exit_reason=exit_reason,
            tp_price=tp_price, stop_price=stop_price,
            exit_price=exit_price, exit_date=exit_date,
            shares=shares, pnl_usd=pnl, days_held=days_held,
        ))
    return trades


def _scan_window_buy(*, bars: Sequence, entry_idx: int, tp: float, stop: float,
                     window: int, max_hold: int):
    """Return (ExitReason, exit_price, exit_date, days_held).

    Iterates days entry_idx+1 .. entry_idx+window. First day where today.low
    crosses stop -> STOP. First day where today.high crosses tp -> OVERNIGHT_TP.
    The Excel `match` formula scans separate lanes and compares positions;
    the lane with the SMALLER position wins. If neither lane finds a YES,
    fall back to exit at close on entry_idx + max_hold.
    """
    last_day = min(entry_idx + window, len(bars) - 1)
    stop_pos = None
    tp_pos = None
    for offset in range(1, last_day - entry_idx + 1):
        bar = bars[entry_idx + offset]
        if stop_pos is None and bar.low < stop:
            stop_pos = offset
        if tp_pos is None and bar.high > tp:
            tp_pos = offset
        if stop_pos is not None and tp_pos is not None:
            break

    # Excel logic: `IF(AH<AI, stop_exit, tp_exit_or_blank)` with `match` returning
    # "" on no-hit. Comparing position numbers: smaller position fires first.
    if stop_pos is not None and (tp_pos is None or stop_pos < tp_pos):
        bar = bars[entry_idx + stop_pos]
        return ExitReason.STOP, stop, bar.d, stop_pos
    if tp_pos is not None and (stop_pos is None or tp_pos < stop_pos):
        bar = bars[entry_idx + tp_pos]
        return ExitReason.OVERNIGHT_TP, tp, bar.d, tp_pos
    # Neither hit in window — Excel exits at close on row + max_hold
    max_idx = entry_idx + max_hold
    if max_idx >= len(bars):
        # we don't have enough future bars yet (e.g., entered near end of series)
        return ExitReason.DAY_MAX, bars[-1].close, bars[-1].d, len(bars) - 1 - entry_idx
    return ExitReason.DAY_MAX, bars[max_idx].close, bars[max_idx].d, max_hold


def buy_signal(bars: Sequence, params: StrategyParams, symbol: str) -> Signal:
    """Forward-test: emit today's actionable order using the most recent bar
    as the prior close. Caller is responsible for placing orders the next
    morning."""
    if params.side != "buy":
        raise ValueError("buy_signal needs side='buy'")
    if len(bars) < 2:
        raise ValueError(f"{symbol}: need at least 2 bars to compute a signal")
    sigma = hl_spread_stdev(bars)
    last = bars[-1]
    entry_limit = last.close - params.sigma_mult * sigma
    tp_price = last.close + params.limit_mult * sigma
    stop_price = entry_limit - params.stop_mult * sigma
    shares = params.order_size_usd / entry_limit
    return Signal(
        symbol=symbol, side="buy", asof_date=last.d, prev_close=last.close,
        sigma=sigma, entry_limit=entry_limit, tp_price=tp_price,
        stop_price=stop_price, shares=shares,
    )
