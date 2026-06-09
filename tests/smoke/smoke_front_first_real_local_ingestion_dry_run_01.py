"""Smoke test for FRONT-FIRST-REAL-LOCAL-INGESTION-DRY-RUN-01.

Validates real local file read ingestion module behavior and safety gates.
"""

import subprocess
import sys
from pathlib import Path

_REPO_ROOT = str(Path(__file__).resolve().parent.parent.parent)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

import brain.first_real_local_ingestion_dry_run as frid


def test_module_imports():
    assert callable(frid.build_source_allowlist)
    assert callable(frid.validate_source_path)
    assert callable(frid.read_local_source_for_dry_run)
    assert callable(frid.build_real_execution_packet)
    assert callable(frid.validate_real_execution_packet)
    assert callable(frid.summarize_real_execution_packet)
    assert callable(frid.run_first_real_local_ingestion_dry_run)
    assert issubclass(frid.IngestionError, Exception)


def test_allowlist_contains_real_execution_policy():
    allowlist = frid.build_source_allowlist()
    assert "docs/REAL_EXECUTION_POLICY.md" in allowlist


def test_allowlist_contains_runtime_recovery_runbook():
    allowlist = frid.build_source_allowlist()
    assert "docs/RUNTIME_RECOVERY_RUNBOOK.md" in allowlist


def test_default_run_reads_real_file():
    result = frid.run_first_real_local_ingestion_dry_run()
    assert result["packet"]["read_executed"] is True
    assert result["packet"]["source_size_bytes"] > 0


def test_packet_has_sha256():
    result = frid.run_first_real_local_ingestion_dry_run()
    sha = result["packet"]["sha256"]
    assert isinstance(sha, str) and len(sha) == 64


def test_packet_has_source_size_bytes():
    result = frid.run_first_real_local_ingestion_dry_run()
    assert result["packet"]["source_size_bytes"] > 0


def test_packet_has_preview():
    result = frid.run_first_real_local_ingestion_dry_run()
    preview = result["packet"]["preview_first_500_chars"]
    assert isinstance(preview, str)


def test_read_executed_true():
    result = frid.run_first_real_local_ingestion_dry_run()
    assert result["packet"]["read_executed"] is True


def test_semantic_memory_write_executed_false():
    result = frid.run_first_real_local_ingestion_dry_run()
    assert result["packet"]["semantic_memory_write_executed"] is False


def test_faiss_write_executed_false():
    result = frid.run_first_real_local_ingestion_dry_run()
    assert result["packet"]["faiss_write_executed"] is False


def test_network_called_false():
    result = frid.run_first_real_local_ingestion_dry_run()
    assert result["packet"]["network_called"] is False


def test_connector_called_false():
    result = frid.run_first_real_local_ingestion_dry_run()
    assert result["packet"]["connector_called"] is False


def test_promotion_executed_false():
    result = frid.run_first_real_local_ingestion_dry_run()
    assert result["packet"]["promotion_executed"] is False


def test_trading_executed_false():
    result = frid.run_first_real_local_ingestion_dry_run()
    assert result["packet"]["trading_executed"] is False


def test_b8_touched_false():
    result = frid.run_first_real_local_ingestion_dry_run()
    assert result["packet"]["b8_touched"] is False


def test_env_path_rejected():
    val = frid.validate_source_path(".env")
    assert val["ok"] is False


def test_memory_semantic_path_rejected():
    val = frid.validate_source_path("memory/semantic/semantic_memory.jsonl")
    assert val["ok"] is False


def test_faiss_path_rejected():
    val = frid.validate_source_path("memory/semantic_faiss/semantic_memory_faiss.index")
    assert val["ok"] is False


def test_trading_path_rejected():
    val = frid.validate_source_path("trading/strategy.py")
    assert val["ok"] is False


def test_b8_path_rejected():
    val = frid.validate_source_path("B8/config.py")
    assert val["ok"] is False


def test_absolute_outside_repo_path_rejected():
    val = frid.validate_source_path("C:/Windows/System32/file.txt")
    assert val["ok"] is False


def test_path_traversal_rejected():
    val = frid.validate_source_path("docs/../../secret.txt")
    assert val["ok"] is False


def test_unknown_source_rejected():
    val = frid.validate_source_path("some/random/file.py")
    assert val["ok"] is False


def test_validate_packet_returns_ok_true():
    result = frid.run_first_real_local_ingestion_dry_run()
    validation = frid.validate_real_execution_packet(result["packet"])
    assert validation["ok"] is True


def test_summary_returns_expected_fields():
    result = frid.run_first_real_local_ingestion_dry_run()
    summary = frid.summarize_real_execution_packet(result["packet"])
    assert "source_path" in summary
    assert "source_size_bytes" in summary
    assert "sha256" in summary
    assert "read_executed" in summary
    assert "ready_for_memory_write" in summary
    assert "next_required_front" in summary


def test_roadmap_status_json_valid():
    result = subprocess.run(
        ["python", "-m", "json.tool", "ROADMAP_STATUS.json"],
        capture_output=True,
        text=True,
        cwd=".",
    )
    assert result.returncode == 0


def test_no_semantic_memory_staged():
    result = subprocess.run(
        ["git", "diff", "--cached", "--name-status"],
        capture_output=True,
        text=True,
        cwd=".",
    )
    staged = result.stdout.strip()
    if staged:
        assert "memory/semantic" not in staged


def test_no_faiss_staged():
    result = subprocess.run(
        ["git", "diff", "--cached", "--name-status"],
        capture_output=True,
        text=True,
        cwd=".",
    )
    staged = result.stdout.strip()
    if staged:
        assert "faiss" not in staged.lower()


def test_no_env_staged():
    result = subprocess.run(
        ["git", "diff", "--cached", "--name-status"],
        capture_output=True,
        text=True,
        cwd=".",
    )
    staged = result.stdout.strip()
    if staged:
        assert ".env" not in staged


def test_no_trading_or_b8_staged():
    result = subprocess.run(
        ["git", "diff", "--cached", "--name-status"],
        capture_output=True,
        text=True,
        cwd=".",
    )
    staged = result.stdout.strip()
    if staged:
        lines = staged.split("\n")
        bad = any("trading" in line or "b8" in line.lower() for line in lines)
        assert not bad


def test_no_session_py_staged():
    result = subprocess.run(
        ["git", "diff", "--cached", "--name-status"],
        capture_output=True,
        text=True,
        cwd=".",
    )
    staged = result.stdout.strip()
    if staged:
        assert "session.py" not in staged


def test_no_main_py_staged():
    result = subprocess.run(
        ["git", "diff", "--cached", "--name-status"],
        capture_output=True,
        text=True,
        cwd=".",
    )
    staged = result.stdout.strip()
    if staged:
        assert "main.py" not in staged


def test_no_execution_gate_py_staged():
    result = subprocess.run(
        ["git", "diff", "--cached", "--name-status"],
        capture_output=True,
        text=True,
        cwd=".",
    )
    staged = result.stdout.strip()
    if staged:
        assert "execution_gate.py" not in staged
