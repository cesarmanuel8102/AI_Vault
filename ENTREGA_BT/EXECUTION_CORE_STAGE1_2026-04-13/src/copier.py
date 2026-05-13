from dataclasses import dataclass
from typing import Dict, List

from .types import StrategySignal


@dataclass
class FollowerConfig:
    account_id: str
    qty_multiplier: float
    enabled: bool = True


class OrderCopier:
    def __init__(self, followers: List[FollowerConfig]):
        self.followers = followers

    def fanout(self, leader_signal: StrategySignal) -> Dict[str, StrategySignal]:
        output: Dict[str, StrategySignal] = {}
        for f in self.followers:
            if not f.enabled:
                continue
            q = max(1, int(round(leader_signal.qty * f.qty_multiplier)))
            output[f.account_id] = StrategySignal(
                strategy_id=leader_signal.strategy_id,
                symbol=leader_signal.symbol,
                side=leader_signal.side,
                qty=q,
                stop_price=leader_signal.stop_price,
                target_price=leader_signal.target_price,
                created_at=leader_signal.created_at,
                note=f"copied_from_leader x{f.qty_multiplier}",
            )
        return output
