"""Pop-short strategy — mirrors Excel `Short` tab logic exactly.

For each day i with prior close C and rolling H/L stdev `sigma`:
  entry_limit = C + sigma_mult * sigma            (T column)
  tp_price    = entry_limit - limit_mult * sigma  (W column, "Buy -$ Stdev PP")
  stop_price  = entry_limit + stop_mult * sigma   (AC column)

Note the asymmetry: Excel hard-codes Short's `W4 = T4 * 0.75` (default
`limit_mult = 0.75`), while Buy uses `W4 = T4 / 2`. We honor the param.

Fill rules (V `SHORT`):
  - "miss" if entry_limit is NOT inside today's [low, high]
  - "Exec" if entry_limit < today.high (short fills when price rallies up)

Same-day cover (X `Exec Buy Order`):
  - "Exec" if tp_price > today.low -> intraday round-trip
  - else "Open" -> tracked next holding_window days

Window scan (AJ:BC stop=high crosses up, BE:BX TP=low crosses down):
  - first day t where high_t > stop_price -> STOP (covered against us)
  - first day t where low_t  < tp_price   -> OVERNIGHT_TP (covered for profit)
  - whichever earlier wins.

Day-max exit (AG): if neither in window, cover at close of row + max_hold.
"""
from __future__ import annotations

from typing import Sequence

from config.settings import StrategyParams
from models.trade import Trade, ExitReason, Signal
from strategies.common import hl_spread_stdev


def simulate_short(
    bars: Sequence, params: StrategyParams, *, sigma_override: float | None = None,
    sigma_by_day: dict | None = None,
) -> list[Trade]:
    """`sigma_by_day` (entry date -> sigma) gives a rolling/trailing sigma
    (Excel-faithful lookback); days without a sigma are skipped. Default uses
    one whole-window sigma. See simulate_buy."""
    if params.side != "short":
        raise ValueError("simulate_short needs side='short'")
    if len(bars) < 2:
        return []

    whole = (sigma_override if sigma_override is not None
             else (None if sigma_by_day is not None else hl_spread_stdev(bars)))

    trades: list[Trade] = []
    for i in range(1, len(bars)):
        prev_close = bars[i - 1].close
        today = bars[i]
        sig = sigma_by_day.get(today.d) if sigma_by_day is not None else whole
        if sig is None or sig <= 0:
            continue  # insufficient trailing history for this day

        entry_limit = prev_close + params.sigma_mult * sig
        tp_price = entry_limit - params.limit_mult * sig
        stop_price = entry_limit + params.stop_mult * sig

        in_range = today.low < entry_limit < today.high
        filled = in_range and entry_limit < today.high
        if not filled:
            trades.append(Trade(
                entry_date=today.d, side="short", entry_limit=entry_limit,
                filled=False, intraday_tp=False, exit_reason=ExitReason.NONE,
            ))
            continue

        shares = params.order_size_usd / entry_limit

        # same-day TP? (cover)
        if today.low <= tp_price:
            pnl = (entry_limit - tp_price) * shares
            trades.append(Trade(
                entry_date=today.d, side="short", entry_limit=entry_limit,
                filled=True, intraday_tp=True, exit_reason=ExitReason.INTRADAY_TP,
                tp_price=tp_price, stop_price=stop_price,
                exit_price=tp_price, exit_date=today.d,
                shares=shares, pnl_usd=pnl, days_held=0,
            ))
            continue

        outcome = _scan_window_short(
            bars=bars, entry_idx=i, tp=tp_price, stop=stop_price,
            window=params.holding_window, max_hold=params.holding_max,
        )
        exit_reason, exit_price, exit_date, days_held = outcome
        pnl = (entry_limit - exit_price) * shares
        trades.append(Trade(
            entry_date=today.d, side="short", entry_limit=entry_limit,
            filled=True, intraday_tp=False, exit_reason=exit_reason,
            tp_price=tp_price, stop_price=stop_price,
            exit_price=exit_price, exit_date=exit_date,
            shares=shares, pnl_usd=pnl, days_held=days_held,
        ))
    return trades


def _scan_window_short(*, bars: Sequence, entry_idx: int, tp: float, stop: float,
                       window: int, max_hold: int):
    last_day = min(entry_idx + window, len(bars) - 1)
    stop_pos = None
    tp_pos = None
    for offset in range(1, last_day - entry_idx + 1):
        bar = bars[entry_idx + offset]
        if stop_pos is None and bar.high > stop:
            stop_pos = offset
        if tp_pos is None and bar.low < tp:
            tp_pos = offset
        if stop_pos is not None and tp_pos is not None:
            break

    if stop_pos is not None and (tp_pos is None or stop_pos < tp_pos):
        bar = bars[entry_idx + stop_pos]
        return ExitReason.STOP, stop, bar.d, stop_pos
    if tp_pos is not None and (stop_pos is None or tp_pos < stop_pos):
        bar = bars[entry_idx + tp_pos]
        return ExitReason.OVERNIGHT_TP, tp, bar.d, tp_pos
    max_idx = entry_idx + max_hold
    if max_idx >= len(bars):
        return ExitReason.DAY_MAX, bars[-1].close, bars[-1].d, len(bars) - 1 - entry_idx
    return ExitReason.DAY_MAX, bars[max_idx].close, bars[max_idx].d, max_hold


def short_signal(
    bars: Sequence, params: StrategyParams, symbol: str,
    *, sigma_override: float | None = None,
) -> Signal:
    if params.side != "short":
        raise ValueError("short_signal needs side='short'")
    if not bars:
        raise ValueError(f"{symbol}: need at least 1 bar to compute a signal")
    if sigma_override is None and len(bars) < 2:
        raise ValueError(f"{symbol}: need at least 2 bars to compute sigma (or pass sigma_override)")
    sigma = sigma_override if sigma_override is not None else hl_spread_stdev(bars)
    last = bars[-1]
    entry_limit = last.close + params.sigma_mult * sigma
    tp_price = entry_limit - params.limit_mult * sigma
    stop_price = entry_limit + params.stop_mult * sigma
    shares = params.order_size_usd / entry_limit
    return Signal(
        symbol=symbol, side="short", asof_date=last.d, prev_close=last.close,
        sigma=sigma, entry_limit=entry_limit, tp_price=tp_price,
        stop_price=stop_price, shares=shares,
    )
