import argparse
import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List

from src.copier import OrderCopier
from src.engine import ExecutionEngine
from src.router import OrderRouter, PaperAdapter
from src.types import AccountState, FirmProfile, StrategySignal


def load_profiles(path: Path) -> Dict[str, FirmProfile]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    profiles: Dict[str, FirmProfile] = {}
    for i, p in enumerate(raw.get("profiles", []), start=1):
        aid = f"A{i:03d}"
        profiles[aid] = FirmProfile(
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


def default_state(account_id: str) -> AccountState:
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


def patch_state(state: AccountState, patch: dict) -> None:
    for k, v in patch.items():
        if hasattr(state, k):
            setattr(state, k, v)


def parse_et(ts: str) -> datetime:
    # Expected local ET string: YYYY-MM-DDTHH:MM:SS
    return datetime.fromisoformat(ts)


def run_session(
    profile_path: Path,
    signals_path: Path,
    out_dir: Path,
) -> Path:
    profiles = load_profiles(profile_path)
    if not profiles:
        raise RuntimeError("No profiles found")

    account_id = sorted(profiles.keys())[0]
    state = default_state(account_id)

    engine = ExecutionEngine(
        profiles=profiles,
        router=OrderRouter(adapters={"TRADOVATE": PaperAdapter(), "TOPSTEPX": PaperAdapter()}),
        copier=OrderCopier(followers=[]),
        audit_path=out_dir / "audit.jsonl",
    )

    raw_signals: List[dict] = json.loads(signals_path.read_text(encoding="utf-8"))
    rows = []
    accepted = 0
    rejected = 0
    reasons: Dict[str, int] = {}

    for i, s in enumerate(raw_signals, start=1):
        patch_before = s.get("state_patch_before", {})
        if patch_before:
            patch_state(state, patch_before)

        now_et = parse_et(s["timestamp_et"])
        signal = StrategySignal(
            strategy_id=s.get("strategy_id", "PF100_FASTPASS_PAPER"),
            symbol=s.get("symbol", "MNQ"),
            side=s["side"],
            qty=int(s["qty"]),
            stop_price=float(s.get("stop_price", 0.0)),
            target_price=float(s.get("target_price", 0.0)),
            created_at=now_et,
            note=s.get("note", ""),
        )

        result = engine.execute_one(account_id, signal, state, now_et)
        ok = bool(result.get("ok", False))
        reason = result.get("reason", "accepted")
        reasons[reason] = reasons.get(reason, 0) + 1

        if ok:
            accepted += 1
            # Simplified exposure tracking for paper gate checks.
            state.open_contracts += signal.qty
            state.open_positions = 1 if state.open_contracts > 0 else 0
        else:
            rejected += 1

        patch_after = s.get("state_patch_after", {})
        if patch_after:
            patch_state(state, patch_after)

        rows.append(
            {
                "idx": i,
                "timestamp_et": s["timestamp_et"],
                "signal": asdict(signal),
                "result": result,
                "state_after": asdict(state),
            }
        )

    report = {
        "generated_at_utc": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "profile_path": str(profile_path),
        "signals_path": str(signals_path),
        "summary": {
            "accepted": accepted,
            "rejected": rejected,
            "total": len(raw_signals),
            "reasons": reasons,
        },
        "final_state": asdict(state),
        "events": rows,
    }

    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"paper_day_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    out.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="Run one paper validation day in pre-brain execution core")
    parser.add_argument(
        "--profile",
        default="config/firm_profiles.mffu_flex50.paper.json",
        help="Profile JSON path",
    )
    parser.add_argument(
        "--signals",
        default="config/paper_day_signals.sample.json",
        help="Signals JSON path",
    )
    parser.add_argument(
        "--outdir",
        default="artifacts",
        help="Output directory",
    )
    args = parser.parse_args()

    base = Path(__file__).resolve().parent
    report = run_session(
        profile_path=(base / args.profile).resolve(),
        signals_path=(base / args.signals).resolve(),
        out_dir=(base / args.outdir).resolve(),
    )
    payload = json.loads(report.read_text(encoding="utf-8"))
    print(json.dumps(payload["summary"], indent=2))
    print(f"report={report}")
    print(f"audit={(base / args.outdir / 'audit.jsonl').resolve()}")


if __name__ == "__main__":
    main()
