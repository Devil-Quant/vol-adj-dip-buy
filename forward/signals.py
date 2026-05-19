"""Forward-test: turn the last N bars into today's actionable order
parameters. The caller places the orders the next morning."""
from __future__ import annotations

from typing import Iterable

import pandas as pd

from config.settings import StrategyParams
from models.trade import Signal
from strategies.dip_buy import buy_signal
from strategies.pop_short import short_signal


def generate_signal(symbol: str, bars, params: StrategyParams) -> Signal:
    if params.side == "buy":
        return buy_signal(bars, params, symbol)
    if params.side == "short":
        return short_signal(bars, params, symbol)
    raise ValueError(f"unknown side {params.side!r}")


def signals_to_dataframe(signals: Iterable[Signal]) -> pd.DataFrame:
    rows = []
    for s in signals:
        rows.append({
            "symbol": s.symbol,
            "side": s.side,
            "asof_date": s.asof_date,
            "prev_close": round(s.prev_close, 4),
            "sigma": round(s.sigma, 4),
            "entry_limit": round(s.entry_limit, 4),
            "tp_price": round(s.tp_price, 4),
            "stop_price": round(s.stop_price, 4),
            "shares": round(s.shares, 2),
        })
    return pd.DataFrame(rows)
