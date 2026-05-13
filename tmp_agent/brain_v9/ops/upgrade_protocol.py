"""
Brain V9 — Fase 7.3 Protocolo de Upgrade de Brain
Canonical pre-upgrade and post-upgrade checklist.
Formalizes the validation steps required before/after any runtime change.
"""
import asyncio
import logging
import time
from typing import Any, Dict, List, Optional

import aiohttp

logger = logging.getLogger("brain_v9.ops.upgrade_protocol")

BRAIN_URL = "http://localhost:8090"
HEALTH_TIMEOUT = 10
ENDPOINT_TIMEOUT = 10

# Critical endpoints that must return 200 after upgrade
CRITICAL_ENDPOINTS = [
    "/health",
    "/brain/strategy-engine/ranking",
    "/brain/strategy-engine/active-catalog",
    "/brain/strategy-engine/learning-loop",
    "/brain/strategy-engine/context-edge-validation",
    "/brain/strategy-engine/execution-audit",
    "/brain/ops/log-status",
    "/brain/ops/adn-quality",
]


async def _check_endpoint(session: aiohttp.ClientSession, path: str) -> Dict[str, Any]:
    """Check a single endpoint returns 200."""
    url = f"{BRAIN_URL}{path}"
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=ENDPOINT_TIMEOUT)) as resp:
            return {
                "endpoint": path,
                "status": resp.status,
                "ok": resp.status == 200,
            }
    except Exception as e:
        return {
            "endpoint": path,
            "status": None,
            "ok": False,
            "error": str(e),
        }


async def _check_health() -> Dict[str, Any]:
    """Verify Brain V9 is healthy and responsive."""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{BRAIN_URL}/health",
                timeout=aiohttp.ClientTimeout(total=HEALTH_TIMEOUT),
            ) as resp:
                data = await resp.json()
                return {
                    "check": "health",
                    "ok": data.get("status") == "healthy",
                    "version": data.get("version"),
                    "status": data.get("status"),
                }
    except Exception as e:
        return {"check": "health", "ok": False, "error": str(e)}


async def _check_all_endpoints() -> Dict[str, Any]:
    """Verify all critical endpoints respond with 200."""
    results = []
    try:
        async with aiohttp.ClientSession() as session:
            tasks = [_check_endpoint(session, ep) for ep in CRITICAL_ENDPOINTS]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            # Convert exceptions to dicts
            clean = []
            for r in results:
                if isinstance(r, Exception):
                    clean.append({"endpoint": "unknown", "ok": False, "error": str(r)})
                else:
                    clean.append(r)
            results = clean
    except Exception as e:
        results = [{"endpoint": "all", "ok": False, "error": str(e)}]

    all_ok = all(r.get("ok", False) for r in results)
    failed = [r["endpoint"] for r in results if not r.get("ok", False)]
    return {
        "check": "critical_endpoints",
        "ok": all_ok,
        "total": len(CRITICAL_ENDPOINTS),
        "passed": sum(1 for r in results if r.get("ok")),
        "failed_endpoints": failed,
        "details": results,
    }


async def _check_disk_space() -> Dict[str, Any]:
    """Verify disk space is not critical."""
    import shutil
    try:
        usage = shutil.disk_usage("C:/")
        used_pct = round((usage.used / usage.total) * 100, 1)
        free_gb = round(usage.free / (1024**3), 2)
        return {
            "check": "disk_space",
            "ok": used_pct < 95,
            "used_pct": used_pct,
            "free_gb": free_gb,
            "warning": used_pct >= 85,
        }
    except Exception as e:
        return {"check": "disk_space", "ok": False, "error": str(e)}


async def _check_py_compile() -> Dict[str, Any]:
    """Verify all brain_v9 modules compile without syntax errors."""
    from pathlib import Path
    import py_compile
    from brain_v9.config import BRAIN_V9_PATH

    src_dir = BRAIN_V9_PATH / "brain_v9"
    errors = []
    total = 0
    for py_file in src_dir.rglob("*.py"):
        total += 1
        try:
            py_compile.compile(str(py_file), doraise=True)
        except py_compile.PyCompileError as e:
            errors.append({"file": str(py_file.relative_to(BRAIN_V9_PATH)), "error": str(e)})

    return {
        "check": "py_compile",
        "ok": len(errors) == 0,
        "total_files": total,
        "errors": errors,
    }


async def run_pre_upgrade_checks() -> Dict[str, Any]:
    """
    Run all pre-upgrade checks. Call BEFORE making changes.
    Returns overall pass/fail and per-check details.
    """
    start = time.time()
    checks = await asyncio.gather(
        _check_health(),
        _check_all_endpoints(),
        _check_disk_space(),
        _check_py_compile(),
    )
    elapsed = round(time.time() - start, 2)

    all_ok = all(c.get("ok", False) for c in checks)
    return {
        "phase": "pre_upgrade",
        "overall": "PASS" if all_ok else "FAIL",
        "checks": {c["check"]: c for c in checks},
        "elapsed_seconds": elapsed,
        "advisory": "Safe to proceed with upgrade" if all_ok else "Resolve failures before upgrading",
    }


async def run_post_upgrade_checks() -> Dict[str, Any]:
    """
    Run all post-upgrade checks. Call AFTER making changes and restarting.
    Returns overall pass/fail and per-check details.
    """
    start = time.time()
    checks = await asyncio.gather(
        _check_health(),
        _check_all_endpoints(),
        _check_disk_space(),
        _check_py_compile(),
    )
    elapsed = round(time.time() - start, 2)

    all_ok = all(c.get("ok", False) for c in checks)
    return {
        "phase": "post_upgrade",
        "overall": "PASS" if all_ok else "FAIL",
        "checks": {c["check"]: c for c in checks},
        "elapsed_seconds": elapsed,
        "advisory": "Upgrade successful — system operational" if all_ok
                     else "ROLLBACK RECOMMENDED — post-upgrade checks failed",
    }


async def run_full_upgrade_validation() -> Dict[str, Any]:
    """
    Run pre and post checks together (for testing or manual validation).
    """
    pre = await run_pre_upgrade_checks()
    post = await run_post_upgrade_checks()
    return {
        "pre_upgrade": pre,
        "post_upgrade": post,
        "recommendation": (
            "System healthy" if pre["overall"] == "PASS" and post["overall"] == "PASS"
            else "Issues detected — review check details"
        ),
    }
