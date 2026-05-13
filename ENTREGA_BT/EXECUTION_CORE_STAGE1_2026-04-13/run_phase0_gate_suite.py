import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple

from src.engine import ExecutionEngine
from src.copier import OrderCopier
from src.router import OrderRouter, PaperAdapter
from src.types import AccountState, FirmProfile, StrategySignal


def load_profiles(path: Path) -> Dict[str, FirmProfile]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    profiles: Dict[str, FirmProfile] = {}
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


def base_state(account_id: str) -> AccountState:
    return AccountState(
        account_id=account_id,
        equity=50000.0,
        day_start_equity=50000.0,
        peak_equity=50000.0,
        open_contracts=0,
        open_positions=0,
        day_pnl_pct=0.0,
        trailing_dd_pct=0.0,
    )


def base_signal() -> StrategySignal:
    return StrategySignal(
        strategy_id="PF100_FASTPASS_PAPER",
        symbol="MNQ",
        side="BUY",
        qty=1,
        stop_price=17990.0,
        target_price=18180.0,
        created_at=datetime.now(),
        note="phase0_gate_suite",
    )


def build_cases() -> List[Tuple[str, dict]]:
    return [
        (
            "accept_in_session",
            {
                "now": datetime.now().replace(hour=10, minute=0, second=0, microsecond=0),
                "state_patch": {},
                "signal_patch": {"qty": 1},
                "expect_ok": True,
            },
        ),
        (
            "reject_outside_session",
            {
                "now": datetime.now().replace(hour=8, minute=15, second=0, microsecond=0),
                "state_patch": {},
                "signal_patch": {"qty": 1},
                "expect_ok": False,
                "expect_reason": "outside_allowed_session",
            },
        ),
        (
            "reject_qty_over_order_limit",
            {
                "now": datetime.now().replace(hour=10, minute=0, second=0, microsecond=0),
                "state_patch": {},
                "signal_patch": {"qty": 99},
                "expect_ok": False,
                "expect_reason": "qty_over_order_limit",
            },
        ),
        (
            "reject_daily_loss_guard",
            {
                "now": datetime.now().replace(hour=10, minute=0, second=0, microsecond=0),
                "state_patch": {"day_pnl_pct": -0.01},
                "signal_patch": {"qty": 1},
                "expect_ok": False,
                "expect_reason": "daily_loss_limit_reached",
            },
        ),
        (
            "reject_trailing_guard",
            {
                "now": datetime.now().replace(hour=10, minute=0, second=0, microsecond=0),
                "state_patch": {"trailing_dd_pct": 0.05},
                "signal_patch": {"qty": 1},
                "expect_ok": False,
                "expect_reason": "trailing_drawdown_limit_reached",
            },
        ),
    ]


def main() -> None:
    base = Path(__file__).resolve().parent
    profile_path = base / "config" / "firm_profiles.mffu_flex50.paper.json"
    profiles = load_profiles(profile_path)
    account_id = sorted(profiles.keys())[0]

    engine = ExecutionEngine(
        profiles=profiles,
        router=OrderRouter(adapters={"TRADOVATE": PaperAdapter(), "TOPSTEPX": PaperAdapter()}),
        copier=OrderCopier(followers=[]),
        audit_path=base / "artifacts" / "audit.jsonl",
    )

    report = {
        "generated_at_utc": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "profile_path": str(profile_path),
        "profile": asdict(profiles[account_id]),
        "cases": [],
    }

    passed = 0
    cases = build_cases()

    for name, spec in cases:
        st = base_state(account_id)
        sig = base_signal()
        for k, v in spec.get("state_patch", {}).items():
            setattr(st, k, v)
        for k, v in spec.get("signal_patch", {}).items():
            setattr(sig, k, v)

        result = engine.execute_one(account_id, sig, st, spec["now"])
        ok = bool(result.get("ok", False))
        reason = result.get("reason", "")

        case_pass = ok == spec["expect_ok"] and (
            "expect_reason" not in spec or reason == spec["expect_reason"]
        )
        if case_pass:
            passed += 1

        report["cases"].append(
            {
                "name": name,
                "result": result,
                "expected_ok": spec["expect_ok"],
                "expected_reason": spec.get("expect_reason", ""),
                "pass": case_pass,
            }
        )

    report["summary"] = {"passed": passed, "total": len(cases)}

    out = base / "artifacts" / f"phase0_gate_suite_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    out.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")

    print(json.dumps(report["summary"], indent=2))
    print(f"report={out}")
    print(f"audit={base / 'artifacts' / 'audit.jsonl'}")


if __name__ == "__main__":
    main()
