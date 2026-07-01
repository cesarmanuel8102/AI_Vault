#!/usr/bin/env python3
"""
One-command local launcher for Brain Chat V9 + Dashboard.

Starts:
- Brain main app on http://127.0.0.1:8091 (with strict operator token)
- Dashboard app on http://127.0.0.1:8092 (same token)

The token is set only in the server process environments and printed to the
console. It is NOT written to .env or committed files.

Usage:
    python tmp_agent/brain_v9/start_local_browser_operational.py
"""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

LOCAL_TOKEN = "AGENTV2_TEST_ADMIN_TOKEN_08F8_R1B"
BRAIN_PORT = 8091
DASHBOARD_PORT = 8092
BASE_DIR = Path(__file__).resolve().parent
ROOT_DIR = BASE_DIR.parent.parent


def _port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", port)) == 0


def _wait_for_http(url: str, timeout: float = 30.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1.0) as r:
                return r.status == 200
        except Exception:
            time.sleep(0.5)
    return False


def _start_process(name: str, cmd: list[str], env: dict[str, str]) -> tuple[subprocess.Popen, Path]:
    merged_env = {**os.environ, **env, "PYTHONPATH": str(ROOT_DIR)}
    print(f"[launcher] {name} PYTHONPATH: {merged_env.get('PYTHONPATH')}")
    log_path = BASE_DIR / f"start_local_browser_operational_{name}.log"
    print(f"[launcher] Starting {name}: {' '.join(cmd)}")
    print(f"[launcher] {name} log: {log_path}")
    log_file = open(log_path, "w", encoding="utf-8")
    proc = subprocess.Popen(
        cmd,
        env=merged_env,
        cwd=str(ROOT_DIR),
        stdout=log_file,
        stderr=subprocess.STDOUT,
        text=True,
        # Windows: avoid popping extra console windows when launcher is run from another process.
        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
    )
    proc._log_file = log_file  # type: ignore[attr-defined]
    return proc, log_path


def _tail_log(log_path: Path, prefix: str, lines: int = 3) -> None:
    if not log_path.exists():
        return
    text = log_path.read_text(encoding="utf-8")
    tail = text.splitlines()[-lines:]
    for line in tail:
        print(f"[{prefix}] {line}")


def main() -> int:
    # Ensure UTF-8 output on Windows consoles that support it.
    if sys.platform == "win32" and sys.stdout.encoding.lower() not in {"utf-8", "utf8"}:
        try:
            sys.stdout.reconfigure(encoding="utf-8")
            sys.stderr.reconfigure(encoding="utf-8")
        except Exception:
            pass

    print("=" * 64)
    print(" Brain Chat V9 - Local Browser Operational Launcher")
    print("=" * 64)

    if _port_in_use(BRAIN_PORT):
        print(f"[ERROR] Port {BRAIN_PORT} is already in use. Stop the existing Brain server first.")
        return 1
    if _port_in_use(DASHBOARD_PORT):
        print(f"[ERROR] Port {DASHBOARD_PORT} is already in use. Stop the existing dashboard server first.")
        return 1

    common_env = {
        "BRAIN_ADMIN_TOKEN": LOCAL_TOKEN,
        "BRAIN_SAFE_MODE": "false",
        "BRAIN_START_AUTONOMY": "false",
        "BRAIN_START_PROACTIVE": "false",
        "BRAIN_START_SELF_DIAGNOSTIC": "false",
        "BRAIN_START_QC_LIVE_MONITOR": "false",
        "BRAIN_WARMUP_MODEL": "false",
        "BRAIN_ENABLE_UNSAFE_DEV_ENDPOINTS": "false",
        "BRAIN_LOG_LEVEL": "info",
    }

    brain_cmd = [sys.executable, str(BASE_DIR / "start_safe_server.py")]

    # The dashboard app imports from tmp_agent.brain_v9.*; ensure repo root is on PYTHONPATH via env.
    dashboard_cmd = [
        sys.executable,
        "-c",
        "import uvicorn; uvicorn.run('tmp_agent.brain_v9.dashboard.dashboard_app:app', "
        f"host='127.0.0.1', port={DASHBOARD_PORT}, log_level='info', reload=False)",
    ]

    brain_proc, brain_log = _start_process("brain", brain_cmd, common_env)
    dashboard_proc, dashboard_log = _start_process("dashboard", dashboard_cmd, common_env)

    print("[launcher] Waiting for services to become healthy...")
    brain_ok = _wait_for_http(f"http://127.0.0.1:{BRAIN_PORT}/health", timeout=60.0)
    dashboard_ok = _wait_for_http(f"http://127.0.0.1:{DASHBOARD_PORT}/health", timeout=30.0)

    print()
    if brain_ok and dashboard_ok:
        print("[OK] Brain and Dashboard are operational")
        print()
        print(f"Brain Chat URL: http://127.0.0.1:{BRAIN_PORT}/ui/")
        print(f"Dashboard URL:  http://127.0.0.1:{DASHBOARD_PORT}/")
        print(f"Local operator token: {LOCAL_TOKEN}")
        print()
        print("Paste the token into the 'Token de operador' field in the UI.")
        print()
        print(f"Health Brain:     http://127.0.0.1:{BRAIN_PORT}/health")
        print(f"Health Dashboard: http://127.0.0.1:{DASHBOARD_PORT}/health")
        print(f"Agent status:     http://127.0.0.1:{BRAIN_PORT}/v2/agent/status")
        print()
        print("Press Ctrl+C to stop both services.")
    else:
        print("[ERROR] Startup incomplete:")
        print(f"   Brain healthy:     {brain_ok}")
        print(f"   Dashboard healthy: {dashboard_ok}")
        _tail_log(brain_log, "brain")
        _tail_log(dashboard_log, "dashboard")
        brain_proc.terminate()
        dashboard_proc.terminate()
        try:
            brain_proc.wait(timeout=5.0)
            dashboard_proc.wait(timeout=5.0)
        except subprocess.TimeoutExpired:
            brain_proc.kill()
            dashboard_proc.kill()
        return 1

    try:
        while brain_proc.poll() is None and dashboard_proc.poll() is None:
            _tail_log(brain_log, "brain", lines=1)
            _tail_log(dashboard_log, "dashboard", lines=1)
            time.sleep(1.0)
    except KeyboardInterrupt:
        print("\n[launcher] Stopping services...")
    finally:
        brain_proc.terminate()
        dashboard_proc.terminate()
        try:
            brain_proc.wait(timeout=5.0)
            dashboard_proc.wait(timeout=5.0)
        except subprocess.TimeoutExpired:
            brain_proc.kill()
            dashboard_proc.kill()
    return 0


if __name__ == "__main__":
    sys.exit(main())
