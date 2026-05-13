import json
import os
import sys
from pathlib import Path
from datetime import datetime, timezone
import io
import contextlib


def utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _derive_repo_root(contract_path: str) -> str:
    """
    Best-effort: contracts live under <repo_root>\\brainlab\\contracts\\*.json
    If we can find a parent named 'brainlab', repo_root = parent.parent.
    Else fallback to the contract's parent directory.
    """
    try:
        p = Path(contract_path).resolve()
        for parent in p.parents:
            if parent.name.lower() == "brainlab":
                return str(parent.parent)
        return str(p.parent)
    except Exception:
        return ""


def _get_contract_from_argv_env(argv) -> str:
    # argv supports:
    #   --contract=PATH
    #   --contract PATH
    #   positional PATH
    for i, a in enumerate(argv):
        if a.startswith("--contract="):
            return a.split("=", 1)[1].strip()
        if a == "--contract" and i + 1 < len(argv):
            return (argv[i + 1] or "").strip()

    # positional
    if argv and not argv[0].startswith("--"):
        return (argv[0] or "").strip()

    # explicit env fallbacks (known/common)
    for k in (
        "CONTRACT_PATH", "SMOKE_CONTRACT", "SMOKE_CONTRACT_PATH",
        "CONTRACT", "contract", "contract_path",
        "POST_SMOKE", "POST_SMOKE_CONTRACT", "POST_SMOKE_CONTRACT_PATH",
        "POST_SMOKE_PATH", "post_smoke", "post_smoke_path",
    ):
        v = os.environ.get(k)
        if v and v.strip():
            return v.strip()

    # last resort: scan env for anything that looks like a contract json path
    # Prefer keys containing CONTRACT/SMOKE; prefer existing paths; prefer *.json
    candidates = []
    for k, v in os.environ.items():
        if not v or not isinstance(v, str):
            continue
        vv = v.strip()
        if not vv:
            continue
        lk = k.lower()
        if ("contract" not in lk) and ("smoke" not in lk):
            continue
        # quick plausibility
        if (".json" in vv.lower()) or (":\\" in vv) or ("/" in vv):
            candidates.append((k, vv))

    def score(item):
        k, vv = item
        lk = k.lower()
        s = 0
        if "contract" in lk: s += 5
        if "smoke" in lk: s += 3
        if "post_smoke" in lk: s += 4
        if vv.lower().endswith(".json"): s += 5
        try:
            if Path(vv).exists(): s += 10
        except Exception:
            pass
        return s

    candidates.sort(key=score, reverse=True)
    for k, vv in candidates:
        try:
            if Path(vv).exists() or vv.lower().endswith(".json"):
                return vv
        except Exception:
            continue

    return ""
def _get_profile_from_argv_env(argv) -> str:
    # --profile=quick|full|violations
    for a in argv:
        if a.startswith("--profile="):
            return a.split("=", 1)[1].strip().lower()
    # env fallback
    v = os.environ.get("SMOKE_PROFILE") or os.environ.get("smoke_profile")
    if v:
        return v.strip().lower()
    return "quick"
def main(argv=None) -> int:
    argv = list(argv) if argv is not None else sys.argv[1:]
    contract = _get_contract_from_argv_env(argv)

    if not contract:
        out = {"ok": False, "error": "MISSING_CONTRACT_PATH"}
        sys.stdout.write(json.dumps(out, ensure_ascii=False, indent=2) + "\n")
        return 1

    # Import RiskEngine with stdout suppressed to avoid extra prints corrupting JSON output
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            from smoke_risk_engine import RiskEngine
    except Exception as e:
        out = {"ok": False, "error": "IMPORT_FAILED", "detail": repr(e)}
        sys.stdout.write(json.dumps(out, ensure_ascii=False, indent=2) + "\n")
        return 1

    try:
        re = RiskEngine.from_contract_path(contract)
    except Exception as e:
        out = {"ok": False, "error": "LOAD_CONTRACT_FAILED", "contract_path": contract, "detail": repr(e)}
        sys.stdout.write(json.dumps(out, ensure_ascii=False, indent=2) + "\n")
        return 1
    profile = _get_profile_from_argv_env(argv)
    if profile not in ("quick", "full", "violations"):
        profile = "quick"

    # Profiles:
    # - quick: only a safe "ok" snapshot
    # - full: ok + violation cases (stress)
    # - violations: only the violation cases
    tests_ok = [
        {"name": "ok", "snapshot": {"nlv": 1000.0, "daily_pnl": -5.0, "weekly_drawdown": 0.01, "total_exposure": 0.35}},
    ]
    tests_viol = [
        {"name": "daily_loss_violation", "snapshot": {"nlv": 1000.0, "daily_pnl": -25.0, "weekly_drawdown": 0.01, "total_exposure": 0.35}},
        {"name": "weekly_dd_violation", "snapshot": {"nlv": 1000.0, "daily_pnl": 0.0, "weekly_drawdown": 0.10, "total_exposure": 0.35}},
        {"name": "exposure_violation", "snapshot": {"nlv": 1000.0, "daily_pnl": 0.0, "weekly_drawdown": 0.01, "total_exposure": 0.95}},
    ]

    if profile == "quick":
        tests = tests_ok
    elif profile == "violations":
        tests = tests_viol
    else:
        tests = tests_ok + tests_viol
    results = [{"name": t["name"], "assess": re.assess(t["snapshot"])} for t in tests]

    has_halt = False
    halt_reasons = []
    for r in results:
        a = r.get("assess") or {}
        if a.get("verdict") == "halt":
            has_halt = True
            halt_reasons.append({
                "name": r.get("name"),
                "reason": a.get("reason"),
                "violations": a.get("violations") or []
            })

    limits = {}
    try:
        limits = getattr(re, "limits").__dict__ if getattr(re, "limits", None) is not None else {}
    except Exception:
        limits = {}

    out = {
        "profile": profile,
        "ts": utc_iso(),
        "contract_path": contract,
        "repo_root": _derive_repo_root(contract),
        "limits": limits,
        "results": results,
        "has_halt": bool(has_halt),
        "halt_reasons": halt_reasons,
        # ok means "policy passed"
        "ok": (not has_halt),
    }

    sys.stdout.write(json.dumps(out, ensure_ascii=False, indent=2) + "\n")
    return 2 if has_halt else 0


if __name__ == "__main__":
    raise SystemExit(main())


