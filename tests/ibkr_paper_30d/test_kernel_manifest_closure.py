from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from ibkr_paper_30d.kernel_manifest import (
    KernelManifestError,
    build_kernel_manifest,
    verify_kernel_manifest,
)


REPO = Path(__file__).resolve().parents[2]


def _git(repo: Path, *arguments: str) -> None:
    subprocess.run(
        ["git", "-C", str(repo), *arguments],
        check=True,
        capture_output=True,
        text=True,
    )


def _mini_repo(tmp_path: Path) -> Path:
    package = tmp_path / "ibkr_paper_30d"
    package.mkdir()
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "root.py").write_text(
        "from .guard import enforce\n\ndef launch():\n    return enforce()\n",
        encoding="utf-8",
    )
    (package / "guard.py").write_text(
        "from .new_authority import check\n\ndef enforce():\n    return check()\n",
        encoding="utf-8",
    )
    (package / "new_authority.py").write_text(
        "def check():\n    return True\n", encoding="utf-8"
    )
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "test@example.invalid")
    _git(tmp_path, "config", "user.name", "Test")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-qm", "fixture")
    return tmp_path


def test_python_ast_closure_includes_new_authority_dependency(tmp_path) -> None:
    repo = _mini_repo(tmp_path)

    manifest = build_kernel_manifest(
        repo,
        python_roots=("ibkr_paper_30d/root.py",),
        powershell_roots=(),
    )

    entries = {item["path"]: item for item in manifest["kernel_files"]}
    assert set(entries) == {
        "ibkr_paper_30d/guard.py",
        "ibkr_paper_30d/new_authority.py",
        "ibkr_paper_30d/root.py",
    }
    assert entries["ibkr_paper_30d/root.py"]["authority_role"] == "python_authority_root"
    assert entries["ibkr_paper_30d/new_authority.py"]["authority_role"] == "python_dependency"


def test_untracked_imported_authority_file_is_rejected(tmp_path) -> None:
    repo = _mini_repo(tmp_path)
    imported = repo / "ibkr_paper_30d" / "untracked.py"
    imported.write_text("VALUE = True\n", encoding="utf-8")
    root = repo / "ibkr_paper_30d" / "root.py"
    root.write_text("from .untracked import VALUE\n", encoding="utf-8")

    with pytest.raises(KernelManifestError, match="not tracked"):
        build_kernel_manifest(
            repo,
            python_roots=("ibkr_paper_30d/root.py",),
            powershell_roots=(),
        )


@pytest.mark.parametrize(
    ("roots", "message"),
    [
        (("ibkr_paper_30d/missing.py",), "missing"),
        (("../outside.py",), "escapes"),
        (("ibkr_paper_30d/root.py", "ibkr_paper_30d/root.py"), "duplicate"),
    ],
)
def test_invalid_root_specification_fails_closed(tmp_path, roots, message) -> None:
    repo = _mini_repo(tmp_path)

    with pytest.raises(KernelManifestError, match=message):
        build_kernel_manifest(repo, python_roots=roots, powershell_roots=())


def test_real_kernel_has_complete_roots_roles_and_valid_hashes() -> None:
    manifest = build_kernel_manifest(REPO)
    paths = {item["path"] for item in manifest["kernel_files"]}

    assert {
        "RUN_IBKR_MARKET_DATA_GATE.ps1",
        "RUN_IBKR_DAY1_SERVICE.ps1",
        "FINALIZE_IBKR_PREREQUISITES.ps1",
        "ibkr_paper_30d/day1_launch.py",
        "ibkr_paper_30d/autonomous_execution.py",
        "ibkr_paper_30d/autonomy_bootstrap.py",
        "ibkr_paper_30d/experiment_epoch.py",
        "ibkr_paper_30d/kernel_manifest.py",
        "ibkr_paper_30d/continuity_schema.py",
        "ibkr_paper_30d/continuity_models.py",
        "ibkr_paper_30d/continuity_store.py",
        "ibkr_paper_30d/provider_lifecycle.py",
        "ibkr_paper_30d/continuity_evaluator.py",
        "ibkr_paper_30d/continuity_binding.py",
        "ibkr_paper_30d/broker_write_coordinator.py",
        "ibkr_paper_30d/authoritative_broker_writer.py",
        "ibkr_paper_30d/broker_writer_capability.py",
        "ibkr_paper_30d/continuity_executor.py",
        "ibkr_paper_30d/continuity_watchdog.py",
        "ibkr_paper_30d/continuity_reporting.py",
    } <= paths
    assert manifest["file_count"] == len(paths)
    assert all(len(item["sha256"]) == 64 for item in manifest["kernel_files"])
    assert all(item["authority_role"] for item in manifest["kernel_files"])
    assert verify_kernel_manifest(REPO, manifest)["verified"] is True
    assert "generated_at_utc" not in manifest


def test_checked_in_manifest_matches_derived_closure() -> None:
    stored = json.loads(
        (REPO / "IMMUTABLE_EXECUTION_KERNEL_MANIFEST.json").read_text(
            encoding="utf-8"
        )
    )
    verification = verify_kernel_manifest(REPO, stored)

    assert verification["verified"] is True
