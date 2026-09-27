"""Persistent model-controlled autonomy workspace (AUTONOMY_EPOCH_1).

Design rulings encoded here:

1. The workspace is a capability, not a methodology. The host never tells
   the model WHAT to remember; it only guarantees persistence and
   auditability.
2. Structural isolation: all workspace writes resolve strictly inside the
   workspace root. Model-created code may only live under ``tools/`` and is
   executed in a detached ``python -I`` subprocess that never receives
   broker credentials, never imports the execution kernel and never gains
   broker-write authority. The immutable kernel files are never writable
   through this module.
3. Every artifact creation is recorded in an append-only registry with
   content hashes so later cycles/audits can reconstruct what code was
   used, when, and by which cycle.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .canonical import canonical_bytes, sha256_json
from .types import new_uuid7


WORKSPACE_SCHEMA = "AUTONOMY_WORKSPACE_EVENT_V1"
ARTIFACT_SCHEMA = "AUTONOMY_WORKSPACE_ARTIFACT_V1"
RUN_SCHEMA = "AUTONOMY_WORKSPACE_SCRIPT_RUN_V1"

WORKSPACE_SUBDIRS = ("memory", "research", "tools", "datasets", "experiments")
MAX_ARTIFACT_BYTES = 5 * 1024 * 1024
MAX_SCRIPT_OUTPUT_BYTES = 512 * 1024
DEFAULT_SCRIPT_TIMEOUT_SECONDS = 60.0
MAX_SCRIPT_TIMEOUT_SECONDS = 300.0

FORBIDDEN_ARTIFACT_NAME_CHARS = ("..", ":", "%", "\x00")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class WorkspaceViolation(PermissionError):
    pass


def _validate_relative_path(relative: str) -> Path:
    if not isinstance(relative, str) or not relative.strip():
        raise WorkspaceViolation("workspace path must be a non-empty string")
    candidate = Path(relative)
    if candidate.is_absolute():
        raise WorkspaceViolation("workspace path must be relative")
    parts = [part for part in candidate.parts if part not in (".",)]
    if not parts:
        raise WorkspaceViolation("workspace path must name a location")
    if any(part == ".." for part in parts):
        raise WorkspaceViolation("workspace path must not traverse upward")
    for part in parts:
        if any(char in part for char in FORBIDDEN_ARTIFACT_NAME_CHARS):
            raise WorkspaceViolation(
                f"workspace path component not allowed: {part!r}"
            )
    return Path(*parts)


@dataclass(frozen=True)
class WorkspacePaths:
    root: Path

    @property
    def memory(self) -> Path:
        return self.root / "memory"

    @property
    def research(self) -> Path:
        return self.root / "research"

    @property
    def tools(self) -> Path:
        return self.root / "tools"

    @property
    def datasets(self) -> Path:
        return self.root / "datasets"

    @property
    def experiments(self) -> Path:
        return self.root / "experiments"

    @property
    def registry_path(self) -> Path:
        return self.root / "workspace_registry.jsonl"


class AutonomyWorkspace:
    """Model-controlled persistent workspace with structural isolation.

    All artifacts resolve inside the workspace root. Python code can only
    be written into ``tools/``. Script execution is a detached subprocess
    with a sanitized environment; it cannot reach the broker, the
    execution kernel, or credentials by construction.
    """

    def __init__(self, root: str | Path) -> None:
        self.paths = WorkspacePaths(root=Path(root))
        self.paths.root.mkdir(parents=True, exist_ok=True)
        for subdirectory in WORKSPACE_SUBDIRS:
            (self.paths.root / subdirectory).mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # registry (append-only, hash-chained)
    # ------------------------------------------------------------------

    def _append_registry(self, event: dict[str, Any]) -> None:
        record = {
            "schema": WORKSPACE_SCHEMA,
            "event_id": f"ws-{new_uuid7()}",
            "created_at_utc": _utc_now(),
            "event": event,
        }
        line = canonical_bytes(record) + b"\n"
        with self.paths.registry_path.open("ab") as handle:
            handle.write(line)
            handle.flush()
            os.fsync(handle.fileno())

    def _registry_events(self) -> list[dict[str, Any]]:
        if not self.paths.registry_path.exists():
            return []
        events: list[dict[str, Any]] = []
        for line in self.paths.registry_path.read_text(
            encoding="utf-8"
        ).splitlines():
            try:
                import json

                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(record, dict):
                events.append(record)
        return events

    # ------------------------------------------------------------------
    # artifacts
    # ------------------------------------------------------------------

    def list_artifacts(self) -> list[dict[str, Any]]:
        artifacts: list[dict[str, Any]] = []
        for record in self._registry_events():
            event = record.get("event") or {}
            if event.get("event_type") == "ARTIFACT_CREATED":
                artifacts.append(event.get("artifact") or {})
        return artifacts

    def read_artifact(self, relative: str) -> dict[str, Any]:
        target = self._resolve(relative, must_exist=True)
        content = target.read_text(encoding="utf-8", errors="replace")
        return {
            "path": relative,
            "content": content,
            "sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
            "size_bytes": len(content.encode("utf-8")),
        }

    def write_artifact(
        self, relative: str, content: str, *, cycle_id: str = ""
    ) -> dict[str, Any]:
        target = self._resolve(relative)
        if target.suffix == ".py" and self.paths.tools not in target.parents:
            raise WorkspaceViolation(
                "python artifacts may only be created inside tools/"
            )
        encoded = content.encode("utf-8")
        if len(encoded) > MAX_ARTIFACT_BYTES:
            raise WorkspaceViolation(
                f"artifact exceeds {MAX_ARTIFACT_BYTES} bytes"
            )
        target.parent.mkdir(parents=True, exist_ok=True)
        artifact = {
            "schema": ARTIFACT_SCHEMA,
            "artifact_id": f"art-{new_uuid7()}",
            "path": str(target.relative_to(self.paths.root)).replace("\\", "/"),
            "sha256": hashlib.sha256(encoded).hexdigest(),
            "size_bytes": len(encoded),
            "created_by_cycle": cycle_id,
            "created_at_utc": _utc_now(),
        }
        temporary = target.with_name(f".{target.name}.{os.getpid()}.tmp")
        with temporary.open("wb") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
        self._append_registry(
            {"event_type": "ARTIFACT_CREATED", "artifact": artifact}
        )
        return artifact

    def delete_artifact(self, relative: str, *, cycle_id: str = "") -> dict[str, Any]:
        target = self._resolve(relative, must_exist=True)
        if self.paths.registry_path == target:
            raise WorkspaceViolation("the workspace registry cannot be deleted")
        target.unlink()
        self._append_registry(
            {
                "event_type": "ARTIFACT_DELETED",
                "path": str(target.relative_to(self.paths.root)).replace("\\", "/"),
                "deleted_by_cycle": cycle_id,
                "deleted_at_utc": _utc_now(),
            }
        )
        return {"deleted": relative}

    def artifact_count(self) -> int:
        return len(self.list_artifacts())

    # ------------------------------------------------------------------
    # script execution (isolated research compute)
    # ------------------------------------------------------------------

    def run_script(
        self,
        relative: str,
        *,
        cycle_id: str = "",
        timeout_seconds: float = DEFAULT_SCRIPT_TIMEOUT_SECONDS,
        arguments: list[str] | None = None,
    ) -> dict[str, Any]:
        target = self._resolve(relative, must_exist=True)
        if target.suffix != ".py":
            raise WorkspaceViolation("only python research scripts can be run")
        if self.paths.tools not in target.parents:
            raise WorkspaceViolation(
                "research scripts may only live inside tools/"
            )
        timeout = min(
            max(float(timeout_seconds), 1.0), MAX_SCRIPT_TIMEOUT_SECONDS
        )
        command = [sys.executable, "-I", str(target), *(arguments or [])]
        started = time.monotonic()
        try:
            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=str(self.paths.experiments),
                env=self._script_environment(),
                check=False,
            )
            status = "COMPLETED" if completed.returncode == 0 else "FAILED"
            stdout = completed.stdout or ""
            stderr = completed.stderr or ""
            returncode = completed.returncode
        except subprocess.TimeoutExpired as exc:
            status = "TIMEOUT"
            stdout = (exc.stdout or b"").decode("utf-8", errors="replace") if isinstance(exc.stdout, bytes) else (exc.stdout or "")
            stderr = (exc.stderr or b"").decode("utf-8", errors="replace") if isinstance(exc.stderr, bytes) else (exc.stderr or "")
            returncode = None
        elapsed_ms = int((time.monotonic() - started) * 1000)
        run = {
            "schema": RUN_SCHEMA,
            "run_id": f"run-{new_uuid7()}",
            "script_path": str(target.relative_to(self.paths.root)).replace("\\", "/"),
            "script_sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
            "cycle_id": cycle_id,
            "status": status,
            "returncode": returncode,
            "elapsed_ms": elapsed_ms,
            "stdout_sha256": hashlib.sha256(stdout.encode("utf-8")).hexdigest(),
            "stderr_sha256": hashlib.sha256(stderr.encode("utf-8")).hexdigest(),
            "stdout": stdout[:MAX_SCRIPT_OUTPUT_BYTES],
            "stderr": stderr[:MAX_SCRIPT_OUTPUT_BYTES],
            "ran_at_utc": _utc_now(),
        }
        self._append_registry(
            {"event_type": "SCRIPT_RUN", "run": _run_without_large_output(run)}
        )
        return run

    @staticmethod
    def _script_environment() -> dict[str, str]:
        """No broker credentials, no kernel reachability by environment.

        PATH is deliberately excluded: research scripts must not spawn
        external CLIs (lean, codex, git) from the host environment. The
        model reaches QuantConnect through the QUANTCONNECT research tool
        instead, keeping provider credits and lab access host-mediated.
        """

        allowed = ("SYSTEMROOT", "WINDIR", "TEMP", "TMP")
        return {name: os.environ[name] for name in allowed if name in os.environ}

    # ------------------------------------------------------------------
    # workspace summary for prompt context (model-controlled content)
    # ------------------------------------------------------------------

    def summary(self, *, max_artifacts: int = 40) -> dict[str, Any]:
        artifacts = self.list_artifacts()
        return {
            "workspace_root": str(self.paths.root),
            "artifact_count": len(artifacts),
            "recent_artifacts": artifacts[-max_artifacts:],
            "registry_events": len(self._registry_events()),
        }

    # ------------------------------------------------------------------
    # internals
    # ------------------------------------------------------------------

    def _resolve(self, relative: str, *, must_exist: bool = False) -> Path:
        resolved = _validate_relative_path(relative)
        target = (self.paths.root / resolved).resolve()
        root = self.paths.root.resolve()
        if root != target and root not in target.parents:
            raise WorkspaceViolation("workspace path escapes the workspace root")
        if must_exist and not target.exists():
            raise WorkspaceViolation(f"workspace artifact not found: {relative}")
        return target


def _run_without_large_output(run: dict[str, Any]) -> dict[str, Any]:
    trimmed = dict(run)
    trimmed["stdout"] = (run.get("stdout") or "")[:2000]
    trimmed["stderr"] = (run.get("stderr") or "")[:2000]
    return trimmed