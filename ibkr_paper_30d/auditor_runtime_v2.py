from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable, Mapping, Sequence

from .canonical import sha256_json


RUNTIME_MANIFEST_NAME = "AUDITOR_RUNTIME_MANIFEST_V2.json"
RUNTIME_PAYLOAD_ALLOWLIST = (
    "AUDITOR_DENIAL_PROBE_V1.ps1",
    "AUDITOR_GATE_V2_PROBE.ps1",
    "CODEX_DECISION_AUDITOR_V1.ps1",
)
_RUNTIME_SCHEMA = "AUDITOR_RUNTIME_MANIFEST_V2"
_DEPLOYMENT_SCHEMA = "AUDITOR_RUNTIME_DEPLOYMENT_MANIFEST_V2"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_TARGET_NAMES = (
    "SECRETS_READ",
    "IBKR_SECRET_READ",
    "SMTP_SECRET_READ",
    "EXECUTION_LOCK_ACCESS",
    "LIVE_DATABASE_MUTATION",
    "BROKER_WRITE_PATH_ACCESS",
    "TRADER_CONTEXT_ACCESS",
    "AUDIT_INPUT_MUTATION",
    "IMMUTABLE_EXPORT_READ",
    "AUDITOR_REPORT_WRITE",
)


@dataclass(frozen=True)
class RuntimeIntegrityResult:
    status: str
    reason_codes: tuple[str, ...]
    runtime_manifest_sha256: str | None = None
    deployment_manifest_sha256: str | None = None

    @classmethod
    def block(cls, *reasons: str) -> "RuntimeIntegrityResult":
        return cls("BLOCK", tuple(dict.fromkeys(reasons)))


@dataclass(frozen=True)
class RuntimeCapabilityAssessment:
    status: str
    predicates: Mapping[str, bool]
    reason_codes: tuple[str, ...]


_STRUCTURAL_PATTERNS = {
    "BROKER_MODULE_AVAILABLE": (
        "ibapi",
        "ib_insync",
        "eclientsocket",
        "ewrapper",
        "twsapi",
    ),
    "ORDER_WRITE_SYMBOL_AVAILABLE": (
        "placeorder",
        "cancelorder",
        "reqglobalcancel",
        "modifyorder",
    ),
    "EXECUTION_ADAPTER_AVAILABLE": (
        "ibkr_paper_30d.broker",
        "executionadapter",
        "execution adapter",
    ),
    "EXECUTION_LOCK_CLIENT_AVAILABLE": (
        "acquire-executionlock",
        "execution_lock",
        "executionlockclient",
    ),
    "TRADER_IPC_CLIENT_AVAILABLE": (
        "namedpipeclientstream",
        "trader_invocation",
        "traderipcclient",
    ),
    "BROKER_CREDENTIAL_SOURCE_AVAILABLE": (
        "ibkr_password",
        "ibkr_username",
        "brokercredential",
        "broker credential",
    ),
}
_GENERIC_PROCESS_SYMBOLS = {
    "start-process",
    "invoke-expression",
    "add-type",
    "powershell.exe",
    "pwsh.exe",
    "python.exe",
    "python3.exe",
    "system.diagnostics.process",
}
_GENERIC_NETWORK_SYMBOLS = {
    "invoke-webrequest",
    "invoke-restmethod",
    "system.net.http.httpclient",
    "net.http.httpclient",
    "system.net.webclient",
    "net.webclient",
    "system.net.sockets.socket",
    "net.sockets.socket",
}
_AST_SCANNER = r"""
$rows = @()
$inputDocument = $env:CODEX_AUDITOR_AST_PATHS | ConvertFrom-Json
foreach ($path in @($inputDocument.paths)) {
    $tokens = $null
    $errors = $null
    $ast = [System.Management.Automation.Language.Parser]::ParseFile(
        $path, [ref]$tokens, [ref]$errors
    )
    $commands = @($ast.FindAll({
        param($node) $node -is [System.Management.Automation.Language.CommandAst]
    }, $true) | ForEach-Object { $_.GetCommandName() } | Where-Object { $null -ne $_ })
    $types = @($ast.FindAll({
        param($node) $node -is [System.Management.Automation.Language.TypeExpressionAst]
    }, $true) | ForEach-Object { $_.TypeName.FullName })
    $members = @($ast.FindAll({
        param($node) $node -is [System.Management.Automation.Language.MemberExpressionAst]
    }, $true) | ForEach-Object { $_.Member.Value })
    $strings = @($ast.FindAll({
        param($node) $node -is [System.Management.Automation.Language.StringConstantExpressionAst]
    }, $true) | ForEach-Object { $_.Value })
    $variables = @($ast.FindAll({
        param($node) $node -is [System.Management.Automation.Language.VariableExpressionAst]
    }, $true) | ForEach-Object { $_.VariablePath.UserPath })
    $rows += [ordered]@{
        path = $path
        errors = @($errors | ForEach-Object { $_.Message })
        commands = $commands
        types = $types
        members = $members
        strings = $strings
        variables = $variables
    }
}
ConvertTo-Json -InputObject @($rows) -Depth 5 -Compress
"""


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _validate_name(name: object) -> str:
    if not isinstance(name, str) or not name:
        raise ValueError("RUNTIME_NAME_INVALID")
    if Path(name).name != name or "/" in name or "\\" in name:
        raise ValueError("RUNTIME_PATH_SEPARATOR")
    return name


