from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

from ibkr_paper_30d.auditor_runtime_v2 import (
    RUNTIME_MANIFEST_NAME,
    RUNTIME_PAYLOAD_ALLOWLIST,
    build_deployment_manifest_v2,
    build_runtime_manifest_v2,
    verify_runtime_fileset_v2,
)
from ibkr_paper_30d.canonical import canonical_bytes


@pytest.fixture
def staged_runtime(tmp_path: Path) -> Path:
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    for name in RUNTIME_PAYLOAD_ALLOWLIST:
        (runtime / name).write_text(f"# {name}\n", encoding="utf-8")
    manifest = build_runtime_manifest_v2(runtime, RUNTIME_PAYLOAD_ALLOWLIST)
    (runtime / RUNTIME_MANIFEST_NAME).write_bytes(canonical_bytes(manifest))
    return runtime


def _deployment(runtime: Path) -> dict[str, object]:
    return build_deployment_manifest_v2(
        runtime / RUNTIME_MANIFEST_NAME,
        [runtime / name for name in RUNTIME_PAYLOAD_ALLOWLIST],
    )


def test_runtime_v2_accepts_exact_hash_bound_fileset(staged_runtime: Path) -> None:
    result = verify_runtime_fileset_v2(staged_runtime, _deployment(staged_runtime))

    assert result.status == "PASS"
    assert result.reason_codes == ()
    assert result.runtime_manifest_sha256
    assert result.deployment_manifest_sha256


@pytest.mark.parametrize(
    "mutation",
    ["EXTRA", "MISSING", "PAYLOAD_HASH", "RUNTIME_MANIFEST_HASH"],
)
def test_runtime_v2_blocks_every_fileset_or_hash_mutation(
    staged_runtime: Path, mutation: str
) -> None:
    deployment = _deployment(staged_runtime)
    if mutation == "EXTRA":
        (staged_runtime / "extra.ps1").write_text("# extra", encoding="utf-8")
    elif mutation == "MISSING":
        (staged_runtime / RUNTIME_PAYLOAD_ALLOWLIST[0]).unlink()
    elif mutation == "PAYLOAD_HASH":
        (staged_runtime / RUNTIME_PAYLOAD_ALLOWLIST[0]).write_text(
            "# changed", encoding="utf-8"
        )
    else:
        (staged_runtime / RUNTIME_MANIFEST_NAME).write_text(
            "{}", encoding="utf-8"
        )

    result = verify_runtime_fileset_v2(staged_runtime, deployment)

    assert result.status == "BLOCK"
    assert result.reason_codes


@pytest.mark.parametrize(
    "mutation",
    ["SCHEMA", "MALFORMED_HASH", "CASE_COLLISION", "PATH_SEPARATOR"],
)
def test_runtime_v2_rejects_untrusted_deployment_manifest(
    staged_runtime: Path, mutation: str
) -> None:
    deployment = deepcopy(_deployment(staged_runtime))
    if mutation == "SCHEMA":
        deployment["schema"] = "FOREIGN"
    elif mutation == "MALFORMED_HASH":
        deployment["files"][RUNTIME_PAYLOAD_ALLOWLIST[0]] = "bad"
    elif mutation == "CASE_COLLISION":
        deployment["files"][RUNTIME_PAYLOAD_ALLOWLIST[0].lower()] = "0" * 64
    else:
        deployment["files"]["nested/evil.ps1"] = "0" * 64

    result = verify_runtime_fileset_v2(staged_runtime, deployment)

    assert result.status == "BLOCK"


def test_runtime_v2_rejects_non_file_runtime_entry(staged_runtime: Path) -> None:
    (staged_runtime / "directory").mkdir()

    result = verify_runtime_fileset_v2(staged_runtime, _deployment(staged_runtime))

    assert result.status == "BLOCK"
    assert "RUNTIME_FILESET_MISMATCH" in result.reason_codes
