import json
from datetime import datetime
from pathlib import Path

from src.copier import FollowerConfig, OrderCopier
from src.engine import ExecutionEngine
from src.router import OrderRouter, PaperAdapter
from src.types import AccountState, FirmProfile, StrategySignal


def load_profiles(path: Path):
    raw = json.loads(path.read_text(encoding="utf-8"))
    profiles = {}
    for i, p in enumerate(raw.get("profiles", []), start=1):
        account_id = f"A{i:03d}"
        profiles[account_id] = FirmProfile(
            name=p["name"],
            provider=p["provider"],
            automation_allowed=bool(p["automation_allowed"]),
            max_contracts_per_order=int(p["max_contracts_per_order"]),
            max_contracts_total=int(p["max_contracts_total"]),
            daily_loss_limit_pct=float(p["daily_loss_limit_pct"]),
            trailing_drawdown_limit_pct=float(p["trailing_drawdown_limit_pct"]),
            allow_overnight=bool(p["allow_overnight"]),
            session_start_et=p["session_start_et"],
            session_end_et=p["session_end_et"],
            allow_hedging=bool(p["allow_hedging"]),
        )
    return profiles


def build_states(account_ids):
    states = {}
    for aid in account_ids:
        states[aid] = AccountState(
            account_id=aid,
            equity=50000.0,
            day_start_equity=50000.0,
            peak_equity=50000.0,
            open_contracts=0,
            open_positions=0,
            day_pnl_pct=0.0,
            trailing_dd_pct=0.0,
        )
    return states


def main():
    base = Path(__file__).resolve().parent
    profiles = load_profiles(base / "config" / "firm_profiles.sample.json")
    states = build_states(list(profiles.keys()))

    router = OrderRouter(adapters={"TOPSTEPX": PaperAdapter(), "TRADOVATE": PaperAdapter()})
    copier = OrderCopier(
        followers=[
            FollowerConfig(account_id="A002", qty_multiplier=1.0, enabled=False),
            FollowerConfig(account_id="A003", qty_multiplier=0.5, enabled=False),
        ]
    )
    engine = ExecutionEngine(
        profiles=profiles,
        router=router,
        copier=copier,
        audit_path=base / "artifacts" / "audit.jsonl",
    )

    signal = StrategySignal(
        strategy_id="PF100_R1150_V1030",
        symbol="MNQ",
        side="BUY",
        qty=2,
        stop_price=17990.0,
        target_price=18180.0,
        created_at=datetime.now(),
        note="manual validation batch",
    )

    now_et = datetime.now().replace(hour=10, minute=0, second=0, microsecond=0)
    out = engine.execute_with_copy("A001", signal, states, now_et)
    print(json.dumps(out, indent=2, default=str))
    print(f"audit={base / 'artifacts' / 'audit.jsonl'}")


if __name__ == "__main__":
    main()