def _assert_no_case_collisions(names: Iterable[str]) -> None:
    seen: set[str] = set()
    for name in names:
        folded = name.casefold()
        if folded in seen:
            raise ValueError("RUNTIME_CASE_COLLISION")
        seen.add(folded)


def _manifest_with_hash(body: dict[str, object]) -> dict[str, object]:
    return {**body, "manifest_sha256": sha256_json(body)}


def build_runtime_manifest_v2(
    runtime_root: Path | str, payload_names: Sequence[str]
) -> dict[str, object]:
    root = Path(runtime_root)
    names = tuple(_validate_name(name) for name in payload_names)
    _assert_no_case_collisions(names)
    if set(names) != set(RUNTIME_PAYLOAD_ALLOWLIST) or len(names) != len(
        RUNTIME_PAYLOAD_ALLOWLIST
    ):
        raise ValueError("RUNTIME_PAYLOAD_ALLOWLIST_MISMATCH")
    files = {name: _file_sha256(root / name) for name in sorted(names)}
    return _manifest_with_hash(
        {
            "schema": _RUNTIME_SCHEMA,
            "files": files,
        }
    )


def build_deployment_manifest_v2(
    runtime_manifest_path: Path | str, payload_paths: Iterable[Path | str]
) -> dict[str, object]:
    manifest_path = Path(runtime_manifest_path)
    paths = tuple(Path(path) for path in payload_paths)
    names = tuple(path.name for path in paths)
    _assert_no_case_collisions((*names, manifest_path.name))
    if set(names) != set(RUNTIME_PAYLOAD_ALLOWLIST):
        raise ValueError("RUNTIME_PAYLOAD_ALLOWLIST_MISMATCH")
    if manifest_path.name != RUNTIME_MANIFEST_NAME:
        raise ValueError("RUNTIME_MANIFEST_NAME_INVALID")
    files = {path.name: _file_sha256(path) for path in paths}
    files[manifest_path.name] = _file_sha256(manifest_path)
    return _manifest_with_hash(
        {
            "schema": _DEPLOYMENT_SCHEMA,
            "files": {name: files[name] for name in sorted(files)},
        }
    )


def _strict_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    seen: set[str] = set()
    for key, value in pairs:
        folded = key.casefold()
        if folded in seen:
            raise ValueError("MANIFEST_DUPLICATE_KEY")
        seen.add(folded)
        result[key] = value
    return result


