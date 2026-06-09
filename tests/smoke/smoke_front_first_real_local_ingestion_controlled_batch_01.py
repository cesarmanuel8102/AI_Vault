"""Smoke test for FRONT-FIRST-REAL-LOCAL-INGESTION-CONTROLLED-BATCH-01.

Validates controlled batch ingestion module and its idempotency.
"""

import subprocess
import sys
from pathlib import Path

_REPO_ROOT = str(Path(__file__).resolve().parent.parent.parent)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)
sys.path.insert(0, str(Path(_REPO_ROOT) / "tmp_agent"))

import brain.first_real_local_ingestion_controlled_batch as batch


def test_module_imports():
    assert callable(batch.batch_front_id)
    assert callable(batch.build_source_allowlist)
    assert callable(batch.validate_source)
    assert callable(batch.build_memory_record)
    assert callable(batch.validate_memory_record)
    assert callable(batch.inspect_memory_and_faiss)
    assert callable(batch.memory_record_count)
    assert callable(batch.faiss_record_count)
    assert callable(batch.append_memory_record)
    assert callable(batch.promote_record_to_faiss)
    assert callable(batch.run_controlled_batch_ingestion)
    assert callable(batch.summarize_batch_result)


def test_batch_front_id_exact():
    assert batch.batch_front_id() == "FRONT-FIRST-REAL-LOCAL-INGESTION-CONTROLLED-BATCH-01"


def test_allowlist_has_leq_3_sources():
    allowlist = batch.build_source_allowlist()
    assert len(allowlist) <= 3


def test_allowlist_exact_paths_only():
    allowlist = batch.build_source_allowlist()
    paths = [s["path"] for s in allowlist]
    assert "docs/REAL_EXECUTION_POLICY.md" in paths
    assert "docs/RUNTIME_RECOVERY_RUNBOOK.md" in paths
    assert "docs/FRONT_FIRST_REAL_LOCAL_MEMORY_FAISS_CANARY_01.md" in paths


def test_blocked_env_rejected():
    val = batch.validate_source(".env")
    assert val["ok"] is False
    assert val["allowed"] is False


def test_blocked_memory_semantic_source_rejected():
    val = batch.validate_source("memory/semantic/semantic_memory.jsonl")
    assert val["ok"] is False


def test_blocked_trading_rejected():
    val = batch.validate_source("trading/strategy.py")
    assert val["ok"] is False


def test_blocked_b8_rejected():
    val = batch.validate_source("B8/config.py")
    assert val["ok"] is False


def test_each_ready_source_has_deterministic_id():
    for src in batch.build_source_allowlist():
        assert "id" in src
        assert src["id"].startswith("controlled_batch_01_")


def test_memory_record_validates_ok():
    for src in batch.build_source_allowlist():
        src["sha256"] = "a" * 64
        rec = batch.build_memory_record(src)
        val = batch.validate_memory_record(rec)
        assert val["ok"] is True


def test_fact_length_leq_800():
    for src in batch.build_source_allowlist():
        assert len(src["fact"]) <= 800


def test_no_full_document_content_in_fact():
    for src in batch.build_source_allowlist():
        assert "# FRONT" not in src["fact"]
        assert "---" not in src["fact"]


def test_run_is_idempotent():
    before = batch.inspect_memory_and_faiss()
    result1 = batch.run_controlled_batch_ingestion()
    after1 = batch.inspect_memory_and_faiss()
    # Second run should not create duplicates
    result2 = batch.run_controlled_batch_ingestion()
    after2 = batch.inspect_memory_and_faiss()
    assert after2["memory"]["line_count"] == after1["memory"]["line_count"]
    assert after2["faiss"]["ids_count"] == after1["faiss"]["ids_count"]
    assert result2["already_complete_count"] == 3 or result2["already_complete_count"] >= len(batch.SOURCES)


def test_each_completed_item_memory_count_after_is_1():
    result = batch.run_controlled_batch_ingestion()
    for item in result["items"]:
        if item["status"] in ("WRITTEN_AND_PROMOTED", "ALREADY_COMPLETE"):
            assert item["memory_count_after"] == 1


def test_each_completed_item_faiss_count_after_is_1():
    result = batch.run_controlled_batch_ingestion()
    for item in result["items"]:
        if item["status"] in ("WRITTEN_AND_PROMOTED", "ALREADY_COMPLETE"):
            assert item["faiss_count_after"] == 1


def test_network_called_false():
    result = batch.run_controlled_batch_ingestion()
    assert result["network_called"] is False


def test_connector_called_false():
    result = batch.run_controlled_batch_ingestion()
    assert result["connector_called"] is False


def test_trading_executed_false():
    result = batch.run_controlled_batch_ingestion()
    assert result["trading_executed"] is False


def test_b8_touched_false():
    result = batch.run_controlled_batch_ingestion()
    assert result["b8_touched"] is False


def test_no_env_staged():
    result = subprocess.run(["git", "diff", "--cached", "--name-status"], capture_output=True, text=True, cwd=".")
    staged = result.stdout.strip()
    if staged:
        assert ".env" not in staged


def test_no_session_py_staged():
    result = subprocess.run(["git", "diff", "--cached", "--name-status"], capture_output=True, text=True, cwd=".")
    staged = result.stdout.strip()
    if staged:
        assert "session.py" not in staged


def test_no_main_py_staged():
    result = subprocess.run(["git", "diff", "--cached", "--name-status"], capture_output=True, text=True, cwd=".")
    staged = result.stdout.strip()
    if staged:
        assert "main.py" not in staged


def test_no_execution_gate_py_staged():
    result = subprocess.run(["git", "diff", "--cached", "--name-status"], capture_output=True, text=True, cwd=".")
    staged = result.stdout.strip()
    if staged:
        assert "execution_gate.py" not in staged


def test_no_curated_runtime_lookup_staged():
    result = subprocess.run(["git", "diff", "--cached", "--name-status"], capture_output=True, text=True, cwd=".")
    staged = result.stdout.strip()
    if staged:
        assert "curated_runtime_lookup.py" not in staged


def test_roadmap_status_json_valid():
    result = subprocess.run([sys.executable, "-m", "json.tool", "ROADMAP_STATUS.json"], capture_output=True, text=True, cwd=".")
    assert result.returncode == 0
