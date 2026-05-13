from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class StrategySignal:
    strategy_id: str
    symbol: str
    side: str  # BUY or SELL
    qty: int
    stop_price: float
    target_price: float
    created_at: datetime
    note: str = ""


@dataclass
class AccountState:
    account_id: str
    equity: float
    day_start_equity: float
    peak_equity: float
    open_contracts: int
    open_positions: int
    day_pnl_pct: float
    trailing_dd_pct: float


@dataclass
class FirmProfile:
    name: str
    provider: str
    automation_allowed: bool
    max_contracts_per_order: int
    max_contracts_total: int
    daily_loss_limit_pct: float
    trailing_drawdown_limit_pct: float
    allow_overnight: bool
    session_start_et: str
    session_end_et: str
    allow_hedging: bool


@dataclass
class Decision:
    accepted: bool
    reason: str
    route_provider: Optional[str] = None