def _is_reparse(path: Path) -> bool:
    if path.is_symlink():
        return True
    try:
        return bool(path.stat(follow_symlinks=False).st_file_attributes & 0x400)
    except AttributeError:
        return False


def _validate_manifest(
    manifest: object, schema: str, expected_names: set[str]
) -> tuple[dict[str, str], str]:
    if not isinstance(manifest, dict) or set(manifest) != {
        "schema",
        "files",
        "manifest_sha256",
    }:
        raise ValueError("MANIFEST_SCHEMA_INVALID")
    if manifest["schema"] != schema or not isinstance(manifest["files"], dict):
        raise ValueError("MANIFEST_SCHEMA_INVALID")
    files = manifest["files"]
    names = list(files)
    _assert_no_case_collisions(names)
    for name in names:
        _validate_name(name)
    if set(names) != expected_names:
        raise ValueError("MANIFEST_FILESET_MISMATCH")
    if any(
        not isinstance(digest, str) or not _SHA256_RE.fullmatch(digest)
        for digest in files.values()
    ):
        raise ValueError("MANIFEST_HASH_INVALID")
    claimed = manifest["manifest_sha256"]
    if not isinstance(claimed, str) or not _SHA256_RE.fullmatch(claimed):
        raise ValueError("MANIFEST_HASH_INVALID")
    body = {"schema": manifest["schema"], "files": files}
    if sha256_json(body) != claimed:
        raise ValueError("MANIFEST_SELF_HASH_MISMATCH")
    return files, claimed


def verify_runtime_fileset_v2(
    runtime_root: Path | str, deployment_manifest: Mapping[str, object]
) -> RuntimeIntegrityResult:
    root = Path(runtime_root)
    expected = set(RUNTIME_PAYLOAD_ALLOWLIST) | {RUNTIME_MANIFEST_NAME}
    try:
        if not root.is_dir() or _is_reparse(root):
            return RuntimeIntegrityResult.block("RUNTIME_PATH_REDIRECTED")
        entries = list(root.iterdir())
        if any(not entry.is_file() or _is_reparse(entry) for entry in entries):
            return RuntimeIntegrityResult.block("RUNTIME_FILESET_MISMATCH")
        actual_names = [entry.name for entry in entries]
        _assert_no_case_collisions(actual_names)
        if set(actual_names) != expected or len(actual_names) != len(expected):
            return RuntimeIntegrityResult.block("RUNTIME_FILESET_MISMATCH")

        deployment_files, deployment_self_hash = _validate_manifest(
            dict(deployment_manifest), _DEPLOYMENT_SCHEMA, expected
        )
        for name, digest in deployment_files.items():
            if _file_sha256(root / name) != digest:
                return RuntimeIntegrityResult.block("DEPLOYMENT_HASH_MISMATCH")

        raw_manifest = (root / RUNTIME_MANIFEST_NAME).read_text(encoding="utf-8")
        runtime_manifest = json.loads(raw_manifest, object_pairs_hook=_strict_object)
        runtime_files, _ = _validate_manifest(
            runtime_manifest, _RUNTIME_SCHEMA, set(RUNTIME_PAYLOAD_ALLOWLIST)
        )
        for name, digest in runtime_files.items():
            if _file_sha256(root / name) != digest:
                return RuntimeIntegrityResult.block("RUNTIME_HASH_MISMATCH")
    except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
        return RuntimeIntegrityResult.block(str(exc) or "RUNTIME_VERIFICATION_FAILED")

    return RuntimeIntegrityResult(
        status="PASS",
        reason_codes=(),
        runtime_manifest_sha256=_file_sha256(root / RUNTIME_MANIFEST_NAME),
        deployment_manifest_sha256=deployment_self_hash,
    )


