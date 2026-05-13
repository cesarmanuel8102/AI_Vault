# apply_gate.py (v1.1)
from __future__ import annotations

import json
import shutil
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from policies import SandboxPolicy
from sandbox_executor import SandboxExecutor
from sandbox_logger import SandboxLogger


SANDBOX_ROOT = Path(r"C:\AI_VAULT\tmp_agent").resolve()
LOG_PATH = SANDBOX_ROOT / "logs" / "dev.ndjson"
STATE_DIR = (SANDBOX_ROOT / "state").resolve()

REPO_ROOT = Path(r"C:\AI_VAULT\workspace\brainlab").resolve()
WORK_DIR = (SANDBOX_ROOT / "workspace").resolve()

DEFAULT_DEST_DIR = (REPO_ROOT / "brainlab" / "risk").resolve()  # destino recomendado
DENY_RUNTIME = Path(r"C:\AI_VAULT\00_identity").resolve()


def utc_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def read_json(p: Path, policy: SandboxPolicy) -> Any:
    policy.assert_can_read(p)
    return json.loads(p.read_text(encoding="utf-8"))


def ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def backup_path_for(dest: Path) -> Path:
    stamp = time.strftime("%Y%m%d_%H%M%S")
    return dest.with_suffix(dest.suffix + f".bak_{stamp}")


def py_compile_paths(paths: List[Path], exec: SandboxExecutor) -> Dict[str, Any]:
    cmd = ["python", "-m", "py_compile"] + [str(p) for p in paths]
    res = exec.run_cmd(cmd, cwd=str(SANDBOX_ROOT))
    return {
        "ok": res.ok,
        "detail": res.detail,
        "returncode": res.data.get("returncode"),
        "stderr": res.data.get("stderr", ""),
        "stdout": res.data.get("stdout", ""),
    }

def validate_json_paths(paths: List[Path]) -> Dict[str, Any]:
    ok = True
    errors: List[Dict[str, str]] = []
    for p in paths:
        try:
            raw = p.read_text(encoding="utf-8")
            json.loads(raw)
        except Exception as e:
            ok = False
            errors.append({"path": str(p), "error": str(e)})
    return {"ok": ok, "detail": "OK" if ok else "JSON_INVALID", "errors": errors}


def postflight_validate(applied_paths: List[Path], exec: SandboxExecutor) -> Dict[str, Any]:
    py_targets = [p for p in applied_paths if p.suffix.lower() == ".py"]
    json_targets = [p for p in applied_paths if p.suffix.lower() == ".json"]

    results: Dict[str, Any] = {"py": None, "json": None, "ok": True, "detail": "OK"}

    if py_targets:
        py_res = py_compile_paths(py_targets, exec)
        results["py"] = py_res
        if not py_res.get("ok"):
            results["ok"] = False
            results["detail"] = "PY_COMPILE_FAILED"

    if json_targets:
        js_res = validate_json_paths(json_targets)
        results["json"] = js_res
        if not js_res.get("ok"):
            results["ok"] = False
            results["detail"] = "JSON_VALIDATION_FAILED"

    # If there are other file types, we do not validate them in v1.1.x
    return results


def _guard_dest_in_repo(dest: Path, repo_root: Path) -> None:
    dest = dest.resolve()
    repo_root = repo_root.resolve()
    try:
        dest.relative_to(repo_root)
    except Exception:
        raise PermissionError(f"DEST_OUTSIDE_REPO_ROOT: {dest}")

    # hard deny any touch to runtime
    if DENY_RUNTIME in dest.parents or dest == DENY_RUNTIME:
        raise PermissionError(f"DEST_TOUCHES_RUNTIME_DENIED: {dest}")


def preflight(bundle: Dict[str, Any], dest_root: Path) -> Dict[str, Any]:
    items = bundle.get("items", [])
    if not isinstance(items, list) or len(items) == 0:
        return {"ok": False, "reason": "EMPTY_BUNDLE"}

    # validate dest_root is under repo root
    _guard_dest_in_repo(dest_root, REPO_ROOT)

    # Validate each item
    for it in items:
        kind = it.get("kind")
        ws = Path(it.get("workspace_path", "")).resolve()
        if WORK_DIR not in ws.parents and ws != WORK_DIR:
            return {"ok": False, "reason": "WORKSPACE_PATH_OUTSIDE_TMP_WORKDIR", "workspace_path": str(ws)}

        if kind == "new_file":
            dest = (dest_root / ws.name).resolve()
            _guard_dest_in_repo(dest, REPO_ROOT)
        elif kind == "modify":
            dest = Path(it.get("repo_path", "")).resolve()
            _guard_dest_in_repo(dest, REPO_ROOT)
        else:
            return {"ok": False, "reason": f"UNKNOWN_KIND:{kind}"}

    return {"ok": True, "reason": "OK", "count": len(items)}


