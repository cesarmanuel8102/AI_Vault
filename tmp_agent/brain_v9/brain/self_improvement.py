"""
Brain V9 - Self Improvement
Pipeline gobernado:
staging -> validation -> promotion job -> restart -> smoke tests -> rollback si falla.
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List

from brain_v9.brain.utility import read_utility_state
from brain_v9.config import BASE_PATH

log = logging.getLogger("self_improvement")

STATE_ROOT = BASE_PATH / "tmp_agent" / "state" / "self_improvement"
CHANGES_ROOT = STATE_ROOT / "changes"
STAGING_ROOT = BASE_PATH / "tmp_agent" / "staging"
LEDGER_FILE = STATE_ROOT / "self_improvement_ledger.json"
POLICY_FILE = STATE_ROOT / "self_improvement_policy.json"

ALLOWED_ROOTS = [
    (BASE_PATH / "tmp_agent" / "brain_v9").resolve(),
    (BASE_PATH / "tmp_agent" / "ops").resolve(),
]


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _ensure_dirs() -> None:
    for p in [STATE_ROOT, CHANGES_ROOT, STAGING_ROOT]:
        p.mkdir(parents=True, exist_ok=True)


def _ensure_policy() -> None:
    if POLICY_FILE.exists():
        return
    policy = {
        "schema_version": "self_improvement_policy_v2",
        "created_utc": _utc_now(),
        "domain_rules": {
            "ui": "auto_with_validation",
            "tools": "auto_with_validation",
            "runtime_core": "staging_required",
            "trading_connectors": "staging_required",
            "trading_capital": "autonomous_forbidden",
            "credentials": "autonomous_forbidden",
        },
        "forbidden_path_markers": [
            "\\tmp_agent\\Secrets\\",
            "\\Secrets\\",
            "\\credentials\\",
            "capital_state.json",
            "wallet",
            "live_trading",
            "broker_live",
        ],
    }
    POLICY_FILE.write_text(json.dumps(policy, ensure_ascii=False, indent=2), encoding="utf-8")


def _load_policy() -> Dict:
    _ensure_dirs()
    _ensure_policy()
    return json.loads(POLICY_FILE.read_text(encoding="utf-8"))


def _load_ledger() -> Dict:
    _ensure_dirs()
    _ensure_policy()
    if not LEDGER_FILE.exists():
        seed = {"schema_version": "self_improvement_ledger_v2", "updated_utc": _utc_now(), "entries": []}
        LEDGER_FILE.write_text(json.dumps(seed, ensure_ascii=False, indent=2), encoding="utf-8")
        return seed
    return json.loads(LEDGER_FILE.read_text(encoding="utf-8"))


def _save_ledger(ledger: Dict) -> None:
    ledger["updated_utc"] = _utc_now()
    LEDGER_FILE.write_text(json.dumps(ledger, ensure_ascii=False, indent=2), encoding="utf-8")


def _check_allowed_target(path_str: str) -> Path:
    path = Path(path_str).resolve()
    if not any(str(path).startswith(str(root)) for root in ALLOWED_ROOTS):
        raise PermissionError(f"Ruta no permitida para automejora: {path}")
    if not path.exists():
        raise FileNotFoundError(f"No existe: {path}")
    return path


def _classify_domain(change_type: str, files: List[Dict]) -> str:
    if change_type:
        return change_type
    targets = " ".join(item["target"].lower() for item in files)
    if "\\secrets\\" in targets or "credential" in targets:
        return "credentials"
    if "\\trading\\" in targets and ("capital" in targets or "broker" in targets or "order" in targets):
        return "trading_capital"
    if "\\trading\\" in targets:
        return "trading_connectors"
    if "\\ui\\" in targets:
        return "ui"
    if "\\agent\\" in targets or "\\tools.py" in targets:
        return "tools"
    return "runtime_core"


def _required_endpoints(files: List[Dict]) -> List[str]:
    endpoints = ["/health", "/status", "/brain/utility"]
    targets = " ".join(item["target"].lower() for item in files)
    if any(token in targets for token in ["main.py", "session.py", "llm.py", "utility.py"]):
        endpoints.extend(["/brain/utility", "/self-diagnostic"])
    if "\\autonomy\\" in targets:
        endpoints.append("/autonomy/status")
    if "\\trading\\" in targets:
        endpoints.append("/trading/health")
    return sorted(set(endpoints))


def _run_subprocess(args: List[str], timeout: int = 90) -> Dict:
    t0 = time.time()
    proc = subprocess.run(args, capture_output=True, text=True, timeout=timeout, cwd=str(BASE_PATH / "tmp_agent"))
    return {
        "passed": proc.returncode == 0,
        "returncode": proc.returncode,
        "stdout": proc.stdout[:4000],
        "stderr": proc.stderr[:4000],
        "duration_ms": round((time.time() - t0) * 1000, 2),
    }


def _run_subprocess_with_env(args: List[str], *, timeout: int = 90, extra_env: Dict[str, str] | None = None) -> Dict:
    t0 = time.time()
    env = os.environ.copy()
    if extra_env:
        env.update(extra_env)
    proc = subprocess.run(
        args,
        capture_output=True,
        text=True,
        timeout=timeout,
        cwd=str(BASE_PATH / "tmp_agent"),
        env=env,
    )
    return {
        "passed": proc.returncode == 0,
        "returncode": proc.returncode,
        "stdout": proc.stdout[:4000],
        "stderr": proc.stderr[:4000],
        "duration_ms": round((time.time() - t0) * 1000, 2),
    }


def _build_import_check_script(files: List[str]) -> str:
    escaped = ",".join(repr(f) for f in files)
    return "\n".join([
        "import importlib.util, pathlib, sys, traceback, json",
        f"files = [{escaped}]",
        "errors = []",
        "for raw in files:",
        "    path = pathlib.Path(raw)",
        "    try:",
        "        name = 'stage_' + path.stem + '_' + str(abs(hash(str(path))))",
        "        spec = importlib.util.spec_from_file_location(name, path)",
        "        if spec is None or spec.loader is None:",
        "            raise RuntimeError(f'No spec for {path}')",
        "        mod = importlib.util.module_from_spec(spec)",
        "        spec.loader.exec_module(mod)",
        "    except Exception as exc:",
        "        errors.append({'file': str(path), 'error': str(exc), 'trace': traceback.format_exc()[-2000:]})",
        "if errors:",
        "    print(json.dumps({'passed': False, 'errors': errors}, ensure_ascii=False))",
        "    sys.exit(1)",
        "print('{\"passed\": true}')",
    ])


def _discover_relevant_tests(files: List[Dict]) -> List[str]:
    tests_root = BASE_PATH / "tmp_agent" / "tests"
    if not tests_root.exists():
        return []
    candidates: List[Path] = []
    for item in files:
        target = Path(item["target"])
        stem = target.stem.lower()
        parent = target.parent.name.lower()
        for test_file in tests_root.rglob("test_*.py"):
            name = test_file.name.lower()
            if stem in name or parent in name:
                candidates.append(test_file)
    seen = set()
    ordered = []
    for path in candidates:
        raw = str(path)
        if raw not in seen:
            seen.add(raw)
            ordered.append(raw)
    return ordered[:8]


def _capture_impact_snapshot() -> Dict:
    state = read_utility_state()
    snapshot = {
        "captured_utc": _utc_now(),
        "u_score": state.get("u_score"),
        "verdict": state.get("verdict"),
        "can_promote": state.get("can_promote"),
        "blockers": state.get("blockers", []),
        "current_phase": state.get("current_phase"),
    }
    # Enrich with chat quality metrics (P-OP56)
    try:
        _metrics_base = Path(BASE_PATH) / "tmp_agent" / "state"
        chat_metrics_path = _metrics_base / "brain_metrics" / "chat_metrics_latest.json"
        if chat_metrics_path.exists():
            cm = json.loads(chat_metrics_path.read_text(encoding="utf-8"))
            total = cm.get("total_conversations", 0)
            success = cm.get("success", 0)
            snapshot["chat_success_rate"] = round(success / max(total, 1), 4)
            snapshot["chat_total"] = total
            snapshot["chat_avg_latency_ms"] = cm.get("avg_latency_ms")
        self_test_path = _metrics_base / "brain_metrics" / "self_test_latest.json"
        if self_test_path.exists():
            st = json.loads(self_test_path.read_text(encoding="utf-8"))
            snapshot["self_test_score"] = st.get("score")
            snapshot["self_test_passed"] = st.get("passed")
            snapshot["self_test_total"] = st.get("total")
    except Exception:
        pass
    return snapshot


def _compute_impact_delta(before: Dict | None, after: Dict | None) -> Dict | None:
    if not before or not after:
        return None
    before_score = before.get("u_score")
    after_score = after.get("u_score")
    delta_score = None
    if isinstance(before_score, (int, float)) and isinstance(after_score, (int, float)):
        delta_score = round(after_score - before_score, 6)
    delta = {
        "before_u_score": before_score,
        "after_u_score": after_score,
        "delta_u_score": delta_score,
        "verdict_changed": before.get("verdict") != after.get("verdict"),
        "can_promote_changed": before.get("can_promote") != after.get("can_promote"),
        "blockers_changed": before.get("blockers") != after.get("blockers"),
    }
    # Chat quality delta (P-OP56)
    if before.get("self_test_score") is not None and after.get("self_test_score") is not None:
        delta["before_self_test_score"] = before["self_test_score"]
        delta["after_self_test_score"] = after["self_test_score"]
        delta["delta_self_test_score"] = round(after["self_test_score"] - before["self_test_score"], 4)
    if before.get("chat_success_rate") is not None and after.get("chat_success_rate") is not None:
        delta["before_chat_success_rate"] = before["chat_success_rate"]
        delta["after_chat_success_rate"] = after["chat_success_rate"]
        delta["delta_chat_success_rate"] = round(after["chat_success_rate"] - before["chat_success_rate"], 4)
    return delta


def _metric_degradation_threshold(before_u_score: float | int | None) -> float:
    if not isinstance(before_u_score, (int, float)):
        return 0.15
    return round(max(abs(float(before_u_score)) * 0.15, 0.15), 6)


def _is_metric_degraded(before: Dict | None, after: Dict | None) -> bool:
    if not before or not after:
        return False
    before_score = before.get("u_score")
    after_score = after.get("u_score")
    if not isinstance(before_score, (int, float)) or not isinstance(after_score, (int, float)):
        return False
    threshold = _metric_degradation_threshold(before_score)
    delta = float(after_score) - float(before_score)
    return delta < -threshold


def _evaluate_promotion_gate(metadata: Dict) -> Dict:
    policy = _load_policy()
    domain = _classify_domain(metadata.get("change_type", ""), metadata["files"])
    domain_rule = policy.get("domain_rules", {}).get(domain, "staging_required")
    validation = metadata.get("validation") or {}
    targets = [item["target"].lower() for item in metadata["files"]]
    forbidden_markers = [m.lower() for m in policy.get("forbidden_path_markers", [])]
    sensitive_path_hit = any(marker in target for target in targets for marker in forbidden_markers)
    checks = {
        "domain_allowed": domain_rule != "autonomous_forbidden",
        "sensitive_paths_allowed": not sensitive_path_hit,
        "backup_ready": True,
        "validation_passed": bool(validation.get("passed")),
        "required_endpoints_declared": bool(validation.get("required_endpoints")),
    }
    allow_promote = all(checks.values())
    blockers = [name for name, ok in checks.items() if not ok]
    return {
        "evaluated_utc": _utc_now(),
        "domain": domain,
        "domain_rule": domain_rule,
        "checks": checks,
        "allow_promote": allow_promote,
        "blockers": blockers,
        "required_endpoints": validation.get("required_endpoints", ["/health", "/status"]),
    }


def _apply_result_to_metadata(metadata: Dict, result: Dict) -> Dict:
    desired_status = "promoted" if result.get("promoted") else "rolled_back" if result.get("rollback") else "promotion_failed"
    metadata["status"] = desired_status
    metadata["promotion"] = {
        "status": "completed",
        "artifact": str(Path(metadata["change_dir"]) / "promotion_result.json"),
        "result": result,
    }
    metadata["impact_after"] = result.get("impact_after")
    metadata["impact_delta"] = _compute_impact_delta(metadata.get("impact_before"), result.get("impact_after"))
    if result.get("rollback"):
        metadata["rollback"] = metadata.get("rollback") or {
            "timestamp": _utc_now(),
            "trigger": "automatic_after_promotion_failure",
        }
    return metadata


def _apply_result_to_entry(entry: Dict, result: Dict) -> Dict:
    entry["status"] = "promoted" if result.get("promoted") else "rolled_back" if result.get("rollback") else "promotion_failed"
    entry["restart"] = "ok" if result.get("promoted") else "rolled_back_healthy" if result.get("rollback") and result.get("health_status") == "healthy" else "failed"
    entry["health"] = result.get("health_status")
    entry["rollback"] = bool(result.get("rollback"))
    entry["impact_after"] = result.get("impact_after")
    entry["impact_delta"] = _compute_impact_delta(entry.get("impact_before"), result.get("impact_after"))
    return entry


def _reconcile_ledger(ledger: Dict) -> Dict:
    changed = False
    for entry in ledger.get("entries", []):
        change_dir = CHANGES_ROOT / entry["change_id"]
        metadata_path = change_dir / "metadata.json"
        promotion_result_path = change_dir / "promotion_result.json"
        if metadata_path.exists():
            try:
                metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
                if metadata.get("validation"):
                    desired_validation = "passed" if metadata["validation"].get("passed") else "failed"
                    if entry.get("validation") != desired_validation:
                        entry["validation"] = desired_validation
                        changed = True
                if metadata.get("promotion_gate"):
                    gate = bool(metadata["promotion_gate"].get("allow_promote"))
                    if entry.get("gate") != gate:
                        entry["gate"] = gate
                        changed = True
                if metadata.get("impact_before") and entry.get("impact_before") != metadata.get("impact_before"):
                    entry["impact_before"] = metadata.get("impact_before")
                    changed = True
                if metadata.get("status") and entry.get("status") != metadata["status"] and not promotion_result_path.exists():
                    entry["status"] = metadata["status"]
                    changed = True
            except Exception as exc:
                log.debug("Error syncing metadata for entry %s: %s", entry.get("id", "?"), exc)
        if promotion_result_path.exists():
            try:
                result = json.loads(promotion_result_path.read_text(encoding="utf-8-sig"))
                before_entry = dict(entry)
                _apply_result_to_entry(entry, result)
                if entry != before_entry:
                    changed = True
                if metadata_path.exists():
                    try:
                        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
                        before_meta = json.dumps(metadata, ensure_ascii=False, sort_keys=True)
                        metadata = _apply_result_to_metadata(metadata, result)
                        after_meta = json.dumps(metadata, ensure_ascii=False, sort_keys=True)
                        if before_meta != after_meta:
                            metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
                    except Exception as exc:
                        log.debug("Error applying promotion result to metadata: %s", exc)
            except Exception as exc:
                log.warning("Error processing promotion result for entry %s: %s", entry.get("id", "?"), exc)
    if changed:
        _save_ledger(ledger)
    return ledger


def get_self_improvement_ledger() -> Dict:
    return _reconcile_ledger(_load_ledger())


def get_change_status(change_id: str) -> Dict:
    ledger = get_self_improvement_ledger()
    entry = next((item for item in ledger.get("entries", []) if item.get("change_id") == change_id), None)
    if entry is None:
        raise FileNotFoundError(f"Change no encontrado: {change_id}")
    metadata_path = CHANGES_ROOT / change_id / "metadata.json"
    result_path = CHANGES_ROOT / change_id / "promotion_result.json"
    job_path = CHANGES_ROOT / change_id / "promotion_job.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8")) if metadata_path.exists() else {}
    status = {
        "change_id": change_id,
        "job_id": f"job_{change_id}",
        "status": entry.get("status"),
        "job_status": "completed" if result_path.exists() else "running" if job_path.exists() else "queued" if entry.get("status") == "promotion_scheduled" else "idle",
        "objective": entry.get("objective"),
        "gate": entry.get("gate"),
        "validation": entry.get("validation"),
        "artifact": str(result_path) if result_path.exists() else None,
        "impact_before": metadata.get("impact_before"),
        "impact_after": metadata.get("impact_after"),
        "impact_delta": metadata.get("impact_delta"),
    }
    if job_path.exists():
        status["job"] = json.loads(job_path.read_text(encoding="utf-8-sig"))
    if result_path.exists():
        status["promotion_result"] = json.loads(result_path.read_text(encoding="utf-8-sig"))
    return status


def create_staged_change(files: List[str], objective: str = "", change_type: str = "code_patch") -> Dict:
    _ensure_dirs()
    change_id = f"chg_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
    change_dir = CHANGES_ROOT / change_id
    stage_dir = STAGING_ROOT / change_id
    backups_dir = change_dir / "backups"
    change_dir.mkdir(parents=True, exist_ok=True)
    stage_dir.mkdir(parents=True, exist_ok=True)
    backups_dir.mkdir(parents=True, exist_ok=True)

    touched = []
    for file_path in files:
        src = _check_allowed_target(file_path)
        relative = src.relative_to(BASE_PATH)
        staged = stage_dir / relative
        staged.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, staged)
        touched.append({"target": str(src), "relative": str(relative), "staged": str(staged)})

    impact_before = _capture_impact_snapshot()
    metadata = {
        "change_id": change_id,
        "created_utc": _utc_now(),
        "objective": objective,
        "change_type": change_type,
        "status": "staged",
        "files": touched,
        "stage_dir": str(stage_dir),
        "change_dir": str(change_dir),
        "impact_before": impact_before,
        "validation": None,
        "promotion_gate": None,
        "promotion": None,
        "rollback": None,
    }
    (change_dir / "metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")

    ledger = _load_ledger()
    ledger["entries"].append({
        "change_id": change_id,
        "timestamp": metadata["created_utc"],
        "objective": objective,
        "files": [f["target"] for f in touched],
        "status": "staged",
        "validation": None,
        "gate": None,
        "restart": None,
        "health": None,
        "rollback": False,
        "impact_before": impact_before,
        "impact_after": None,
        "impact_delta": None,
    })
    _save_ledger(ledger)
    return metadata


def validate_staged_change(change_id: str) -> Dict:
    change_dir = CHANGES_ROOT / change_id
    metadata_path = change_dir / "metadata.json"
    if not metadata_path.exists():
        raise FileNotFoundError(f"Change no encontrado: {change_id}")
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))

    staged_py = [f["staged"] for f in metadata["files"] if f["staged"].endswith(".py")]
    result = {
        "passed": True,
        "errors": [],
        "logs": "",
        "duration_ms": 0,
        "validated_files": staged_py,
        "checks": {},
        "required_endpoints": _required_endpoints(metadata["files"]),
    }
    if staged_py:
        syntax_check = _run_subprocess(["python", "-m", "py_compile", *staged_py], timeout=90)
        result["checks"]["syntax"] = syntax_check
        if not syntax_check["passed"]:
            result["errors"].append(syntax_check["stderr"] or syntax_check["stdout"] or f"py_compile returncode={syntax_check['returncode']}")

        import_script = _build_import_check_script(staged_py)
        import_check = _run_subprocess(["python", "-c", import_script], timeout=90)
        result["checks"]["imports"] = import_check
        if not import_check["passed"]:
            result["errors"].append(import_check["stderr"] or import_check["stdout"] or "import validation failed")

        test_targets = _discover_relevant_tests(metadata["files"])
        if test_targets:
            staged_pythonpath = str(Path(metadata["stage_dir"]) / "tmp_agent")
            baseline_pythonpath = str(BASE_PATH / "tmp_agent")
            unit_check = _run_subprocess_with_env(
                ["python", "-m", "pytest", *test_targets, "-q"],
                timeout=180,
                extra_env={"PYTHONPATH": os.pathsep.join([staged_pythonpath, baseline_pythonpath])},
            )
            unit_check["targets"] = test_targets
            result["checks"]["unit_tests"] = unit_check
            if not unit_check["passed"]:
                result["errors"].append(unit_check["stderr"] or unit_check["stdout"] or "unit test validation failed")
        else:
            result["checks"]["unit_tests"] = {"passed": None, "targets": [], "status": "no_relevant_tests_found", "duration_ms": 0}

    result["duration_ms"] = round(sum(item.get("duration_ms", 0) for item in result["checks"].values()), 2)
    result["logs"] = "\n".join(
        filter(None, [item.get("stdout", "") + ("\n" + item.get("stderr", "") if item.get("stderr") else "") for item in result["checks"].values()])
    ).strip()[:6000]
    result["passed"] = not result["errors"]

    metadata["validation"] = result
    metadata["promotion_gate"] = _evaluate_promotion_gate(metadata)
    metadata["status"] = "validated" if result["passed"] else "validation_failed"
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")

    ledger = _load_ledger()
    for entry in ledger["entries"]:
        if entry["change_id"] == change_id:
            entry["validation"] = "passed" if result["passed"] else "failed"
            entry["status"] = metadata["status"]
            entry["gate"] = metadata["promotion_gate"]["allow_promote"]
    _save_ledger(ledger)
    return result


def _write_promote_helper(change_id: str, metadata: Dict) -> Path:
    helper_path = Path(metadata["change_dir"]) / "promote_change.ps1"
    backups_dir = Path(metadata["change_dir"]) / "backups"
    result_artifact = Path(metadata["change_dir"]) / "promotion_result.json"
    job_artifact = Path(metadata["change_dir"]) / "promotion_job.json"
    required_endpoints = metadata.get("promotion_gate", {}).get("required_endpoints", ["/health", "/status"])

    lines = [
        "$ErrorActionPreference = 'Stop'",
        f"$resultPath = '{result_artifact}'",
        f"$jobPath = '{job_artifact}'",
        "$promotionOk = $false",
        "$rollbackDone = $false",
        "$healthStatus = $null",
        "$endpointResults = @()",
        "$impactAfter = $null",
        "$metricCheckPassed = $true",
        "@{ change_id = '" + change_id + "'; job_id = 'job_" + change_id + "'; status = 'running'; updated_at = (Get-Date).ToString('s') } | ConvertTo-Json -Depth 4 | Set-Content $jobPath -Encoding UTF8",
    ]
    for idx, item in enumerate(metadata["files"]):
        target = item["target"]
        staged = item["staged"]
        backup = backups_dir / f"{idx}_{Path(target).name}.bak"
        lines.append(f"Copy-Item '{target}' '{backup}' -Force")
        lines.append(f"Copy-Item '{staged}' '{target}' -Force")
    lines.extend([
        "Start-Sleep -Seconds 1",
        "$conn = Get-NetTCPConnection -LocalPort 8090 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1",
        "if ($conn) { try { Stop-Process -Id $conn.OwningProcess -Force -ErrorAction SilentlyContinue } catch {} }",
        "Start-Sleep -Seconds 2",
        "$env:PYTHONUNBUFFERED = '1'",
        "$p = Start-Process -FilePath python -ArgumentList '-u','-m','brain_v9.main' -WorkingDirectory 'C:\\AI_VAULT\\tmp_agent' -WindowStyle Hidden -PassThru",
        "for ($i = 0; $i -lt 30; $i++) {",
        "  Start-Sleep -Seconds 1",
        "  try {",
        "    $resp = Invoke-RestMethod 'http://127.0.0.1:8090/health' -TimeoutSec 3",
        "    $healthStatus = $resp.status",
        "    if ($resp.status -eq 'healthy') { $promotionOk = $true; break }",
        "  } catch {}",
        "}",
        "if ($promotionOk) {",
    ])
    for endpoint in required_endpoints:
        lines.extend([
            "  try {",
            f"    $epResp = Invoke-RestMethod 'http://127.0.0.1:8090{endpoint}' -TimeoutSec 5",
            "    if ('" + endpoint + "' -eq '/brain/utility') { $impactAfter = @{ u_score = $epResp.u_score; verdict = $epResp.verdict; can_promote = $epResp.can_promote; blockers = $epResp.blockers } }",
            "    $endpointResults += @{ endpoint = '" + endpoint + "'; ok = $true; detail = 'ok' }",
            "  } catch {",
            "    $promotionOk = $false",
            "    $endpointResults += @{ endpoint = '" + endpoint + "'; ok = $false; detail = $_.Exception.Message }",
            "  }",
        ])
    lines.extend([
        "}",
        "if ($promotionOk -and $null -ne $impactAfter -and $null -ne $impactAfter.u_score) {",
        f"  $beforeU = {float(metadata.get('impact_before', {}).get('u_score', 0.0) or 0.0)}",
        f"  $metricThreshold = {_metric_degradation_threshold(metadata.get('impact_before', {}).get('u_score'))}",
        "  $afterU = [double]$impactAfter.u_score",
        "  $deltaU = $afterU - $beforeU",
        "  if ($deltaU -lt (-1 * $metricThreshold)) {",
        "    $promotionOk = $false",
        "    $metricCheckPassed = $false",
        "    $endpointResults += @{ endpoint = 'metric_check'; ok = $false; detail = ('u_score degraded by ' + $deltaU) }",
        "  } else {",
        "    $endpointResults += @{ endpoint = 'metric_check'; ok = $true; detail = ('u_score delta ' + $deltaU) }",
        "  }",
        "} elseif ($promotionOk) {",
        "  $endpointResults += @{ endpoint = 'metric_check'; ok = $true; detail = 'u_score not available; skipped' }",
        "}",
        "if (-not $promotionOk) {",
    ])
    for idx, item in enumerate(metadata["files"]):
        target = item["target"]
        backup = backups_dir / f"{idx}_{Path(target).name}.bak"
        lines.append(f"  Copy-Item '{backup}' '{target}' -Force")
    lines.extend([
        "  $rollbackDone = $true",
        "  $conn2 = Get-NetTCPConnection -LocalPort 8090 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1",
        "  if ($conn2) { try { Stop-Process -Id $conn2.OwningProcess -Force -ErrorAction SilentlyContinue } catch {} }",
        "  Start-Sleep -Seconds 2",
        "  $p2 = Start-Process cmd.exe -ArgumentList '/c', $cmd -WindowStyle Minimized -PassThru",
        "  for ($j = 0; $j -lt 30; $j++) {",
        "    Start-Sleep -Seconds 1",
        "    try {",
        "      $resp2 = Invoke-RestMethod 'http://127.0.0.1:8090/health' -TimeoutSec 3",
        "      $healthStatus = $resp2.status",
        "      if ($resp2.status -eq 'healthy') { break }",
        "    } catch {}",
        "  }",
        "}",
        "@{",
        f"  change_id = '{change_id}'",
        "  promoted = $promotionOk",
        "  rollback = $rollbackDone",
        "  health_status = $healthStatus",
        "  generated_at = (Get-Date).ToString('s')",
        "  endpoint_results = $endpointResults",
        "  impact_after = $impactAfter",
        "  metric_check_passed = $metricCheckPassed",
        "} | ConvertTo-Json -Depth 4 | Set-Content $resultPath -Encoding UTF8",
        "@{ change_id = '" + change_id + "'; job_id = 'job_" + change_id + "'; status = 'completed'; promoted = $promotionOk; rollback = $rollbackDone; updated_at = (Get-Date).ToString('s'); artifact = $resultPath } | ConvertTo-Json -Depth 4 | Set-Content $jobPath -Encoding UTF8",
    ])
    helper_path.write_text("\n".join(lines), encoding="utf-8")
    return helper_path


def promote_staged_change(change_id: str) -> Dict:
    change_dir = CHANGES_ROOT / change_id
    metadata_path = change_dir / "metadata.json"
    if not metadata_path.exists():
        raise FileNotFoundError(f"Change no encontrado: {change_id}")
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    gate = metadata.get("promotion_gate") or _evaluate_promotion_gate(metadata)
    metadata["promotion_gate"] = gate
    if not gate.get("allow_promote"):
        metadata["status"] = "promotion_blocked"
        metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
        return {"success": False, "status": "promotion_blocked", "reason": "promotion_gate_failed", "gate": gate}

    helper = _write_promote_helper(change_id, metadata)
    result_artifact = Path(metadata["change_dir"]) / "promotion_result.json"
    job_artifact = Path(metadata["change_dir"]) / "promotion_job.json"
    metadata["promotion"] = {
        "status": "scheduled",
        "helper": str(helper),
        "artifact": str(result_artifact),
        "job_id": f"job_{change_id}",
    }
    metadata["status"] = "promotion_scheduled"
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")

    subprocess.run(
        ["cmd.exe", "/c", "start", "", "powershell", "-ExecutionPolicy", "Bypass", "-File", str(helper)],
        cwd=str(BASE_PATH),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=15,
    )

    ledger = _load_ledger()
    for entry in ledger["entries"]:
        if entry["change_id"] == change_id:
            entry["status"] = "promotion_scheduled"
    _save_ledger(ledger)

    return {
        "success": True,
        "status": "promotion_scheduled",
        "job_id": f"job_{change_id}",
        "helper": str(helper),
        "artifact": str(result_artifact),
        "job_artifact": str(job_artifact),
        "gate": gate,
        "status_endpoint": f"/brain/self-improvement/change/{change_id}/status",
    }


def rollback_change(change_id: str) -> Dict:
    change_dir = CHANGES_ROOT / change_id
    metadata_path = change_dir / "metadata.json"
    if not metadata_path.exists():
        raise FileNotFoundError(f"Change no encontrado: {change_id}")
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    backups_dir = Path(metadata["change_dir"]) / "backups"
    restored = []
    for idx, item in enumerate(metadata["files"]):
        backup = backups_dir / f"{idx}_{Path(item['target']).name}.bak"
        if backup.exists():
            shutil.copy2(backup, item["target"])
            restored.append(item["target"])
    metadata["rollback"] = {"restored_files": restored, "timestamp": _utc_now()}
    metadata["status"] = "rolled_back"
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    ledger = _load_ledger()
    for entry in ledger["entries"]:
        if entry["change_id"] == change_id:
            entry["rollback"] = True
            entry["status"] = "rolled_back"
    _save_ledger(ledger)
    return {"success": True, "status": "rolled_back", "restored_files": restored}