def _narrow_tcp_classifier_allowed(path: Path, source: str) -> bool:
    if path.name != "AUDITOR_DENIAL_PROBE_V1.ps1":
        return False
    required = (
        "function Test-TcpEndpoint",
        "127.0.0.1",
        "::1",
    )
    compact = re.sub(r"\s+", "", source)
    return all(fragment in source for fragment in required) and (
        "ValidateRange(1,65535)" in compact
    )


def _fixed_child_orchestrator_allowed(path: Path, source: str) -> bool:
    if path.name != "AUDITOR_GATE_V2_PROBE.ps1":
        return False
    header = source.split(")", 1)[0]
    return (
        '"AUDITOR_DENIAL_PROBE_V1.ps1"' in source
        and '"CODEX_DECISION_AUDITOR_V1.ps1"' in source
        and "ScriptPath" not in header
        and "ExecutablePath" not in header
    )


def assess_runtime_capabilities(
    runtime_root: Path | str,
) -> RuntimeCapabilityAssessment:
    root = Path(runtime_root)
    paths = [root / name for name in RUNTIME_PAYLOAD_ALLOWLIST]
    predicates = {name: False for name in _STRUCTURAL_PATTERNS}
    predicates["ORDER_WRITE_MODULE_AVAILABLE"] = False
    reasons: list[str] = []
    try:
        if any(not path.is_file() or _is_reparse(path) for path in paths):
            raise ValueError("RUNTIME_FILESET_NOT_VERIFIED")
        command = [
            "powershell.exe",
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            _AST_SCANNER,
        ]
        environment = os.environ.copy()
        environment["CODEX_AUDITOR_AST_PATHS"] = json.dumps(
            {"paths": [str(path.resolve()) for path in paths]}
        )
        completed = subprocess.run(  # noqa: S603 - fixed executable and script
            command,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="strict",
            timeout=30,
            env=environment,
        )
        if completed.returncode != 0:
            raise ValueError("POWERSHELL_AST_UNAVAILABLE")
        rows = json.loads(completed.stdout)
        if isinstance(rows, dict):
            rows = [rows]
        if not isinstance(rows, list) or len(rows) != len(paths):
            raise ValueError("POWERSHELL_AST_OUTPUT_INVALID")
        for path, row in zip(paths, rows, strict=True):
            if not isinstance(row, dict) or row.get("errors"):
                reasons.append("POWERSHELL_AST_PARSE_ERROR")
                continue
            values: set[str] = set()
            for key in ("commands", "types", "members", "strings", "variables"):
                items = row.get(key, [])
                if not isinstance(items, list):
                    reasons.append("POWERSHELL_AST_OUTPUT_INVALID")
                    continue
                values.update(str(item).casefold() for item in items if item is not None)
            values.difference_update(
                name.casefold()
                for name in (
                    *_STRUCTURAL_PATTERNS,
                    "ORDER_WRITE_MODULE_AVAILABLE",
                    *_TARGET_NAMES,
                )
            )
            symbols = "\n".join(sorted(values))
            for predicate, patterns in _STRUCTURAL_PATTERNS.items():
                if any(pattern in symbols for pattern in patterns):
                    predicates[predicate] = True
            process_symbols = values & _GENERIC_PROCESS_SYMBOLS
            if process_symbols:
                source = path.read_text(encoding="utf-8")
                if process_symbols != {"powershell.exe"} or not (
                    _fixed_child_orchestrator_allowed(path, source)
                ):
                    reasons.append("GENERIC_PROCESS_HELPER_AVAILABLE")
            if values & _GENERIC_NETWORK_SYMBOLS:
                reasons.append("GENERIC_NETWORK_HELPER_AVAILABLE")
            tcp_present = any("tcpclient" in value for value in values)
            if tcp_present:
                source = path.read_text(encoding="utf-8")
                if not _narrow_tcp_classifier_allowed(path, source):
                    reasons.append("GENERIC_NETWORK_HELPER_AVAILABLE")
            if "import-module" in values:
                reasons.append("BROAD_MODULE_IMPORT_AVAILABLE")
    except (
        OSError,
        UnicodeError,
        ValueError,
        json.JSONDecodeError,
        subprocess.SubprocessError,
    ) as exc:
        reasons.append(str(exc) or "RUNTIME_CAPABILITY_SCAN_FAILED")

    predicates["ORDER_WRITE_MODULE_AVAILABLE"] = any(
        predicates[name]
        for name in (
            "BROKER_MODULE_AVAILABLE",
            "ORDER_WRITE_SYMBOL_AVAILABLE",
            "EXECUTION_ADAPTER_AVAILABLE",
        )
    )
    reasons.extend(name for name, present in predicates.items() if present)
    unique_reasons = tuple(dict.fromkeys(reasons))
    return RuntimeCapabilityAssessment(
        status="BLOCK" if unique_reasons else "PASS",
        predicates=predicates,
        reason_codes=unique_reasons,
    )


