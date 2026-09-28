from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from ibkr_paper_30d.runtime_provenance import (
    RuntimeProvenanceError,
    build_approved_runtime_material,
    verify_runtime_provenance,
)


def _git(repo: Path, *arguments: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(repo), *arguments],
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def _repo(tmp_path: Path) -> tuple[Path, str]:
    package = tmp_path / "ibkr_paper_30d"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "alpha.py").write_text("VALUE = 1\n", encoding="utf-8")
    (package / "beta.py").write_text("from .alpha import VALUE\n", encoding="utf-8")
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "test@example.invalid")
    _git(tmp_path, "config", "user.name", "Test")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-qm", "approved")
    return tmp_path, _git(tmp_path, "rev-parse", "HEAD")


def test_approved_deployed_material_passes_with_exact_hashes(tmp_path) -> None:
    repo, commit = _repo(tmp_path / "repo")
    material = build_approved_runtime_material(repo, commit)
    deployment = tmp_path / "deployment"
    shutil.copytree(repo / "ibkr_paper_30d", deployment / "ibkr_paper_30d")

    report = verify_runtime_provenance(deployment, material, loaded_module_files=[])

    assert report["gate_status"] == "PASS"
    assert report["approved_commit"] == commit
    assert report["file_count"] == 3
    assert set(report["classifications"].values()) == {"TRACKED_APPROVED"}


def test_modified_tracked_module_is_rejected(tmp_path) -> None:
    repo, commit = _repo(tmp_path)
    material = build_approved_runtime_material(repo, commit)
    (repo / "ibkr_paper_30d" / "alpha.py").write_text("VALUE = 2\n", encoding="utf-8")

    with pytest.raises(RuntimeProvenanceError, match="hash mismatch"):
        verify_runtime_provenance(repo, material, loaded_module_files=[])


@pytest.mark.parametrize("ignored", [False, True])
def test_untracked_or_ignored_executable_source_is_rejected(tmp_path, ignored) -> None:
    repo, commit = _repo(tmp_path)
    material = build_approved_runtime_material(repo, commit)
    extra = repo / "ibkr_paper_30d" / "extra.py"
    extra.write_text("VALUE = 3\n", encoding="utf-8")
    if ignored:
        (repo / ".gitignore").write_text("ibkr_paper_30d/extra.py\n", encoding="utf-8")

    with pytest.raises(RuntimeProvenanceError, match="unapproved runtime source"):
        verify_runtime_provenance(repo, material, loaded_module_files=[])


def test_alternate_loaded_import_root_is_rejected(tmp_path) -> None:
    repo, commit = _repo(tmp_path / "repo")
    material = build_approved_runtime_material(repo, commit)
    alternate = tmp_path / "alternate" / "ibkr_paper_30d" / "alpha.py"
    alternate.parent.mkdir(parents=True)
    alternate.write_text("VALUE = 1\n", encoding="utf-8")

    with pytest.raises(RuntimeProvenanceError, match="alternate import root"):
        verify_runtime_provenance(repo, material, loaded_module_files=[alternate])


def test_symlinked_runtime_source_is_rejected(tmp_path) -> None:
    repo, commit = _repo(tmp_path / "repo")
    material = build_approved_runtime_material(repo, commit)
    deployment = tmp_path / "deployment"
    target = deployment / "real-package"
    shutil.copytree(repo / "ibkr_paper_30d", target)
    link = deployment / "ibkr_paper_30d"
    completed = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(link), str(target)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr

    with pytest.raises(RuntimeProvenanceError, match="symlink"):
        verify_runtime_provenance(deployment, material, loaded_module_files=[])


def test_material_hash_tampering_is_rejected(tmp_path) -> None:
    repo, commit = _repo(tmp_path)
    material = build_approved_runtime_material(repo, commit)
    material["files"][0]["sha256"] = "0" * 64

    with pytest.raises(RuntimeProvenanceError, match="material hash"):
        verify_runtime_provenance(repo, material, loaded_module_files=[])
