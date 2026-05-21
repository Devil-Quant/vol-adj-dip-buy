"""Path coverage for the 5-min intraday resolver. Synthetic bars let us
control the exact intraday sequence. Buy levels used throughout:
entry=99, tp=100.5, stop=96 (shares=1000)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta

from models.trade import ExitReason
from backtest.intraday_resolver import resolve_trade, resolve_oco_fade


@dataclass
class IBar:
    ts: datetime
    open: float
    high: float
    low: float
    close: float
    is_rth: bool

    @property
    def d(self) -> date:
        return self.ts.date()


D0 = date(2026, 3, 2)  # Monday
ENTRY, TP, STOP, SH = 99.0, 100.5, 96.0, 1000.0


def rth(d, hh, mm, o, h, l, c):
    return IBar(datetime(d.year, d.month, d.day, hh, mm), o, h, l, c, True)


def ext(d, hh, mm, o, h, l, c):
    return IBar(datetime(d.year, d.month, d.day, hh, mm), o, h, l, c, False)


def flat_day(d):
    """A full session that touches neither stop nor tp (stays 98..99.5)."""
    return [rth(d, 9, 30 + i, 99, 99.5, 98, 99) for i in range(0, 20, 5)]


def buy(bars):
    return resolve_trade(entry_date=D0, side="buy", entry_limit=ENTRY,
                         tp_price=TP, stop_price=STOP, shares=SH, bars=bars)


def test_no_fill():
    bars = [rth(D0, 9, 30, 100, 100.2, 99.5, 100),   # low 99.5 > entry 99
            rth(D0, 9, 35, 100, 100.1, 99.6, 99.9)]
    t = buy(bars)
    assert t.filled is False and t.exit_reason == ExitReason.NONE


def test_intraday_tp():
    bars = [rth(D0, 9, 30, 100, 100.2, 98.5, 99.5),  # fill (low 98.5<=99), high<tp
            rth(D0, 9, 35, 99.5, 101.0, 99.0, 100.8)]  # later bar hits tp
    t = buy(bars)
    assert t.filled and t.exit_reason == ExitReason.INTRADAY_TP
    assert t.days_held == 0
    assert abs(t.exit_price - TP) < 1e-9
    assert abs(t.pnl_usd - (TP - ENTRY) * SH) < 1e-6


def test_intraday_stop():
    bars = [rth(D0, 9, 30, 100, 100.2, 98.5, 99.5),   # fill
            rth(D0, 9, 35, 99.0, 99.2, 95.5, 96.0)]    # low 95.5<=stop 96
    t = buy(bars)
    assert t.exit_reason == ExitReason.STOP and t.gapped is False
    assert abs(t.exit_price - STOP) < 1e-9
    assert t.pnl_usd < 0


def test_overnight_tp():
    d1 = D0 + timedelta(days=1)
    bars = [rth(D0, 9, 30, 100, 100.2, 98.5, 99.5)] + flat_day(D0)[1:]
    bars += [rth(d1, 9, 30, 100, 101.0, 99.5, 100.8)]  # tp next day
    t = buy(bars)
    assert t.exit_reason == ExitReason.OVERNIGHT_TP
    assert t.days_held == 1


def test_overnight_stop():
    d1 = D0 + timedelta(days=1)
    bars = [rth(D0, 9, 30, 100, 100.2, 98.5, 99.5)] + flat_day(D0)[1:]
    bars += [rth(d1, 9, 30, 99.0, 99.5, 95.0, 95.5)]   # stop next day, opens above stop
    t = buy(bars)
    assert t.exit_reason == ExitReason.STOP
    assert abs(t.exit_price - STOP) < 1e-9   # traded down into stop, not gapped
    assert t.gapped is False


def test_gap_through_stop():
    """Next session's first bar OPENS below the stop -> fill at the gap open."""
    d1 = D0 + timedelta(days=1)
    bars = [rth(D0, 9, 30, 100, 100.2, 98.5, 99.5)] + flat_day(D0)[1:]
    bars += [ext(d1, 4, 0, 94.0, 94.5, 93.0, 94.2)]    # gap-down pre-market open 94 < stop 96
    t = buy(bars)
    assert t.exit_reason == ExitReason.STOP and t.gapped is True
    assert abs(t.exit_price - 94.0) < 1e-9              # filled at the open, worse than stop
    assert abs(t.pnl_usd - (94.0 - ENTRY) * SH) < 1e-6


