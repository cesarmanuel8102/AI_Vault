from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
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


@dataclass(frozen=True)
class RuntimeIntegrityResult:
    status: str
    reason_codes: tuple[str, ...]
    runtime_manifest_sha256: str | None = None
    deployment_manifest_sha256: str | None = None

    @classmethod
    def block(cls, *reasons: str) -> "RuntimeIntegrityResult":
        return cls("BLOCK", tuple(dict.fromkeys(reasons)))


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
