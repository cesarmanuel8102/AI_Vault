import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Dict

from .copier import OrderCopier
from .router import OrderRouter
from .rules import check_firm_rules
from .types import AccountState, FirmProfile, StrategySignal


class ExecutionEngine:
    def __init__(
        self,
        profiles: Dict[str, FirmProfile],
        router: OrderRouter,
        copier: OrderCopier,
        audit_path: Path,
    ):
        self.profiles = profiles
        self.router = router
        self.copier = copier
        self.audit_path = audit_path
        self.audit_path.parent.mkdir(parents=True, exist_ok=True)

    def _audit(self, payload: Dict) -> None:
        payload["ts_utc"] = datetime.utcnow().isoformat(timespec="seconds") + "Z"
        with self.audit_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(payload, default=str) + "\n")

    def execute_one(
        self,
        account_id: str,
        signal: StrategySignal,
        account_state: AccountState,
        now_et: datetime,
    ) -> Dict:
        profile = self.profiles[account_id]
        decision = check_firm_rules(signal, account_state, profile, now_et)
        result = self.router.route(account_id, decision, signal)
        self._audit(
            {
                "mode": "single",
                "account_id": account_id,
                "decision": asdict(decision),
                "signal": asdict(signal),
                "result": result,
            }
        )
        return result

    def execute_with_copy(
        self,
        leader_account_id: str,
        leader_signal: StrategySignal,
        states: Dict[str, AccountState],
        now_et: datetime,
    ) -> Dict[str, Dict]:
        out: Dict[str, Dict] = {}
        out[leader_account_id] = self.execute_one(
            leader_account_id, leader_signal, states[leader_account_id], now_et
        )

        if not out[leader_account_id].get("ok"):
            return out

        copied = self.copier.fanout(leader_signal)
        for follower_id, s in copied.items():
            if follower_id not in states or follower_id not in self.profiles:
                self._audit(
                    {
                        "mode": "copy_skip",
                        "follower_id": follower_id,
                        "reason": "missing_state_or_profile",
                    }
                )
                continue
            out[follower_id] = self.execute_one(follower_id, s, states[follower_id], now_et)
        return out