def test_same_bar_tie_goes_to_stop():
    bars = [rth(D0, 9, 30, 100, 100.2, 98.5, 99.5),    # fill
            rth(D0, 9, 35, 99.0, 101.0, 95.0, 97.0)]   # both tp(101>=100.5) and stop(95<=96)
    t = buy(bars)
    assert t.exit_reason == ExitReason.STOP            # adverse wins the tie
    assert abs(t.exit_price - STOP) < 1e-9             # opened 99 > stop, so fill at stop


def test_hold_and_resolve_after_20_days():
    bars = [rth(D0, 9, 30, 100, 100.2, 98.5, 99.5)] + flat_day(D0)[1:]
    for k in range(1, 25):                              # 24 flat days, no resolution
        bars += flat_day(D0 + timedelta(days=k))
    late = D0 + timedelta(days=25)
    bars += [rth(late, 9, 30, 100, 101.0, 99.5, 100.8)]  # tp on day 25
    t = buy(bars)
    assert t.exit_reason == ExitReason.OVERNIGHT_TP
    assert t.days_held >= 21                            # held well past 20 days


def test_never_resolves_is_open():
    bars = [rth(D0, 9, 30, 100, 100.2, 98.5, 99.5)] + flat_day(D0)[1:]
    for k in range(1, 6):
        bars += flat_day(D0 + timedelta(days=k))
    t = buy(bars)
    assert t.filled and t.exit_reason == ExitReason.OPEN
    assert t.still_open is True
    assert t.exit_price == bars[-1].close              # marked at last close


def test_tp_touched_before_entry_is_not_a_win():
    """An early bar reaches the TP level while we are NOT yet filled; the entry
    fills later. The pre-fill TP touch must be ignored (no same-day win)."""
    bars = [rth(D0, 9, 30, 101, 101.5, 100.6, 101.0),  # high>=tp but low>entry -> NO fill
            rth(D0, 9, 35, 100, 100.1, 98.8, 99.2),    # fill here (low 98.8<=99)
            rth(D0, 9, 40, 99.2, 99.5, 99.0, 99.3)]    # nothing after
    t = buy(bars)
    assert t.filled is True
    assert t.exit_reason != ExitReason.INTRADAY_TP     # the early TP was not credited
    assert t.exit_reason == ExitReason.OPEN


# --- Short side (mirror): entry=101, tp(cover)=100.25, stop=104 --------------
SENTRY, STP, SSTOP = 101.0, 100.25, 104.0


def short(bars):
    return resolve_trade(entry_date=D0, side="short", entry_limit=SENTRY,
                         tp_price=STP, stop_price=SSTOP, shares=SH, bars=bars)


def test_short_no_fill():
    bars = [rth(D0, 9, 30, 100.5, 100.9, 100.2, 100.6)]  # high 100.9 < entry 101
    t = short(bars)
    assert t.filled is False and t.exit_reason == ExitReason.NONE


def test_short_intraday_cover():
    bars = [rth(D0, 9, 30, 100.5, 101.5, 100.4, 101.0),  # fill (high>=101), low>tp
            rth(D0, 9, 35, 101.0, 101.2, 100.0, 100.3)]  # low 100.0<=tp 100.25 -> cover
    t = short(bars)
    assert t.exit_reason == ExitReason.INTRADAY_TP and t.days_held == 0
    assert abs(t.exit_price - STP) < 1e-9
    assert abs(t.pnl_usd - (SENTRY - STP) * SH) < 1e-6   # short profit