def apply_bundle(bundle_path: str, dest_dir: Optional[str] = None, approve_token: Optional[str] = None) -> Dict[str, Any]:
    policy = SandboxPolicy.default()
    exec = SandboxExecutor(policy=policy)

    run_id = f"apply_{int(time.time())}"
    logger = SandboxLogger(log_path=str(LOG_PATH), run_id=run_id)

    bpath = Path(bundle_path).resolve()
    policy.assert_can_read(bpath)

    bundle = read_json(bpath, policy)
    proposal_id = bundle.get("proposal_id", "unknown")

    required_token = f"APPLY_{proposal_id}"
    if approve_token != required_token:
        msg = f"APPROVAL_REQUIRED: pass --approve={required_token}"
        logger.emit("apply_denied", {"ts": utc_iso(), "bundle_path": str(bpath), "proposal_id": proposal_id, "required": required_token})
        return {"ok": False, "run_id": run_id, "error": msg, "required": required_token}

    dest_root = Path(dest_dir).resolve() if dest_dir else DEFAULT_DEST_DIR
    dest_root = dest_root.resolve()

    # log start
    logger.emit("apply_start", {"ts": utc_iso(), "bundle_path": str(bpath), "proposal_id": proposal_id, "dest_root": str(dest_root)})

    pf = preflight(bundle, dest_root)
    logger.emit("apply_preflight", pf)
    if not pf.get("ok"):
        return {"ok": False, "run_id": run_id, "proposal_id": proposal_id, "error": f"PRECHECK_FAILED:{pf}"}

    items = bundle.get("items", [])
    backups: List[Dict[str, str]] = []
    applied: List[Dict[str, Any]] = []

    ensure_dir(dest_root)
    ensure_dir(STATE_DIR)

    try:
        for it in items:
            kind = it.get("kind")
            ws_path = Path(it["workspace_path"]).resolve()
            policy.assert_can_read(ws_path)

            if kind == "new_file":
                dest = (dest_root / ws_path.name).resolve()
                _guard_dest_in_repo(dest, REPO_ROOT)

                if dest.exists():
                    bak = backup_path_for(dest)
                    shutil.copy2(dest, bak)
                    backups.append({"dest": str(dest), "bak": str(bak)})

                shutil.copy2(ws_path, dest)
                applied.append({"kind": kind, "workspace_path": str(ws_path), "dest": str(dest)})

            elif kind == "modify":
                dest = Path(it["repo_path"]).resolve()
                _guard_dest_in_repo(dest, REPO_ROOT)

                bak = backup_path_for(dest)
                shutil.copy2(dest, bak)
                backups.append({"dest": str(dest), "bak": str(bak)})

                shutil.copy2(ws_path, dest)
                applied.append({"kind": kind, "workspace_path": str(ws_path), "dest": str(dest)})

        # postflight validation:
        # - .py => py_compile
        # - .json => json.loads
        applied_paths = [Path(x["dest"]).resolve() for x in applied]
        val = postflight_validate(applied_paths, exec)
        logger.emit("apply_validation", {"targets": [str(p) for p in applied_paths], "validation": val})

        if not val.get("ok"):
            raise RuntimeError(f"VALIDATION_FAILED: {val}")

        receipt = {
            "ts": utc_iso(),
            "proposal_id": proposal_id,
            "bundle_path": str(bpath),
            "dest_root": str(dest_root),
            "applied": applied,
            "backups": backups,
            "validation": val,
        }
        receipt_path = (STATE_DIR / f"applied_{proposal_id}.json").resolve()
        receipt_path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.emit("apply_success", {"receipt_path": str(receipt_path), "applied": applied})

        return {"ok": True, "run_id": run_id, "proposal_id": proposal_id, "applied": applied, "backups": backups, "validation": val, "receipt": str(receipt_path)}

    except Exception as e:
        # rollback
        rb = {"ok": False, "error": str(e), "rolled_back": []}

        for b in reversed(backups):
            dest = Path(b["dest"]).resolve()
            bak = Path(b["bak"]).resolve()
            try:
                if bak.exists():
                    shutil.copy2(bak, dest)
                    rb["rolled_back"].append({"dest": str(dest), "bak": str(bak), "status": "restored"})
            except Exception as e2:
                rb["rolled_back"].append({"dest": str(dest), "bak": str(bak), "status": f"rollback_error:{e2}"})

        for a in applied:
            dest = Path(a["dest"]).resolve()
            try:
                # delete new files with no backup
                if dest.exists() and not any(x["dest"] == str(dest) for x in backups):
                    dest.unlink()
                    rb["rolled_back"].append({"dest": str(dest), "status": "deleted_new_file"})
            except Exception as e3:
                rb["rolled_back"].append({"dest": str(dest), "status": f"delete_error:{e3}"})

        logger.emit("apply_failed", rb)
        return {"ok": False, "run_id": run_id, "proposal_id": proposal_id, "error": str(e), "rollback": rb}


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        raise SystemExit("Usage: python apply_gate.py <bundle_path> [dest_dir] [--approve=APPLY_<proposal_id>]")

    bundle = sys.argv[1]
    dest = None
    approve = None

    for a in sys.argv[2:]:
        if a.startswith("--approve="):
            approve = a.split("=", 1)[1]
        else:
            dest = a

    out = apply_bundle(bundle, dest_dir=dest, approve_token=approve)
    print(json.dumps(out, ensure_ascii=False, indent=2))

