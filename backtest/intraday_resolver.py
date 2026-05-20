"""Resolve one day's signal against 5-min (extended-hours) intraday bars.

No look-ahead optimism: the entry only fills if an RTH bar actually trades to
the limit; TP/stop are scanned from the bar AFTER the fill (so a level touched
in the same 5-min bar as the fill is not credited); when one bar contains both
TP and stop, the adverse one (stop) is assumed first; a stop that gaps (the
bar opens beyond it, e.g. after the 20:00-04:00 dead window) fills at the gap
open, not the stop price. Positions are held to resolution — no time cap.

Bars passed in must be chronological and START at the entry day's first bar.
"""
from __future__ import annotations

from datetime import date
from typing import Sequence

from models.trade import Trade, ExitReason


def resolve_trade(
    *,
    entry_date: date,
    side: str,
    entry_limit: float,
    tp_price: float,
    stop_price: float,
    shares: float,
    bars: Sequence,
) -> Trade:
    """`bars` are intraday bars from `entry_date` 04:00 onward."""
    if side not in ("buy", "short"):
        raise ValueError(f"side must be buy/short, got {side!r}")

    no_fill = Trade(
        entry_date=entry_date, side=side, entry_limit=entry_limit,
        filled=False, intraday_tp=False, exit_reason=ExitReason.NONE,
        tp_price=tp_price, stop_price=stop_price,
    )

    # --- 1. Entry fill: RTH bars on entry_date only --------------------------
    fill_i = None
    for i, b in enumerate(bars):
        if b.d != entry_date:
            break  # entry order is good only for its own session
        if not b.is_rth:
            continue
        hit = (b.low <= entry_limit) if side == "buy" else (b.high >= entry_limit)
        if hit:
            fill_i = i
            break
    if fill_i is None:
        return no_fill

    # --- 2. Scan forward (RTH + extended) for the first of TP / stop ---------
    for b in bars[fill_i + 1:]:
        if side == "buy":
            stop_hit = b.low <= stop_price
            tp_hit = b.high >= tp_price
            if stop_hit:
                gapped = b.open <= stop_price
                exit_px = b.open if gapped else stop_price
                return _exit(entry_date, side, entry_limit, tp_price, stop_price,
                             shares, ExitReason.STOP, exit_px, b, gapped)
            if tp_hit:
                return _exit(entry_date, side, entry_limit, tp_price, stop_price,
                             shares, _tp_reason(entry_date, b), tp_price, b, False)
        else:  # short
            stop_hit = b.high >= stop_price
            tp_hit = b.low <= tp_price
            if stop_hit:
                gapped = b.open >= stop_price
                exit_px = b.open if gapped else stop_price
                return _exit(entry_date, side, entry_limit, tp_price, stop_price,
                             shares, ExitReason.STOP, exit_px, b, gapped)
            if tp_hit:
                return _exit(entry_date, side, entry_limit, tp_price, stop_price,
                             shares, _tp_reason(entry_date, b), tp_price, b, False)

    # --- 3. Never resolved -> still open, mark at last close ------------------
    last = bars[-1]
    pnl = _pnl(side, entry_limit, last.close, shares)
    return Trade(
        entry_date=entry_date, side=side, entry_limit=entry_limit,
        filled=True, intraday_tp=False, exit_reason=ExitReason.OPEN,
        tp_price=tp_price, stop_price=stop_price,
        exit_price=last.close, exit_date=last.d, shares=shares,
        pnl_usd=pnl, days_held=_days(entry_date, last.d), still_open=True,
    )


def _tp_reason(entry_date: date, bar) -> ExitReason:
    return ExitReason.INTRADAY_TP if bar.d == entry_date else ExitReason.OVERNIGHT_TP


def _pnl(side: str, entry: float, exit_px: float, shares: float) -> float:
    return (exit_px - entry) * shares if side == "buy" else (entry - exit_px) * shares


def _days(entry_date: date, exit_date: date) -> int:
    return max((exit_date - entry_date).days, 0)


def _exit(entry_date, side, entry_limit, tp_price, stop_price, shares,
          reason, exit_px, bar, gapped) -> Trade:
    return Trade(
        entry_date=entry_date, side=side, entry_limit=entry_limit,
        filled=True, intraday_tp=(reason == ExitReason.INTRADAY_TP),
        exit_reason=reason, tp_price=tp_price, stop_price=stop_price,
        exit_price=exit_px, exit_date=bar.d, shares=shares,
        pnl_usd=_pnl(side, entry_limit, exit_px, shares),
        days_held=_days(entry_date, bar.d), gapped=gapped,
    )
