"""Host broker for model-authored research code.

The broker crosses exactly one trust boundary: it asks WSL2 to construct a
private Linux namespace and execute the trusted worker.  There is deliberately
no local-Python or reduced-security fallback.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import time
import uuid
from pathlib import Path
from typing import Any, Callable

from .autonomy_workspace import MAX_SCRIPT_OUTPUT_BYTES, WorkspaceViolation


SANDBOX_SCHEMA = "RESEARCH_SANDBOX_RUN_V1"
SANDBOX_MODE = "WSL2_NAMESPACE_CHROOT_SECCOMP_V1"
WORKER_SCHEMA = "RESEARCH_WORKER_RESULT_V1"
WORKSPACE_SUBDIRS = ("memory", "research", "tools", "datasets", "experiments")
MAX_ARGUMENTS = 64
MAX_ARGUMENT_BYTES = 16 * 1024
HOST_TIMEOUT_GRACE_SECONDS = 15.0
_SAFE_SCRIPT = re.compile(r"^tools/[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*\.py$")


def _windows_path_to_wsl(path: Path) -> str:
    resolved = path.resolve()
    drive = resolved.drive
    if len(drive) != 2 or drive[1] != ":":
        raise WorkspaceViolation("sandbox paths must use a local Windows drive")
    remainder = resolved.as_posix()[2:].lstrip("/")
    return f"/mnt/{drive[0].lower()}/{remainder}"


def _bounded_text(value: Any) -> tuple[str, bool]:
    encoded = str(value or "").encode("utf-8", errors="replace")
    if len(encoded) <= MAX_SCRIPT_OUTPUT_BYTES:
        return encoded.decode("utf-8", errors="replace"), False
    return (
        encoded[:MAX_SCRIPT_OUTPUT_BYTES].decode("utf-8", errors="ignore"),
        True,
    )


def _snapshot(root: Path) -> dict[str, dict[str, Any]]:
    snapshot: dict[str, dict[str, Any]] = {}
    for subdirectory in WORKSPACE_SUBDIRS:
        base = root / subdirectory
        for path in sorted(base.rglob("*")):
            relative = path.relative_to(root).as_posix()
            try:
                if path.is_symlink():
                    snapshot[relative] = {
                        "kind": "symlink",
                        "target": os.readlink(path),
                    }
                elif path.is_file():
                    digest = hashlib.sha256()
                    with path.open("rb") as handle:
                        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                            digest.update(chunk)
                    snapshot[relative] = {
                        "kind": "file",
                        "sha256": digest.hexdigest(),
                        "size_bytes": path.stat().st_size,
                    }
            except OSError:
                # DrvFS exposes Linux-created symlinks as inaccessible reparse
                # points to Win32. Never follow them while inventorying output.
                snapshot[relative] = {"kind": "inaccessible_reparse_point"}
    return snapshot


def _artifact_delta(
    before: dict[str, dict[str, Any]], after: dict[str, dict[str, Any]]
) -> list[dict[str, Any]]:
    changes: list[dict[str, Any]] = []
    for path in sorted(set(before) | set(after)):
        previous = before.get(path)
        current = after.get(path)
        if previous == current:
            continue
        operation = "CREATED" if previous is None else "DELETED" if current is None else "MODIFIED"
        item: dict[str, Any] = {"path": path, "operation": operation}
        if current is not None:
            item.update(current)
        changes.append(item)
    return changes


class WSLResearchSandbox:
    """Execute a research script through the fixed WSL2 isolation launcher."""

    def __init__(
        self,
        *,
        repo_root: str | Path,
        distro: str = "Ubuntu",
        runner: Callable[..., subprocess.CompletedProcess[bytes]] = subprocess.run,
    ) -> None:
        self.repo_root = Path(repo_root).resolve()
        self.distro = distro
        self.runner = runner
        self.launcher_path = self.repo_root / "scripts" / "run_research_worker_wsl.sh"
        self.worker_path = self.repo_root / "ibkr_paper_30d" / "research_worker_linux.py"

    def run(
        self,
        *,
        workspace_root: Path,
        script_relative: str,
        arguments: tuple[str, ...],
        timeout_seconds: float,
    ) -> dict[str, Any]:
        root = Path(workspace_root)
        if not root.is_absolute() or not root.is_dir():
            raise WorkspaceViolation("sandbox workspace must be an existing absolute directory")
        root = root.resolve()
        for subdirectory in WORKSPACE_SUBDIRS:
            child = root / subdirectory
            if not child.is_dir() or child.is_symlink():
                raise WorkspaceViolation(f"sandbox workspace directory invalid: {subdirectory}")

        if not isinstance(script_relative, str) or not _SAFE_SCRIPT.fullmatch(script_relative):
            raise WorkspaceViolation("research script path is not canonical")
        script_path = root / Path(*script_relative.split("/"))
        if not script_path.is_file() or script_path.is_symlink():
            raise WorkspaceViolation("research script must be a regular workspace file")
        if script_path.resolve().parent != (root / "tools").resolve() and (
            root / "tools"
        ).resolve() not in script_path.resolve().parents:
            raise WorkspaceViolation("research script escapes tools directory")

        if len(arguments) > MAX_ARGUMENTS:
            raise WorkspaceViolation("too many research script arguments")
        normalized_arguments: list[str] = []
        argument_bytes = 0
        for argument in arguments:
            value = str(argument)
            if "\x00" in value:
                raise WorkspaceViolation("research script arguments may not contain NUL")
            argument_bytes += len(value.encode("utf-8"))
            normalized_arguments.append(value)
        if argument_bytes > MAX_ARGUMENT_BYTES:
            raise WorkspaceViolation("research script argument bytes exceed limit")
        if not 1.0 <= float(timeout_seconds) <= 300.0:
            raise WorkspaceViolation("research script timeout is outside allowed bounds")
        if not self.launcher_path.is_file() or not self.worker_path.is_file():
            raise WorkspaceViolation("trusted research sandbox runtime is incomplete")

        before = _snapshot(root)
        nonce = uuid.uuid4().hex
        command = [
            "wsl.exe",
            "-d",
            self.distro,
            "-u",
            "root",
            "--exec",
            "/bin/bash",
            _windows_path_to_wsl(self.launcher_path),
            "--workspace",
            _windows_path_to_wsl(root),
            "--worker",
            _windows_path_to_wsl(self.worker_path),
            "--script",
            script_relative,
            "--timeout",
            str(int(float(timeout_seconds) + 0.999)),
            "--nonce",
            nonce,
            "--",
            *normalized_arguments,
        ]
        started = time.monotonic()
        try:
            completed = self.runner(
                command,
                check=False,
                shell=False,
                capture_output=True,
                timeout=float(timeout_seconds) + HOST_TIMEOUT_GRACE_SECONDS,
                env={"SystemRoot": os.environ["SystemRoot"]},
            )
        except (FileNotFoundError, OSError, subprocess.TimeoutExpired) as exc:
            raise WorkspaceViolation(
                f"WSL2 research sandbox unavailable: {type(exc).__name__}"
            ) from exc
        elapsed_ms = int((time.monotonic() - started) * 1000)

        raw_stdout = completed.stdout or b""
        raw_stderr = completed.stderr or b""
        if completed.returncode in (124, 137) and not raw_stdout:
            worker = {
                "schema": WORKER_SCHEMA,
                "status": "TIMEOUT",
                "returncode": completed.returncode,
                "stdout": "",
                "stderr": raw_stderr.decode("utf-8", errors="replace"),
                "resource_usage": {},
                "failure_reason": "SANDBOX_TIMEOUT",
            }
        else:
            try:
                worker = json.loads(raw_stdout.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                diagnostic, _ = _bounded_text(raw_stderr.decode("utf-8", errors="replace"))
                raise WorkspaceViolation(
                    "WSL2 research sandbox returned no authenticated worker result"
                    + (f": {diagnostic}" if diagnostic else "")
                ) from exc
        if not isinstance(worker, dict) or worker.get("schema") != WORKER_SCHEMA:
            raise WorkspaceViolation("WSL2 research sandbox returned invalid worker schema")

        stdout, stdout_truncated = _bounded_text(worker.get("stdout"))
        stderr, stderr_truncated = _bounded_text(worker.get("stderr"))
        after = _snapshot(root)
        status = str(worker.get("status") or "FAILED")
        if status not in {"COMPLETED", "FAILED", "TIMEOUT"}:
            status = "FAILED"
        return {
            "schema": SANDBOX_SCHEMA,
            "sandbox_mode": SANDBOX_MODE,
            "status": status,
            "returncode": int(worker.get("returncode", 1)),
            "elapsed_ms": elapsed_ms,
            "stdout": stdout,
            "stderr": stderr,
            "output_truncated": stdout_truncated or stderr_truncated,
            "resource_usage": worker.get("resource_usage")
            if isinstance(worker.get("resource_usage"), dict)
            else {},
            "generated_artifacts": _artifact_delta(before, after),
            "failure_reason": worker.get("failure_reason"),
            "controls": {
                "user_namespace": False,
                "mount_namespace": True,
                "pid_namespace": True,
                "network_namespace": True,
                "chroot": True,
                "execution_uid": 65534,
                "dropped_capabilities": True,
                "no_new_privileges": True,
                "seccomp": True,
                "resource_limits": True,
            },
        }