def test_short_overnight_stop():
    d1 = D0 + timedelta(days=1)
    bars = [rth(D0, 9, 30, 100.5, 101.5, 100.4, 101.0),
            rth(D0, 9, 35, 101.0, 101.2, 100.5, 101.0)]  # no cover/stop day 1
    bars += [rth(d1, 9, 30, 102.0, 104.5, 101.5, 104.0)]  # high>=stop, opens below -> fill at stop
    t = short(bars)
    assert t.exit_reason == ExitReason.STOP and t.gapped is False
    assert abs(t.exit_price - SSTOP) < 1e-9
    assert t.pnl_usd < 0


def test_short_gap_through_stop():
    """Gap UP through the short's stop -> fill at the (worse, higher) open."""
    d1 = D0 + timedelta(days=1)
    bars = [rth(D0, 9, 30, 100.5, 101.5, 100.4, 101.0),
            rth(D0, 9, 35, 101.0, 101.2, 100.5, 101.0)]
    bars += [ext(d1, 4, 0, 105.0, 105.5, 104.5, 105.0)]  # opens 105 >= stop 104 -> gap
    t = short(bars)
    assert t.exit_reason == ExitReason.STOP and t.gapped is True
    assert abs(t.exit_price - 105.0) < 1e-9
    assert abs(t.pnl_usd - (SENTRY - 105.0) * SH) < 1e-6


def test_short_same_bar_tie_goes_to_stop():
    bars = [rth(D0, 9, 30, 100.5, 101.5, 100.4, 101.0),  # fill
            rth(D0, 9, 35, 102.0, 104.5, 100.0, 101.0)]  # both stop(104.5>=104) and tp(100<=100.25)
    t = short(bars)
    assert t.exit_reason == ExitReason.STOP             # adverse wins
    assert abs(t.exit_price - SSTOP) < 1e-9


# --- OCO bidirectional fade: prev_close=100, sigma=1, sigma_mult=1 -----------
# long entry 99, short entry 101; tp_mult=1 -> both tp at 100; stop_mult=0.5
def fade(bars):
    return resolve_oco_fade(entry_date=D0, prev_close=100.0, sigma=1.0, sigma_mult=1.0,
                            tp_mult=1.0, stop_mult=0.5, order_size=100_000.0,
                            bars=bars, start_idx=0)


def test_fade_long_first():
    bars = [rth(D0, 9, 30, 100, 100.2, 98.8, 99.5),    # low<=99 (long), high<101 -> LONG
            rth(D0, 9, 35, 99.5, 100.5, 99.0, 100.0)]  # high>=100 tp
    t = fade(bars)
    assert t.side == "buy" and t.filled
    assert t.exit_reason == ExitReason.INTRADAY_TP
    assert t.pnl_usd > 0


def test_fade_short_first():
    bars = [rth(D0, 9, 30, 100, 101.5, 100.0, 101.0),  # high>=101 (short), low>99 -> SHORT
            rth(D0, 9, 35, 101.0, 101.2, 99.5, 100.0)]  # low<=100 tp (cover)
    t = fade(bars)
    assert t.side == "short" and t.filled
    assert t.exit_reason == ExitReason.INTRADAY_TP
    assert t.pnl_usd > 0


def test_fade_ambiguous_same_bar_no_fill():
    bars = [rth(D0, 9, 30, 100, 101.5, 98.5, 100)]     # spans both 99 and 101 -> ambiguous
    t = fade(bars)
    assert t.filled is False and t.exit_reason == ExitReason.NONE


def test_fade_no_touch_no_fill():
    bars = [rth(D0, 9, 30, 100, 100.5, 99.5, 100)]     # never reaches 99 or 101
    t = fade(bars)
    assert t.filled is False
