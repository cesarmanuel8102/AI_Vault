from dataclasses import asdict
from datetime import datetime
from typing import Dict

from .types import Decision, StrategySignal


class BaseAdapter:
    def send_order(self, account_id: str, signal: StrategySignal) -> Dict:
        raise NotImplementedError


class PaperAdapter(BaseAdapter):
    def send_order(self, account_id: str, signal: StrategySignal) -> Dict:
        return {
            "ok": True,
            "account_id": account_id,
            "provider_order_id": f"PAPER-{int(datetime.utcnow().timestamp())}",
            "echo": asdict(signal),
        }


class OrderRouter:
    def __init__(self, adapters: Dict[str, BaseAdapter]):
        self.adapters = adapters

    def route(self, account_id: str, decision: Decision, signal: StrategySignal) -> Dict:
        if not decision.accepted:
            return {"ok": False, "reason": decision.reason, "account_id": account_id}
        provider = decision.route_provider
        if provider not in self.adapters:
            return {"ok": False, "reason": f"missing_adapter:{provider}", "account_id": account_id}
        return self.adapters[provider].send_order(account_id, signal)