def _utc_text(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("CONSOLIDATED_TIMESTAMP_NOT_UTC")
    return value.isoformat().replace("+00:00", "Z")


def consolidate_probe_results_v2(
    *,
    run_id: str,
    started_at: datetime,
    completed_at: datetime,
    identity: Mapping[str, object],
    runtime: Mapping[str, object],
    denial: Mapping[str, object],
    functional: Mapping[str, object],
    paper: Mapping[str, object],
    output: Mapping[str, object],
) -> dict[str, object]:
    if not run_id or completed_at < started_at:
        raise ValueError("CONSOLIDATED_RUN_INVALID")
    if (
        runtime.get("status") != "PASS"
        or denial.get("status") != "COMPLETE"
        or functional.get("status") != "PASS"
    ):
        raise ValueError("CONSOLIDATED_CHILD_FAILURE")
    rows = denial.get("target_validation_matrix")
    outcomes = denial.get("results")
    if not isinstance(rows, list) or not isinstance(outcomes, Mapping):
        raise ValueError("CONSOLIDATED_CHILD_FAILURE")
    row_names = [row.get("probe") for row in rows if isinstance(row, Mapping)]
    if (
        len(rows) != len(_TARGET_NAMES)
        or set(row_names) != set(_TARGET_NAMES)
        or set(outcomes) != set(_TARGET_NAMES)
        or any(row.get("run_id") != run_id for row in rows)
        or denial.get("run_id") != run_id
        or functional.get("run_id") != run_id
        or paper.get("run_id") != run_id
        or output.get("run_id") != run_id
    ):
        raise ValueError("CONSOLIDATED_MIXED_OR_PARTIAL_RUN")
    endpoints = denial.get("network_endpoints")
    if not isinstance(endpoints, Mapping):
        raise ValueError("CONSOLIDATED_CHILD_FAILURE")
    reachable = "CONNECTED" in endpoints.values()
    if not reachable:
        raise ValueError("CONSOLIDATED_NETWORK_FACT_MISMATCH")
    return {
        "schema": "AUDITOR_GATE_V2_RECEIPT_V1",
        "gate_version": "V2",
        "run_id": run_id,
        "started_at_utc": _utc_text(started_at),
        "completed_at_utc": _utc_text(completed_at),
        "effective_sid": identity.get("effective_sid"),
        "token_elevated": identity.get("token_elevated"),
        "separate_process": identity.get("separate_process"),
        "runtime_integrity": dict(runtime),
        "target_validation_matrix": rows,
        "capability_outcomes": dict(outcomes),
        "functional_auditor": dict(functional),
        "paper_identity": dict(paper),
        "network_facts": {
            "AUDITOR_TECHNICAL_SOCKET_REACHABILITY": True,
            "AUDITOR_NETWORK_ISOLATION_REQUIRED": False,
            "AUDITOR_UNAUTHORIZED_RAW_API_PATH_POSSIBLE": True,
            "AUDITOR_COMPROMISE_CONTAINMENT_NOT_CLAIMED": True,
            "endpoints": dict(endpoints),
        },
        "output": dict(output),
    }
