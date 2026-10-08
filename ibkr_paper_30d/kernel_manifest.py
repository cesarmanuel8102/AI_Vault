"""Deterministic authority-closure manifest for the PAPER runtime."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import subprocess
from pathlib import Path, PurePosixPath
from typing import Any, Iterable

from .canonical import canonical_bytes, sha256_json


KERNEL_MANIFEST_SCHEMA = "IMMUTABLE_EXECUTION_KERNEL_MANIFEST_V2"

PYTHON_ROOT_ROLES: dict[str, str] = {
    "ibkr_paper_30d/autonomous_execution.py": "broker_write_dispatch",
    "ibkr_paper_30d/autonomous_runtime.py": "model_runtime_dispatch",
    "ibkr_paper_30d/autonomous_service.py": "continuous_service_authority",
    "ibkr_paper_30d/day1_launch.py": "launch_coordinator",
    "ibkr_paper_30d/execution_lock.py": "single_writer_lock",
    "ibkr_paper_30d/experiment_control.py": "clock_authorization_kill_switch",
    "ibkr_paper_30d/experiment_epoch.py": "epoch_authority",
    "ibkr_paper_30d/experiment_ledger.py": "capital_subledger",
    "ibkr_paper_30d/kill_switch_recovery.py": "kill_switch_recovery_authority",
    "ibkr_paper_30d/ibkr_readonly_session.py": "broker_session_boundary",
    "ibkr_paper_30d/kernel_manifest.py": "kernel_manifest_authority",
    "ibkr_paper_30d/market_data.py": "market_data_gate",
    "ibkr_paper_30d/market_policy.py": "market_data_policy",
    "ibkr_paper_30d/open_order_management.py": "order_lifecycle_authority",
    "ibkr_paper_30d/owner_authorization.py": "owner_authorization",
    "ibkr_paper_30d/persistence.py": "authoritative_storage",
    "ibkr_paper_30d/reconciliation.py": "broker_reconciliation",
    "ibkr_paper_30d/risk.py": "capital_risk_boundary",
    "ibkr_paper_30d/runtime_integrity.py": "runtime_auditor_market_gate",
    "ibkr_paper_30d/scheduler_validation.py": "scheduler_startup_gate",
    "ibkr_paper_30d/continuity_schema.py": "continuity_schema_authority",
    "ibkr_paper_30d/continuity_models.py": "continuity_contracts",
    "ibkr_paper_30d/continuity_store.py": "continuity_event_authority",
    "ibkr_paper_30d/provider_lifecycle.py": "provider_lifecycle_authority",
    "ibkr_paper_30d/continuity_evaluator.py": "continuity_condition_evaluator",
    "ibkr_paper_30d/continuity_binding.py": "continuity_order_binding",
    "ibkr_paper_30d/broker_write_coordinator.py": "single_writer_command_queue",
    "ibkr_paper_30d/authoritative_broker_writer.py": "authoritative_broker_writer",
    "ibkr_paper_30d/broker_writer_capability.py": "writer_capability_boundary",
    "ibkr_paper_30d/continuity_executor.py": "continuity_command_builder",
    "ibkr_paper_30d/continuity_watchdog.py": "independent_continuity_watchdog",
    "ibkr_paper_30d/continuity_reporting.py": "continuity_recovery_review_gate",
}

POWERSHELL_ROOT_ROLES: dict[str, str] = {
    "FINALIZE_IBKR_PREREQUISITES.ps1": "privileged_finalizer_entrypoint",
    "RUN_IBKR_DAY1_SERVICE.ps1": "day1_service_entrypoint",
    "RUN_IBKR_MARKET_DATA_GATE.ps1": "scheduled_market_gate_entrypoint",
}

# Reviewed dynamic authority dependencies that are not guaranteed to appear as
# ordinary imports from every deployment entrypoint.
DYNAMIC_ROOT_ROLES: dict[str, str] = {
    "ibkr_paper_30d/auditor_gate_v2.py": "dynamic_auditor_gate",
    "ibkr_paper_30d/auditor_runtime_v2.py": "dynamic_auditor_runtime",
    "ibkr_paper_30d/ibkr_research_tools.py": "dynamic_broker_research_boundary",
}


class KernelManifestError(RuntimeError):
    pass


def _normalize_root(path: str) -> str:
    value = PurePosixPath(str(path).replace("\\", "/"))
    if value.is_absolute() or ".." in value.parts:
        raise KernelManifestError(f"kernel path escapes repository: {path}")
    normalized = value.as_posix()
    if not normalized or normalized == ".":
        raise KernelManifestError("kernel path is empty")
    return normalized


def _tracked_files(root: Path) -> set[str]:
    completed = subprocess.run(
        ["git", "-C", str(root), "ls-files", "-z"],
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        raise KernelManifestError("repository tracked files are unavailable")
    return {
        item.decode("utf-8").replace("\\", "/")
        for item in completed.stdout.split(b"\0")
        if item
    }


def _validated_file(root: Path, relative: str, tracked: set[str]) -> Path:
    normalized = _normalize_root(relative)
    raw = root.joinpath(*PurePosixPath(normalized).parts)
    if any(parent.is_symlink() for parent in (raw, *raw.parents) if parent != root.parent):
        raise KernelManifestError(f"kernel file is a symlink: {normalized}")
    resolved_root = root.resolve()
    resolved = raw.resolve()
    if resolved_root != resolved and resolved_root not in resolved.parents:
        raise KernelManifestError(f"kernel path escapes repository: {normalized}")
    if not raw.is_file():
        raise KernelManifestError(f"kernel file missing: {normalized}")
    if normalized not in tracked:
        raise KernelManifestError(f"kernel file is not tracked: {normalized}")
    return raw


def _module_name(relative: str) -> str:
    path = PurePosixPath(relative)
    parts = list(path.with_suffix("").parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def _module_path(root: Path, module: str) -> str | None:
    if module != "ibkr_paper_30d" and not module.startswith("ibkr_paper_30d."):
        return None
    direct = PurePosixPath(*module.split(".")).with_suffix(".py").as_posix()
    package = PurePosixPath(*module.split("."), "__init__.py").as_posix()
    if (root / direct).is_file():
        return direct
    if (root / package).is_file():
        return package
    raise KernelManifestError(f"local authority import is missing: {module}")


def _imports(root: Path, relative: str) -> set[str]:
    source = (root / relative).read_text(encoding="utf-8")
    try:
        tree = ast.parse(source, filename=relative)
    except SyntaxError as exc:
        raise KernelManifestError(f"kernel Python syntax is invalid: {relative}") from exc
    current = _module_name(relative).split(".")
    package = current[:-1]
    discovered: set[str] = set()
    for node in ast.walk(tree):
        modules: list[str] = []
        if isinstance(node, ast.Import):
            modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                if node.level - 1 > len(package):
                    raise KernelManifestError(
                        f"relative import escapes package in {relative}"
                    )
                base = package[: len(package) - (node.level - 1)]
                if node.module:
                    modules.append(".".join([*base, *node.module.split(".")]))
                else:
                    modules.extend(".".join([*base, alias.name]) for alias in node.names)
            elif node.module:
                modules.append(node.module)
        for module in modules:
            resolved = _module_path(root, module)
            if resolved is not None:
                discovered.add(resolved)
    return discovered


def _file_entry(path: Path, relative: str, role: str) -> dict[str, Any]:
    content = path.read_bytes()
    digest = hashlib.sha256(content).hexdigest()
    if len(digest) != 64:
        raise KernelManifestError(f"kernel file is unhashed: {relative}")
    return {
        "path": relative,
        "authority_role": role,
        "sha256": digest,
        "size_bytes": len(content),
    }


def _reject_duplicates(paths: Iterable[str]) -> tuple[str, ...]:
    normalized: list[str] = []
    seen: set[str] = set()
    for path in paths:
        item = _normalize_root(path)
        if item in seen:
            raise KernelManifestError(f"duplicate kernel root: {item}")
        seen.add(item)
        normalized.append(item)
    return tuple(normalized)


def build_kernel_manifest(
    repo_root: str | Path,
    *,
    python_roots: tuple[str, ...] | None = None,
    powershell_roots: tuple[str, ...] | None = None,
) -> dict[str, Any]:
    root = Path(repo_root).resolve()
    tracked = _tracked_files(root)
    python = _reject_duplicates(
        python_roots
        if python_roots is not None
        else tuple(PYTHON_ROOT_ROLES) + tuple(DYNAMIC_ROOT_ROLES)
    )
    powershell = _reject_duplicates(
        powershell_roots
        if powershell_roots is not None
        else tuple(POWERSHELL_ROOT_ROLES)
    )
    overlap = set(python) & set(powershell)
    if overlap:
        raise KernelManifestError(f"duplicate kernel root: {sorted(overlap)[0]}")

    roles: dict[str, str] = {}
    for path in python:
        roles[path] = (
            PYTHON_ROOT_ROLES.get(path)
            or DYNAMIC_ROOT_ROLES.get(path)
            or "python_authority_root"
        )
    for path in powershell:
        roles[path] = POWERSHELL_ROOT_ROLES.get(path) or "powershell_authority_root"

    pending = list(python)
    closure: set[str] = set()
    while pending:
        relative = pending.pop()
        if relative in closure:
            continue
        target = _validated_file(root, relative, tracked)
        if target.suffix.lower() != ".py":
            raise KernelManifestError(f"Python kernel root has invalid suffix: {relative}")
        closure.add(relative)
        for imported in sorted(_imports(root, relative)):
            if imported not in closure:
                roles.setdefault(imported, "python_dependency")
                pending.append(imported)

    all_paths = sorted(closure | set(powershell))
    entries = [
        _file_entry(_validated_file(root, path, tracked), path, roles[path])
        for path in all_paths
    ]
    root_spec = {
        "python_roots": list(python),
        "powershell_roots": list(powershell),
    }
    unsigned = {
        "schema": KERNEL_MANIFEST_SCHEMA,
        "root_spec_sha256": sha256_json(root_spec),
        "kernel_files": entries,
        "file_count": len(entries),
    }
    return {**unsigned, "kernel_manifest_sha256": sha256_json(unsigned)}


def verify_kernel_manifest(
    repo_root: str | Path, manifest: dict[str, Any]
) -> dict[str, Any]:
    current = build_kernel_manifest(repo_root)
    expected = manifest.get("kernel_manifest_sha256")
    valid_embedded = (
        isinstance(manifest, dict)
        and expected
        == sha256_json(
            {key: value for key, value in manifest.items() if key != "kernel_manifest_sha256"}
        )
    )
    verified = valid_embedded and manifest == current
    return {
        "schema": "IMMUTABLE_KERNEL_VERIFICATION_V2",
        "verified": bool(verified),
        "expected_sha256": expected,
        "actual_sha256": current["kernel_manifest_sha256"],
        "file_count": current["file_count"],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    manifest = build_kernel_manifest(args.repo_root)
    args.output.write_bytes(canonical_bytes(manifest) + b"\n")
    print(json.dumps({"status": "PASS", "file_count": manifest["file_count"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
