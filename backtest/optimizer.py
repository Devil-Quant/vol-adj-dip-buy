"""Grid-search TP/SL per side on the intraday-realistic engine, with a
reward<=Nx risk cap. Each combo runs ONCE over full history; trades are tagged
by entry-date so OOS / walk-forward windows slice without re-running.

Objective = total REALIZED P&L (closed trades). Still-open trades are tracked
separately (a recent open is fine; an old one is a red flag) and never counted
in the optimization total."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from config.settings import StrategyParams
from models.trade import ExitReason
from strategies.dip_buy import simulate_buy
from strategies.pop_short import simulate_short
from backtest.engine import intraday_trades


@dataclass
class TradeRec:
    sym: str
    entry_date: date
    pnl: float
    win: bool
    still_open: bool


@dataclass
class WindowStats:
    limit_mult: float
    stop_mult: float
    total_pnl: float        # realized (closed) only
    n_trades: int           # closed
    win_rate: float
    worst: float
    expectancy: float       # total_pnl / n_trades
    open_count: int


def rr_ok(sigma_mult: float, limit_mult: float, stop_mult: float, max_rr: float) -> bool:
    """reward/risk = (sigma_mult + limit_mult) / stop_mult <= max_rr."""
    return (sigma_mult + limit_mult) <= max_rr * stop_mult + 1e-9


def combo_trades(symbols_data: dict, side: str, sigma_mult: float,
                 limit_mult: float, stop_mult: float, order_size: float) -> list[TradeRec]:
    recs: list[TradeRec] = []
    for sym, sd in symbols_data.items():
        trades = intraday_trades(
            sd["daily"], sd["intraday"], side, sigma_mult, limit_mult, stop_mult,
            order_size, sigma_by_day=sd["sigma_by_day"], day_start=sd["day_start"],
        )
        for t in trades:
            if t.filled and t.pnl_usd is not None:
                recs.append(TradeRec(sym, t.entry_date, t.pnl_usd, t.pnl_usd > 0, t.still_open))
    return recs


def run_grid(symbols_data: dict, side: str, limit_grid, stop_grid,
             sigma_mult: float, order_size: float, max_rr: float) -> dict:
    """{(limit_mult, stop_mult): [TradeRec, ...]} for RR-passing combos."""
    out: dict = {}
    for lm in limit_grid:
        for sm in stop_grid:
            if not rr_ok(sigma_mult, lm, sm, max_rr):
                continue
            out[(lm, sm)] = combo_trades(symbols_data, side, sigma_mult, lm, sm, order_size)
    return out


def combo_trades_daily(symbols_data: dict, side: str, sigma_mult: float,
                       limit_mult: float, stop_mult: float, order_size: float) -> list[TradeRec]:
    """Excel-FAITHFUL daily engine: whole-window sigma, exact-stop fills,
    same-day-both-in-range = win, and positions unresolved within the 20-day
    window are DROPPED (marked still_open so they contribute $0, mirroring the
    spreadsheet's dead AG column)."""
    params = StrategyParams(
        side=side, sigma_mult=sigma_mult, limit_mult=limit_mult, stop_mult=stop_mult,
        lookback_days=100, holding_window=20, holding_max=24, order_size_usd=order_size,
    )
    sim = simulate_buy if side == "buy" else simulate_short
    recs: list[TradeRec] = []
    for sym, sd in symbols_data.items():
        for t in sim(sd["daily"], params):
            if t.filled and t.pnl_usd is not None:
                dropped = t.exit_reason == ExitReason.DAY_MAX  # Excel drops these
                recs.append(TradeRec(sym, t.entry_date, t.pnl_usd, t.pnl_usd > 0, dropped))
    return recs


def run_grid_daily(symbols_data: dict, side: str, limit_grid, stop_grid,
                   sigma_mult: float, order_size: float, max_rr: float) -> dict:
    """Same as run_grid but using the Excel-faithful daily engine."""
    out: dict = {}
    for lm in limit_grid:
        for sm in stop_grid:
            if not rr_ok(sigma_mult, lm, sm, max_rr):
                continue
            out[(lm, sm)] = combo_trades_daily(symbols_data, side, sigma_mult, lm, sm, order_size)
    return out


def window_stats(limit_mult: float, stop_mult: float, recs: list[TradeRec],
                 start: date | None = None, end: date | None = None) -> WindowStats:
    sel = [r for r in recs
           if (start is None or r.entry_date >= start)
           and (end is None or r.entry_date <= end)]
    closed = [r for r in sel if not r.still_open]
    total = sum(r.pnl for r in closed)
    n = len(closed)
    wins = sum(1 for r in closed if r.win)
    worst = min((r.pnl for r in closed), default=0.0)
    opens = sum(1 for r in sel if r.still_open)
    return WindowStats(
        limit_mult=limit_mult, stop_mult=stop_mult, total_pnl=total, n_trades=n,
        win_rate=(wins / n if n else 0.0), worst=worst,
        expectancy=(total / n if n else 0.0), open_count=opens,
    )


def best_combo(grid: dict, start: date | None = None, end: date | None = None):
    """Rank RR-passing combos by total realized P&L in [start, end]; return
    (best WindowStats, full ranked list)."""
    ranked = [window_stats(lm, sm, recs, start, end) for (lm, sm), recs in grid.items()]
    ranked = [w for w in ranked if w.n_trades > 0]
    ranked.sort(key=lambda w: w.total_pnl, reverse=True)
    return (ranked[0] if ranked else None), ranked


def closed_pnls(recs: list[TradeRec], start: date | None = None,
                end: date | None = None) -> list[float]:
    return [r.pnl for r in recs
            if not r.still_open
            and (start is None or r.entry_date >= start)
            and (end is None or r.entry_date <= end)]
