"""Strategy parameter defaults — mirror the Excel `Buy` and `Short` tabs."""
from dataclasses import dataclass


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
