"""Technical self-introspection for Brain V9."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import psutil

from brain_v9.config import BASE_PATH, STATE_PATH

STATUS_PATH = STATE_PATH / "technical_introspection_status_latest.json"


def get_gpu_status() -> Dict[str, Any]:
    cmd = [
        "nvidia-smi",
        "--query-gpu=name,memory.total,memory.used,memory.free,utilization.gpu,temperature.gpu",
        "--format=csv,noheader,nounits",
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=8)
    except FileNotFoundError:
        return {"ok": False, "available": False, "error": "nvidia-smi_not_found"}
    except Exception as exc:
        return {"ok": False, "available": False, "error": str(exc)}
    if proc.returncode != 0:
        return {"ok": False, "available": False, "error": proc.stderr.strip()[:500]}

    gpus: List[Dict[str, Any]] = []
    for line in proc.stdout.splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 6:
            continue
        try:
            total = float(parts[1])
            used = float(parts[2])
            free = float(parts[3])
            util = float(parts[4])
            temp = float(parts[5])
            used_pct = 100.0 * used / total if total else 0.0
        except Exception:
            total = used = free = util = temp = used_pct = None
        gpus.append({
            "name": parts[0],
            "memory_total_mb": total,
            "memory_used_mb": used,
            "memory_free_mb": free,
            "memory_used_pct": round(used_pct, 2) if used_pct is not None else None,
            "utilization_gpu_pct": util,
            "temperature_c": temp,
        })
    return {"ok": True, "available": bool(gpus), "gpus": gpus, "updated_utc": _utc_now()}


def get_process_resource_status(pid: Optional[int] = None) -> Dict[str, Any]:
    pid = int(pid or os.getpid())
    try:
        proc = psutil.Process(pid)
        mem = proc.memory_info()
        return {
            "ok": True,
            "pid": pid,
            "name": proc.name(),
            "status": proc.status(),
            "cpu_percent": proc.cpu_percent(interval=0.05),
            "rss_mb": round(mem.rss / (1024 * 1024), 2),
            "vms_mb": round(mem.vms / (1024 * 1024), 2),
            "threads": proc.num_threads(),
            "create_time_utc": datetime.fromtimestamp(proc.create_time(), timezone.utc).isoformat().replace("+00:00", "Z"),
        }
    except Exception as exc:
        return {"ok": False, "pid": pid, "error": str(exc)}


def get_codebase_status() -> Dict[str, Any]:
    root = BASE_PATH / "tmp_agent" / "brain_v9"
    py_files = [p for p in root.rglob("*.py") if "__pycache__" not in str(p)] if root.exists() else []
    total_bytes = 0
    for path in py_files:
        try:
            total_bytes += path.stat().st_size
        except Exception:
            pass
    return {
        "ok": root.exists(),
        "root": str(root),
        "python_files": len(py_files),
        "python_total_mb": round(total_bytes / (1024 * 1024), 2),
        "entrypoints": {
            "main": str(root / "main.py"),
            "agent_loop": str(root / "agent" / "loop.py"),
            "agent_tools": str(root / "agent" / "tools.py"),
        },
    }


def build_introspection_status(pid: Optional[int] = None) -> Dict[str, Any]:
    vm = psutil.virtual_memory()
    disk = psutil.disk_usage(str(BASE_PATH))
    status = {
        "ok": True,
        "schema_version": "technical_introspection_status_v1",
        "python": sys.version.split()[0],
        "process": get_process_resource_status(pid),
        "system": {
            "cpu_percent": psutil.cpu_percent(interval=0.05),
            "ram_total_gb": round(vm.total / (1024 ** 3), 2),
            "ram_used_pct": vm.percent,
            "disk_total_gb": round(disk.total / (1024 ** 3), 2),
            "disk_used_pct": disk.percent,
        },
        "gpu": get_gpu_status(),
        "codebase": get_codebase_status(),
        "self_read_capability": {
            "enabled": True,
            "tools": ["read_file", "grep_codebase", "analyze_python", "get_technical_introspection"],
        },
        "hallucination_detection": {
            "enabled": True,
            "method": "metacognition.claim_risk_proxy",
            "perplexity_scores": False,
        },
        "updated_utc": _utc_now(),
    }
    STATUS_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATUS_PATH.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")
    return status


def read_introspection_status() -> Dict[str, Any]:
    try:
        if STATUS_PATH.exists():
            return json.loads(STATUS_PATH.read_text(encoding="utf-8"))
    except Exception:
        pass
    return build_introspection_status()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
