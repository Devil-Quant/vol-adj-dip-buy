"""Strategy parameter defaults (mirror the Excel `Buy`/`Short` tabs) plus
IBKR connection settings for the data client."""
import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

# IBKR paper Gateway defaults: 127.0.0.1:4002. (TWS paper 7497, live Gateway
# 4001, live TWS 7496.) Override via .env.
IBKR_HOST = os.getenv("IBKR_HOST", "127.0.0.1")
IBKR_PORT = int(os.getenv("IBKR_PORT", "4002"))
IBKR_CLIENT_ID = int(os.getenv("IBKR_CLIENT_ID", "37"))


@dataclass(frozen=True)
class StrategyParams:
    side: str
    sigma_mult: float
    limit_mult: float
    stop_mult: float
    lookback_days: int
    holding_window: int
    holding_max: int
    order_size_usd: float

    def __post_init__(self) -> None:
        if self.side not in ("buy", "short"):
            raise ValueError(f"side must be 'buy' or 'short', got {self.side!r}")
        if self.lookback_days < 20:
            raise ValueError("lookback_days < 20 leaves too few samples for stdev")
        if self.holding_max < self.holding_window:
            raise ValueError("holding_max must be >= holding_window")


# Optimization grid (TP and SL multipliers, in sigma units). Entry sigma_mult
# stays fixed at 1.0; only TP & SL are searched.
TP_GRID = (0.5, 0.75, 1.0, 1.5, 2.0, 2.5)
SL_GRID = (0.5, 1.0, 1.5, 2.0, 2.5, 3.0)
MAX_RR = 3.0            # reward <= 3x risk: (sigma_mult + limit_mult) <= 3 * stop_mult
SIGMA_LOOKBACK = 100    # trailing daily bars for per-entry sigma (walk-forward safe)

# Markov 3-state regime gate (forecast/markov.py). State at day k uses the
# trailing-MARKOV_LOOKBACK return: r >= BULL -> bull, r <= BEAR -> bear, else
# sideways. The gate's allow-decision for day X uses data <= day X-1 only.
MARKOV_LOOKBACK = 20
MARKOV_BULL_THRESHOLD = 0.05
MARKOV_BEAR_THRESHOLD = -0.05
MARKOV_GATE_THETA = 0.0   # gate fires when (P_bull - P_bear) > theta


DEFAULT_BUY = StrategyParams(
    side="buy",
    sigma_mult=1.0,
    limit_mult=0.5,
    stop_mult=3.0,
    lookback_days=100,
    holding_window=20,
    holding_max=24,
    order_size_usd=100_000.0,
)

DEFAULT_SHORT = StrategyParams(
    side="short",
    sigma_mult=1.0,
    limit_mult=0.75,
    stop_mult=3.0,
    lookback_days=100,
    holding_window=20,
    holding_max=24,
    order_size_usd=100_000.0,
)
