"""Resolve one day's signal against 5-min (extended-hours) intraday bars.

No look-ahead optimism: the entry only fills if an RTH bar actually trades to
the limit; TP/stop are scanned from the bar AFTER the fill (so a level touched
in the same 5-min bar as the fill is not credited); when one bar contains both
TP and stop, the adverse one (stop) is assumed first; a stop that gaps (the
bar opens beyond it, e.g. after the 20:00-04:00 dead window) fills at the gap
open, not the stop price. Positions are held to resolution — no time cap.

Bars must be chronological; `start_idx` identifies the first bar of
`entry_date` within the full list (no slicing — keeps the optimizer fast).
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
    start_idx: int = 0,
) -> Trade:
    """Resolve the trade against `bars`, scanning from `start_idx` (the first
    index of `entry_date`). Index-based (no slicing) so the optimizer can pass
    the full intraday list cheaply across thousands of (combo x entry) calls."""
    if side not in ("buy", "short"):
        raise ValueError(f"side must be buy/short, got {side!r}")

    no_fill = Trade(
        entry_date=entry_date, side=side, entry_limit=entry_limit,
        filled=False, intraday_tp=False, exit_reason=ExitReason.NONE,
        tp_price=tp_price, stop_price=stop_price,
    )

    n = len(bars)
    # --- 1. Entry fill: RTH bars on entry_date only --------------------------
    fill_i = None
    i = start_idx
    while i < n and bars[i].d == entry_date:
        b = bars[i]
        if b.is_rth:
            hit = (b.low <= entry_limit) if side == "buy" else (b.high >= entry_limit)
            if hit:
                fill_i = i
                break
        i += 1
    if fill_i is None:
        return no_fill

    return _resolve_after_fill(entry_date, side, entry_limit, tp_price,
                               stop_price, shares, bars, fill_i)


def resolve_oco_fade(
    *, entry_date: date, prev_close: float, sigma: float, sigma_mult: float,
    tp_mult: float, stop_mult: float, order_size: float,
    bars: Sequence, start_idx: int = 0,
) -> Trade:
    """Bidirectional OCO fade: place BOTH a long limit at C-sigma_mult*sigma and a
    short limit at C+sigma_mult*sigma at the open; whichever the price reaches
    FIRST (RTH) opens, the other cancels. Then resolve that side with tp_mult /
    stop_mult sigma offsets. A single bar that spans both levels is ambiguous
    (can't tell which came first) -> treated as no-fill for the day."""
    long_entry = prev_close - sigma_mult * sigma
    short_entry = prev_close + sigma_mult * sigma
    no_fill = Trade(entry_date=entry_date, side="buy", entry_limit=long_entry,
                    filled=False, intraday_tp=False, exit_reason=ExitReason.NONE)

    n = len(bars)
    fill_i, side = None, None
    i = start_idx
    while i < n and bars[i].d == entry_date:
        b = bars[i]
        if b.is_rth:
            long_hit = b.low <= long_entry
            short_hit = b.high >= short_entry
            if long_hit and short_hit:
                return no_fill  # ambiguous which extreme came first
            if long_hit:
                side, fill_i = "buy", i
                break
            if short_hit:
                side, fill_i = "short", i
                break
        i += 1
    if fill_i is None:
        return no_fill

    if side == "buy":
        entry = long_entry
        tp_price = entry + tp_mult * sigma
        stop_price = entry - stop_mult * sigma
    else:
        entry = short_entry
        tp_price = entry - tp_mult * sigma
        stop_price = entry + stop_mult * sigma
    return _resolve_after_fill(entry_date, side, entry, tp_price, stop_price,
                               order_size / entry, bars, fill_i)


def _resolve_after_fill(entry_date, side, entry_limit, tp_price, stop_price,
                        shares, bars, fill_i) -> Trade:
    """Walk forward from the fill bar for the first of TP / stop (RTH + ext);
    gap-aware stop; hold to resolution; OPEN at data end."""
    for j in range(fill_i + 1, len(bars)):
        b = bars[j]
        if side == "buy":
            if b.low <= stop_price:
                gapped = b.open <= stop_price
                return _exit(entry_date, side, entry_limit, tp_price, stop_price,
                             shares, ExitReason.STOP, b.open if gapped else stop_price, b, gapped)
            if b.high >= tp_price:
                return _exit(entry_date, side, entry_limit, tp_price, stop_price,
                             shares, _tp_reason(entry_date, b), tp_price, b, False)
        else:
            if b.high >= stop_price:
                gapped = b.open >= stop_price
                return _exit(entry_date, side, entry_limit, tp_price, stop_price,
                             shares, ExitReason.STOP, b.open if gapped else stop_price, b, gapped)
            if b.low <= tp_price:
                return _exit(entry_date, side, entry_limit, tp_price, stop_price,
                             shares, _tp_reason(entry_date, b), tp_price, b, False)

    last = bars[-1]
    return Trade(
        entry_date=entry_date, side=side, entry_limit=entry_limit,
        filled=True, intraday_tp=False, exit_reason=ExitReason.OPEN,
        tp_price=tp_price, stop_price=stop_price,
        exit_price=last.close, exit_date=last.d, shares=shares,
        pnl_usd=_pnl(side, entry_limit, last.close, shares),
        days_held=_days(entry_date, last.d), still_open=True,
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
