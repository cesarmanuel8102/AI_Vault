"""Smoke test for FRONT-FIRST-REAL-LOCAL-MEMORY-FAISS-CANARY-01.

Validates controlled single-record semantic memory write + FAISS canary promotion.
"""

import subprocess
import sys
from pathlib import Path

_REPO_ROOT = str(Path(__file__).resolve().parent.parent.parent)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)
sys.path.insert(0, str(Path(_REPO_ROOT) / "tmp_agent"))

import brain.first_real_local_memory_faiss_canary as cmod


def test_module_imports():
    assert callable(cmod.canary_id)
    assert callable(cmod.build_canary_record)
    assert callable(cmod.validate_canary_record)
    assert callable(cmod.inspect_semantic_memory)
    assert callable(cmod.inspect_faiss_state)
    assert callable(cmod.memory_canary_exists)
    assert callable(cmod.faiss_canary_exists)
    assert callable(cmod.append_memory_canary)
    assert callable(cmod.promote_canary_to_faiss)
    assert callable(cmod.run_first_real_local_memory_faiss_canary)


def test_canary_id_exact():
    assert cmod.canary_id() == "front_first_real_local_memory_faiss_canary_01"


def test_build_canary_record_returns_dict():
    rec = cmod.build_canary_record()
    assert isinstance(rec, dict)
    assert rec["id"] == "front_first_real_local_memory_faiss_canary_01"


def test_record_validates_ok():
    rec = cmod.build_canary_record()
    val = cmod.validate_canary_record(rec)
    assert val["ok"] is True


def test_source_front_exact():
    rec = cmod.build_canary_record()
    assert rec["source_front"] == "FRONT-FIRST-REAL-LOCAL-INGESTION-DRY-RUN-01"


def test_source_path_exact():
    rec = cmod.build_canary_record()
    assert rec["source_path"] == "docs/REAL_EXECUTION_POLICY.md"


def test_source_sha256_exact():
    rec = cmod.build_canary_record()
    assert rec["source_sha256"] == "b493b364185a60c2c9ad116907a347e69890c9978ec6fa6bb18c7bee0ae1801d"


def test_ready_for_faiss_true():
    rec = cmod.build_canary_record()
    assert rec["ready_for_faiss"] is True


def test_semantic_memory_write_executed_true_in_record():
    rec = cmod.build_canary_record()
    assert rec["evidence"]["semantic_memory_write_executed"] is True


def test_faiss_write_executed_true_in_record():
    rec = cmod.build_canary_record()
    assert rec["evidence"]["faiss_write_executed"] is True


def test_network_called_false():
    rec = cmod.build_canary_record()
    assert rec["evidence"]["network_called"] is False


def test_connector_called_false():
    rec = cmod.build_canary_record()
    assert rec["evidence"]["connector_called"] is False


def test_promotion_executed_true():
    rec = cmod.build_canary_record()
    assert rec["evidence"]["promotion_executed"] is True


def test_trading_executed_false():
    rec = cmod.build_canary_record()
    assert rec["evidence"]["trading_executed"] is False


def test_b8_touched_false():
    rec = cmod.build_canary_record()
    assert rec["evidence"]["b8_touched"] is False


def test_semantic_memory_path_correct():
    assert cmod.semantic_memory_path().as_posix() == "memory/semantic/semantic_memory.jsonl"


def test_faiss_index_path_exists():
    assert cmod.faiss_index_path().exists()


def test_faiss_ids_path_exists():
    assert cmod.faiss_ids_path().exists()


def test_inspect_semantic_memory_returns_line_count_and_sha256():
    info = cmod.inspect_semantic_memory()
    assert "line_count" in info
    assert "sha256" in info
    assert info["line_count"] > 0
    assert info["sha256"] is not None


def test_inspect_faiss_state_returns_ids_count():
    info = cmod.inspect_faiss_state()
    assert "ids_count" in info
    assert "canary_count" in info
    assert info["ids_count"] > 0


def test_memory_canary_exists_returns_bool():
    assert isinstance(cmod.memory_canary_exists(), bool)


def test_faiss_canary_exists_returns_bool():
    assert isinstance(cmod.faiss_canary_exists(), bool)


def test_idempotency_second_run_does_not_create_duplicate_memory():
    before = cmod.inspect_semantic_memory()
    # Re-run should not create duplicate
    result = cmod.run_first_real_local_memory_faiss_canary()
    assert result["status"] == "CANARY_ALREADY_COMPLETE"
    after = cmod.inspect_semantic_memory()
    assert after["canary_count"] == 1
    assert after["line_count"] == before["line_count"]


def test_idempotency_second_run_does_not_create_duplicate_faiss_id():
    before = cmod.inspect_faiss_state()
    result = cmod.run_first_real_local_memory_faiss_canary()
    assert result["status"] == "CANARY_ALREADY_COMPLETE"
    after = cmod.inspect_faiss_state()
    assert after["canary_count"] == 1
    assert after["ids_count"] == before["ids_count"]


def test_memory_canary_count_is_one():
    info = cmod.inspect_semantic_memory()
    assert info["canary_count"] == 1


def test_faiss_canary_count_is_one():
    info = cmod.inspect_faiss_state()
    assert info["canary_count"] == 1


def test_no_env_staged():
    result = subprocess.run(["git", "diff", "--cached", "--name-status"], capture_output=True, text=True, cwd=".")
    staged = result.stdout.strip()
    if staged:
        assert ".env" not in staged


def test_no_trading_or_b8_staged():
    result = subprocess.run(["git", "diff", "--cached", "--name-status"], capture_output=True, text=True, cwd=".")
    staged = result.stdout.strip()
    if staged:
        lines = staged.split("\n")
        bad = any("trading" in line or "b8" in line.lower() for line in lines)
        assert not bad


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
    result = subprocess.run(["python", "-m", "json.tool", "ROADMAP_STATUS.json"], capture_output=True, text=True, cwd=".")
    assert result.returncode == 0
