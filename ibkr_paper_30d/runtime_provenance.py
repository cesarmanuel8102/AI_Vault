"""Fail-closed provenance verification for executable package source."""

from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path, PurePosixPath
from typing import Any, Iterable

from .canonical import sha256_json

RUNTIME_MATERIAL_SCHEMA = "APPROVED_RUNTIME_MATERIAL_V1"
RUNTIME_REPORT_SCHEMA = "RUNTIME_SOURCE_PROVENANCE_REPORT_V1"


class RuntimeProvenanceError(RuntimeError):
    pass


def _git(repo: Path, arguments: list[str]) -> bytes:
    completed = subprocess.run(
        ["git", "-C", str(repo), *arguments],
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeProvenanceError("approved Git material is unavailable")
    return completed.stdout


def build_approved_runtime_material(
    repo_root: str | Path,
    approved_commit: str,
    *,
    package: str = "ibkr_paper_30d",
) -> dict[str, Any]:
    root = Path(repo_root).resolve()
    commit = _git(root, ["rev-parse", f"{approved_commit}^{{commit}}"])
    commit_sha = commit.decode("ascii").strip()
    tree_sha = _git(root, ["rev-parse", f"{commit_sha}^{{tree}}"])
    paths = _git(
        root,
        ["ls-tree", "-r", "--name-only", "-z", commit_sha, "--", package],
    )
    source_paths = sorted(
        item.decode("utf-8").replace("\\", "/")
        for item in paths.split(b"\0")
        if item and item.decode("utf-8").endswith(".py")
    )
    if not source_paths:
        raise RuntimeProvenanceError("approved package source is empty")
    files = []
    for relative in source_paths:
        content = _git(root, ["show", f"{commit_sha}:{relative}"])
        files.append(
            {
                "path": relative,
                "sha256": hashlib.sha256(content).hexdigest(),
                "size_bytes": len(content),
            }
        )
    unsigned = {
        "schema": RUNTIME_MATERIAL_SCHEMA,
        "approved_commit": commit_sha,
        "approved_tree": tree_sha.decode("ascii").strip(),
        "package": package,
        "files": files,
        "file_count": len(files),
    }
    return {**unsigned, "material_sha256": sha256_json(unsigned)}


def _has_symlink(path: Path, root: Path) -> bool:
    current = path
    while True:
        try:
            attributes = getattr(current.lstat(), "st_file_attributes", 0)
        except OSError:
            attributes = 0
        if current.is_symlink() or attributes & 0x400:
            return True
        if current == root:
            return False
        if root not in current.parents:
            return True
        current = current.parent


def _loaded_package_files(package: str) -> list[Path]:
    files: list[Path] = []
    for name, module in tuple(sys.modules.items()):
        if name != package and not name.startswith(f"{package}."):
            continue
        value = getattr(module, "__file__", None)
        if not value:
            continue
        path = Path(value)
        if path.suffix in {".pyc", ".pyo"}:
            try:
                path = Path(sys.modules["importlib.util"].source_from_cache(str(path)))
            except (KeyError, ValueError):
                pass
        files.append(path)
    return files


def verify_runtime_provenance(
    runtime_root: str | Path,
    material: dict[str, Any],
    *,
    loaded_module_files: Iterable[str | Path] | None = None,
) -> dict[str, Any]:
    root = Path(runtime_root).resolve()
    unsigned = {
        key: value for key, value in material.items() if key != "material_sha256"
    }
    if material.get("schema") != RUNTIME_MATERIAL_SCHEMA or material.get(
        "material_sha256"
    ) != sha256_json(unsigned):
        raise RuntimeProvenanceError("approved runtime material hash is invalid")
    package = str(material.get("package") or "")
    if not package or "/" in package or "\\" in package:
        raise RuntimeProvenanceError("approved runtime package is invalid")
    rows = material.get("files")
    if not isinstance(rows, list) or len(rows) != material.get("file_count"):
        raise RuntimeProvenanceError("approved runtime material file set is invalid")
    expected: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict):
            raise RuntimeProvenanceError("approved runtime material file is invalid")
        relative = str(row.get("path") or "").replace("\\", "/")
        path = PurePosixPath(relative)
        if (
            path.is_absolute()
            or ".." in path.parts
            or not relative.startswith(f"{package}/")
            or not relative.endswith(".py")
            or relative in expected
        ):
            raise RuntimeProvenanceError("approved runtime material path is invalid")
        expected[relative] = row

    package_root = root / package
    if not package_root.is_dir():
        raise RuntimeProvenanceError("runtime package is missing")
    actual = {
        path.relative_to(root).as_posix(): path for path in package_root.rglob("*.py")
    }
    extras = sorted(set(actual) - set(expected))
    if extras:
        raise RuntimeProvenanceError(f"unapproved runtime source: {extras[0]}")
    missing = sorted(set(expected) - set(actual))
    if missing:
        raise RuntimeProvenanceError(f"approved runtime source missing: {missing[0]}")

    classifications: dict[str, str] = {}
    for relative, row in sorted(expected.items()):
        path = actual[relative]
        if _has_symlink(path, root):
            raise RuntimeProvenanceError(f"runtime source is a symlink: {relative}")
        content = path.read_bytes()
        if len(content) != row.get("size_bytes") or hashlib.sha256(
            content
        ).hexdigest() != row.get("sha256"):
            raise RuntimeProvenanceError(f"runtime source hash mismatch: {relative}")
        classifications[relative] = "TRACKED_APPROVED"

    loaded = (
        _loaded_package_files(package)
        if loaded_module_files is None
        else [Path(value) for value in loaded_module_files]
    )
    for path in loaded:
        resolved = path.resolve()
        if root != resolved and root not in resolved.parents:
            raise RuntimeProvenanceError(
                f"loaded module uses alternate import root: {path.name}"
            )
        if _has_symlink(path, root):
            raise RuntimeProvenanceError(
                f"loaded runtime source is a symlink: {path.name}"
            )
        relative = resolved.relative_to(root).as_posix()
        if relative not in expected:
            raise RuntimeProvenanceError(f"loaded module is not approved: {relative}")

    return {
        "schema": RUNTIME_REPORT_SCHEMA,
        "gate_status": "PASS",
        "reason_codes": [],
        "approved_commit": material["approved_commit"],
        "approved_tree": material["approved_tree"],
        "material_sha256": material["material_sha256"],
        "file_count": len(expected),
        "classifications": classifications,
    }
