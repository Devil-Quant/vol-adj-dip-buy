"""Intraday (extended-hours) bar fetcher via IBKR. No business logic.

IBKR caps intraday history per request, so we fetch in calendar-day chunks
stepping endDateTime backward, then dedupe + sort. Reuses the shared
connection from ibkr_client (its module import also installs the Py3.14
event-loop shim)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from time import sleep

import pandas as pd
from ib_insync import Stock

from clients.ibkr_client import _get_ib, CACHE_DIR, CACHE_TTL_SECONDS

RTH_START = time(9, 30)
RTH_END = time(16, 0)


@dataclass(frozen=True)
class IntradayBar:
    ts: datetime          # ET wall-clock, tz-aware as IBKR returns it
    open: float
    high: float
    low: float
    close: float
    is_rth: bool          # True if 09:30 <= time < 16:00 ET (regular session)

    @property
    def d(self) -> date:
        return self.ts.date()


def _is_rth(ts: datetime) -> bool:
    return RTH_START <= ts.time() < RTH_END


def _to_date(v) -> date:
    if isinstance(v, str):
        return date.fromisoformat(v)
    if isinstance(v, datetime):
        return v.date()
    return v


def _req_chunk(ib, contract, end_str, dur, bar_size, use_rth, attempts=4):
    """Request one historical chunk, retrying on empty/timeout (pacing under
    parallel load). Returns [] only after all attempts fail — so a transient
    timeout never silently truncates the series."""
    for k in range(attempts):
        try:
            bars = ib.reqHistoricalData(
                contract, endDateTime=end_str, durationStr=dur,
                barSizeSetting=bar_size, whatToShow="TRADES", useRTH=use_rth,
                formatDate=1, timeout=180,
            )
        except Exception:
            bars = None
        if bars:
            return bars
        sleep(3 * (k + 1))  # backoff: 3, 6, 9s
    return []


def fetch_intraday(
    symbol: str,
    start,
    end,
    *,
    bar_size: str = "5 mins",
    use_rth: bool = False,
    use_cache: bool = True,
    chunk_days: int = 60,
) -> list[IntradayBar]:
    """Fetch intraday bars for `symbol` covering the calendar span [start, end].

    `start`/`end` are date or 'YYYY-MM-DD'. `use_rth=False` includes pre/post
    market (04:00-20:00 ET). Returns chronological IntradayBar list.
    """
    symbol = symbol.strip().upper()
    if not symbol:
        raise ValueError("symbol must be non-empty")
    start_d, end_d = _to_date(start), _to_date(end)
    if end_d < start_d:
        raise ValueError(f"end {end_d} before start {start_d}")

    tag = bar_size.replace(" ", "")
    rth_tag = "rth" if use_rth else "ext"
    cache_file = CACHE_DIR / f"{symbol}_{tag}_{rth_tag}_{start_d}_{end_d}.parquet"
    if use_cache and cache_file.exists():
        is_now = end_d >= date.today()
        fresh = (not is_now) or (
            datetime.now().timestamp() - cache_file.stat().st_mtime < CACHE_TTL_SECONDS
        )
        if fresh:
            return _df_to_bars(pd.read_parquet(cache_file))

    ib = _get_ib()
    contract = Stock(symbol, "SMART", "USD")
    ib.qualifyContracts(contract)

    collected: dict[str, IntradayBar] = {}
    cursor = end_d
    guard = 0
    reached_start = False
    while cursor >= start_d and guard < 120:
        guard += 1
        end_str = f"{cursor.strftime('%Y%m%d')} 23:59:59"
        bars = _req_chunk(ib, contract, end_str, f"{chunk_days} D", bar_size, use_rth)
        if not bars:
            # Empty AFTER retries -> treat as genuine start of available history
            # (e.g. pre-IPO). A transient timeout would have been recovered by
            # the retries, so we don't silently truncate on a network hiccup.
            reached_start = True
            break
        for b in bars:
            ts = b.date if isinstance(b.date, datetime) else datetime.combine(b.date, time.min)
            collected[ts.isoformat()] = IntradayBar(
                ts=ts, open=float(b.open), high=float(b.high),
                low=float(b.low), close=float(b.close), is_rth=_is_rth(ts),
            )
        cursor = cursor - timedelta(days=chunk_days)
    if cursor < start_d:
        reached_start = True  # stepped past start_d = full coverage
    # guard exhaustion (guard>=120, cursor still >= start_d) leaves
    # reached_start False so the coverage guard below fires.

    out = sorted(
        (b for b in collected.values() if start_d <= b.ts.date() <= end_d),
        key=lambda b: b.ts,
    )
    if not out:
        raise RuntimeError(f"IBKR returned no intraday data for {symbol} {start_d}..{end_d}")

    # Guard against caching a TRUNCATED pull (e.g. repeated timeouts under load):
    # if coverage doesn't reach near start_d and we didn't cleanly hit end-of-data,
    # raise instead of writing a partial cache the optimizer would trust.
    earliest = out[0].ts.date()
    if not reached_start and earliest > start_d + timedelta(days=45):
        raise RuntimeError(
            f"{symbol}: incomplete intraday pull (only back to {earliest}, wanted {start_d}); "
            "not caching partial data")

    if use_cache:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        _bars_to_df(out).to_parquet(cache_file)
    return out


def _bars_to_df(bars: list[IntradayBar]) -> pd.DataFrame:
    return pd.DataFrame(
        [{"ts": b.ts, "Open": b.open, "High": b.high, "Low": b.low,
          "Close": b.close, "is_rth": b.is_rth} for b in bars]
    )


def _df_to_bars(df: pd.DataFrame) -> list[IntradayBar]:
    out: list[IntradayBar] = []
    for _, row in df.iterrows():
        ts = row["ts"]
        ts = ts.to_pydatetime() if hasattr(ts, "to_pydatetime") else ts
        out.append(IntradayBar(
            ts=ts, open=float(row["Open"]), high=float(row["High"]),
            low=float(row["Low"]), close=float(row["Close"]), is_rth=bool(row["is_rth"]),
        ))
    return out
