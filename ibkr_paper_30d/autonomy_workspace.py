"""Persistent model-controlled autonomy workspace (AUTONOMY_EPOCH_1).

Design rulings encoded here:

1. The workspace is a capability, not a methodology. The host never tells
   the model WHAT to remember; it only guarantees persistence and
   auditability.
2. Structural isolation: all workspace writes resolve strictly inside the
   workspace root. Model-created code may only live under ``tools/`` and is
   delegated to an OS-enforced research sandbox. There is no Owner-context
   execution fallback.
3. Every artifact creation is recorded in an append-only registry with
   content hashes so later cycles/audits can reconstruct what code was
   used, when, and by which cycle.
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

from .canonical import canonical_bytes, sha256_json
from .types import new_uuid7


WORKSPACE_SCHEMA_V1 = "AUTONOMY_WORKSPACE_EVENT_V1"
WORKSPACE_SCHEMA = "AUTONOMY_WORKSPACE_EVENT_V2"
ARTIFACT_SCHEMA = "AUTONOMY_WORKSPACE_ARTIFACT_V2"
RUN_SCHEMA = "AUTONOMY_WORKSPACE_SCRIPT_RUN_V1"

WORKSPACE_SUBDIRS = ("memory", "research", "tools", "datasets", "experiments")
MAX_ARTIFACT_BYTES = 5 * 1024 * 1024
MAX_SCRIPT_OUTPUT_BYTES = 512 * 1024
DEFAULT_SCRIPT_TIMEOUT_SECONDS = 60.0
MAX_SCRIPT_TIMEOUT_SECONDS = 300.0

FORBIDDEN_ARTIFACT_NAME_CHARS = ("..", ":", "%", "\x00")
MAX_SUMMARY_ARTIFACTS = 100
_REGISTRY_LOCK = threading.RLock()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class WorkspaceViolation(PermissionError):
    pass


class ResearchSandbox(Protocol):
    def run(
        self,
        *,
        workspace_root: Path,
        script_relative: str,
        arguments: tuple[str, ...],
        timeout_seconds: float,
    ) -> dict[str, Any]: ...


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
    be written into ``tools/``. Script execution requires an injected secure
    sandbox and never falls back to an Owner-context subprocess.
    """

    def __init__(
        self,
        root: str | Path,
        *,
        sandbox: ResearchSandbox | None = None,
    ) -> None:
        self.paths = WorkspacePaths(root=Path(root))
        self.sandbox = sandbox
        self.paths.root.mkdir(parents=True, exist_ok=True)
        for subdirectory in WORKSPACE_SUBDIRS:
            (self.paths.root / subdirectory).mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # registry (append-only, hash-chained)
    # ------------------------------------------------------------------

    def _append_line(self, line: bytes) -> None:
        descriptor = os.open(
            self.paths.registry_path,
            os.O_APPEND | os.O_CREAT | os.O_WRONLY | getattr(os, "O_BINARY", 0),
            0o600,
        )
        try:
            written = os.write(descriptor, line)
            if written != len(line):
                raise WorkspaceViolation("workspace registry append was incomplete")
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

    def _append_v2_record(
        self,
        event: dict[str, Any],
        *,
        sequence: int,
        previous_record_sha256: str | None,
    ) -> dict[str, Any]:
        unsigned = {
            "schema": WORKSPACE_SCHEMA,
            "sequence": sequence,
            "previous_record_sha256": previous_record_sha256,
            "event_id": f"ws-{new_uuid7()}",
            "created_at_utc": _utc_now(),
            "event": event,
        }
        record = {**unsigned, "record_sha256": sha256_json(unsigned)}
        self._append_line(canonical_bytes(record) + b"\n")
        return record

    def _append_registry(self, event: dict[str, Any]) -> None:
        if not isinstance(event, dict) or not event.get("event_type"):
            raise WorkspaceViolation("workspace registry event is invalid")
        with _REGISTRY_LOCK:
            records, legacy_bytes = self._validated_registry()
            v2_records = [item for item in records if item["schema"] == WORKSPACE_SCHEMA]
            if legacy_bytes and not v2_records:
                anchor = self._append_v2_record(
                    {
                        "event_type": "V1_MIGRATION_ANCHOR",
                        "legacy_registry_sha256": hashlib.sha256(legacy_bytes).hexdigest(),
                        "legacy_record_count": len(records),
                    },
                    sequence=1,
                    previous_record_sha256=None,
                )
                v2_records.append(anchor)
            sequence = len(v2_records) + 1
            previous = v2_records[-1]["record_sha256"] if v2_records else None
            self._append_v2_record(
                event,
                sequence=sequence,
                previous_record_sha256=previous,
            )

    def _validated_registry(self) -> tuple[list[dict[str, Any]], bytes]:
        if not self.paths.registry_path.exists():
            return [], b""
        raw = self.paths.registry_path.read_bytes()
        if not raw:
            return [], b""
        if not raw.endswith(b"\n"):
            raise WorkspaceViolation("workspace registry has a truncated tail")

        records: list[dict[str, Any]] = []
        legacy_lines: list[bytes] = []
        seen_v2 = False
        expected_sequence = 1
        previous: str | None = None
        for line_number, line in enumerate(raw.splitlines(keepends=True), start=1):
            try:
                record = json.loads(line)
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise WorkspaceViolation(
                    f"workspace registry line {line_number} is malformed"
                ) from exc
            if not isinstance(record, dict) or not isinstance(record.get("event"), dict):
                raise WorkspaceViolation(
                    f"workspace registry line {line_number} is not an event object"
                )
            schema = record.get("schema")
            if schema == WORKSPACE_SCHEMA_V1:
                if seen_v2:
                    raise WorkspaceViolation("workspace registry contains V1 after V2")
                legacy_lines.append(line)
            elif schema == WORKSPACE_SCHEMA:
                seen_v2 = True
                if record.get("sequence") != expected_sequence:
                    raise WorkspaceViolation("workspace registry sequence is invalid")
                if record.get("previous_record_sha256") != previous:
                    raise WorkspaceViolation("workspace registry hash link is invalid")
                claimed = record.get("record_sha256")
                unsigned = {
                    key: value for key, value in record.items() if key != "record_sha256"
                }
                if not isinstance(claimed, str) or claimed != sha256_json(unsigned):
                    raise WorkspaceViolation("workspace registry record hash is invalid")
                if expected_sequence == 1 and legacy_lines:
                    event = record["event"]
                    legacy_bytes = b"".join(legacy_lines)
                    if (
                        event.get("event_type") != "V1_MIGRATION_ANCHOR"
                        or event.get("legacy_record_count") != len(legacy_lines)
                        or event.get("legacy_registry_sha256")
                        != hashlib.sha256(legacy_bytes).hexdigest()
                    ):
                        raise WorkspaceViolation("workspace registry V1 migration anchor is invalid")
                previous = claimed
                expected_sequence += 1
            else:
                raise WorkspaceViolation(
                    f"workspace registry line {line_number} has unknown schema"
                )
            records.append(record)
        return records, b"".join(legacy_lines)

    def _registry_events(self) -> list[dict[str, Any]]:
        records, _ = self._validated_registry()
        return records

    # ------------------------------------------------------------------
    # artifacts
    # ------------------------------------------------------------------

    def list_artifacts(self) -> list[dict[str, Any]]:
        return list(self._active_artifacts(verify_content=True).values())

    def _active_artifacts(self, *, verify_content: bool) -> dict[str, dict[str, Any]]:
        artifacts: dict[str, dict[str, Any]] = {}
        for record in self._registry_events():
            event = record.get("event") or {}
            event_type = event.get("event_type")
            if event_type == "ARTIFACT_CREATED":
                artifact = self._validate_artifact_metadata(event.get("artifact"))
                artifacts.pop(artifact["path"], None)
                artifacts[artifact["path"]] = artifact
            elif event_type == "ARTIFACT_WRITTEN":
                artifact = self._validate_artifact_metadata(event.get("artifact"))
                path = artifact["path"]
                operation = event.get("operation")
                if operation == "CREATE" and path in artifacts:
                    raise WorkspaceViolation(f"duplicate active artifact: {path}")
                if operation == "UPDATE" and path not in artifacts:
                    raise WorkspaceViolation(f"artifact update has no active predecessor: {path}")
                if operation not in {"CREATE", "UPDATE"}:
                    raise WorkspaceViolation("workspace artifact operation is invalid")
                artifacts.pop(path, None)
                artifacts[path] = artifact
            elif event_type == "ARTIFACT_DELETED":
                path = str(event.get("path") or "")
                if record.get("schema") == WORKSPACE_SCHEMA and path not in artifacts:
                    raise WorkspaceViolation(f"artifact delete has no active predecessor: {path}")
                artifacts.pop(path, None)
        if verify_content:
            for artifact in artifacts.values():
                self._verify_artifact_content(artifact)
        return artifacts

    def _validate_artifact_metadata(self, value: Any) -> dict[str, Any]:
        if not isinstance(value, dict):
            raise WorkspaceViolation("workspace artifact metadata is invalid")
        path = value.get("path")
        digest = value.get("sha256")
        size = value.get("size_bytes")
        if (
            not isinstance(path, str)
            or not isinstance(digest, str)
            or len(digest) != 64
            or not isinstance(size, int)
            or size < 0
        ):
            raise WorkspaceViolation("workspace artifact metadata is incomplete")
        _validate_relative_path(path)
        return dict(value)

    def _verify_artifact_content(self, artifact: dict[str, Any]) -> Path:
        path = artifact["path"]
        target = self._resolve(path, must_exist=True)
        if not target.is_file():
            raise WorkspaceViolation(f"workspace artifact is not a regular file: {path}")
        content = target.read_bytes()
        if len(content) != artifact["size_bytes"]:
            raise WorkspaceViolation(f"workspace artifact size mismatch: {path}")
        if hashlib.sha256(content).hexdigest() != artifact["sha256"]:
            raise WorkspaceViolation(f"workspace artifact content hash mismatch: {path}")
        return target

    def read_artifact(self, relative: str) -> dict[str, Any]:
        canonical = _validate_relative_path(relative).as_posix()
        artifacts = self._active_artifacts(verify_content=True)
        if canonical not in artifacts:
            raise WorkspaceViolation(f"workspace artifact is not active: {canonical}")
        target = self._verify_artifact_content(artifacts[canonical])
        encoded = target.read_bytes()
        content = encoded.decode("utf-8", errors="replace")
        return {
            "path": canonical,
            "content": content,
            "sha256": hashlib.sha256(encoded).hexdigest(),
            "size_bytes": len(encoded),
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
        active = self._active_artifacts(verify_content=True)
        canonical_path = str(target.relative_to(self.paths.root)).replace("\\", "/")
        if target.exists() and canonical_path not in active:
            raise WorkspaceViolation(
                f"workspace path exists without active registry authority: {canonical_path}"
            )
        operation = "UPDATE" if canonical_path in active else "CREATE"
        target.parent.mkdir(parents=True, exist_ok=True)
        artifact = {
            "schema": ARTIFACT_SCHEMA,
            "artifact_id": f"art-{new_uuid7()}",
            "path": canonical_path,
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
            {
                "event_type": "ARTIFACT_WRITTEN",
                "operation": operation,
                "artifact": artifact,
            }
        )
        return artifact

    def delete_artifact(self, relative: str, *, cycle_id: str = "") -> dict[str, Any]:
        canonical = _validate_relative_path(relative).as_posix()
        active = self._active_artifacts(verify_content=True)
        if canonical not in active:
            raise WorkspaceViolation(f"workspace artifact is not active: {canonical}")
        target = self._verify_artifact_content(active[canonical])
        if self.paths.registry_path == target:
            raise WorkspaceViolation("the workspace registry cannot be deleted")
        target.unlink()
        self._append_registry(
            {
                "event_type": "ARTIFACT_DELETED",
                "operation": "DELETE",
                "path": canonical,
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
        if self.sandbox is None:
            raise WorkspaceViolation("secure research sandbox unavailable")
        active_before = self._active_artifacts(verify_content=True)
        script_sha256 = hashlib.sha256(target.read_bytes()).hexdigest()
        receipt = self.sandbox.run(
            workspace_root=self.paths.root.resolve(),
            script_relative=str(target.relative_to(self.paths.root)).replace(
                "\\", "/"
            ),
            arguments=tuple(str(item) for item in (arguments or ())),
            timeout_seconds=timeout,
        )
        if not isinstance(receipt, dict):
            raise WorkspaceViolation("secure research sandbox returned invalid receipt")
        status = str(receipt.get("status") or "FAILED")
        stdout = str(receipt.get("stdout") or "")
        stderr = str(receipt.get("stderr") or "")
        run = {
            "schema": RUN_SCHEMA,
            "run_id": f"run-{new_uuid7()}",
            "script_path": str(target.relative_to(self.paths.root)).replace("\\", "/"),
            "script_sha256": script_sha256,
            "cycle_id": cycle_id,
            "status": status,
            "returncode": receipt.get("returncode"),
            "elapsed_ms": int(receipt.get("elapsed_ms") or 0),
            "stdout_sha256": hashlib.sha256(stdout.encode("utf-8")).hexdigest(),
            "stderr_sha256": hashlib.sha256(stderr.encode("utf-8")).hexdigest(),
            "stdout": stdout[:MAX_SCRIPT_OUTPUT_BYTES],
            "stderr": stderr[:MAX_SCRIPT_OUTPUT_BYTES],
            "resource_usage": receipt.get("resource_usage") or {},
            "generated_artifacts": receipt.get("generated_artifacts") or [],
            "failure_reason": receipt.get("failure_reason"),
            "ran_at_utc": _utc_now(),
        }
        self._record_sandbox_artifacts(
            receipt.get("generated_artifacts") or [],
            active_before=active_before,
            cycle_id=cycle_id,
        )
        self._append_registry(
            {"event_type": "SCRIPT_RUN", "run": _run_without_large_output(run)}
        )
        return run

    def _record_sandbox_artifacts(
        self,
        changes: Any,
        *,
        active_before: dict[str, dict[str, Any]],
        cycle_id: str,
    ) -> None:
        if not isinstance(changes, list):
            raise WorkspaceViolation("sandbox artifact receipt is invalid")
        active_paths = set(active_before)
        for change in changes:
            if not isinstance(change, dict):
                raise WorkspaceViolation("sandbox artifact change is invalid")
            path = str(change.get("path") or "")
            operation = change.get("operation")
            _validate_relative_path(path)
            if operation == "DELETED":
                if path in active_paths:
                    self._append_registry(
                        {
                            "event_type": "ARTIFACT_DELETED",
                            "operation": "DELETE",
                            "path": path,
                            "deleted_by_cycle": cycle_id,
                            "deleted_at_utc": _utc_now(),
                        }
                    )
                    active_paths.remove(path)
                continue
            if change.get("kind") != "file":
                continue
            target = self._resolve(path, must_exist=True)
            content = target.read_bytes()
            digest = hashlib.sha256(content).hexdigest()
            if digest != change.get("sha256") or len(content) != change.get("size_bytes"):
                raise WorkspaceViolation("sandbox artifact receipt hash mismatch")
            registry_operation = "UPDATE" if path in active_paths else "CREATE"
            artifact = {
                "schema": ARTIFACT_SCHEMA,
                "artifact_id": f"art-{new_uuid7()}",
                "path": path,
                "sha256": digest,
                "size_bytes": len(content),
                "created_by_cycle": cycle_id,
                "created_at_utc": _utc_now(),
            }
            self._append_registry(
                {
                    "event_type": "ARTIFACT_WRITTEN",
                    "operation": registry_operation,
                    "source": "RESEARCH_SANDBOX",
                    "artifact": artifact,
                }
            )
            active_paths.add(path)

    # ------------------------------------------------------------------
    # workspace summary for prompt context (model-controlled content)
    # ------------------------------------------------------------------

    def summary(self, *, max_artifacts: int = 40) -> dict[str, Any]:
        if not isinstance(max_artifacts, int) or not 1 <= max_artifacts <= MAX_SUMMARY_ARTIFACTS:
            raise WorkspaceViolation("workspace summary bound is invalid")
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
