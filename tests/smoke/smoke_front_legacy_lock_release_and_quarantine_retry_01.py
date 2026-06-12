from pathlib import Path
import json

ROOT = Path(r"C:\AI_VAULT_CANONICAL")
OUT = ROOT / "tmp_agent" / "front_legacy_lock_release_and_quarantine_retry_01"

def test_canonical_semantic_memory_lines():
    path = ROOT / "memory" / "semantic" / "semantic_memory.jsonl"
    assert path.exists()
    assert sum(1 for _ in path.open("r", encoding="utf-8")) == 1715

def test_canonical_faiss_ids():
    path = ROOT / "memory" / "semantic" / "semantic_memory_faiss_ids.json"
    assert path.exists()
    assert len(json.loads(path.read_text(encoding="utf-8"))) == 1616

def test_canonical_faiss_ntotal_if_readable():
    path = ROOT / "memory" / "semantic" / "semantic_memory_faiss.index"
    assert path.exists()
    try:
        import faiss
    except Exception:
        return
    assert faiss.read_index(str(path)).ntotal == 1616

def test_base_path_canonical():
    import sys
    sys.path.insert(0, str((ROOT / "tmp_agent").resolve()))
    from brain_v9.config import BASE_PATH
    assert str(BASE_PATH.resolve()) == str(ROOT)

def test_lock_process_discovery_artifact_exists():
    assert (OUT / "lock_process_discovery.json").exists()

def test_process_kill_candidate_classification_artifact_exists():
    assert (OUT / "process_kill_candidate_classification.json").exists()

def test_process_close_result_artifact_exists():
    assert (OUT / "process_close_result.json").exists()

def test_post_close_lock_check_artifact_exists():
    assert (OUT / "post_close_lock_check.json").exists()

def test_post_action_canonical_verify_artifact_exists():
    assert (OUT / "post_action_canonical_verify.json").exists()

def test_rollback_plan_exists():
    assert (OUT / "rollback_plan.json").exists()

def _staged_names():
    import subprocess
    proc = subprocess.run(["git", "diff", "--cached", "--name-only"], cwd=ROOT, text=True, capture_output=True, check=True)
    return set(filter(None, proc.stdout.splitlines()))

def test_no_memory_semantic_staged():
    assert not any(name.startswith("memory/semantic/") for name in _staged_names())

def test_no_trading_staged():
    assert not any(name.startswith("trading/") or "/trading/" in name for name in _staged_names())

def test_no_b8_staged():
    assert not any(name.startswith("B8/") or "/B8/" in name for name in _staged_names())

def test_no_tmp_agent_strategies_staged():
    assert not any(name.startswith("tmp_agent/strategies/") for name in _staged_names())

def test_no_env_staged():
    assert ".env" not in _staged_names()

def test_roadmap_status_json_valid():
    json.loads((ROOT / "ROADMAP_STATUS.json").read_text(encoding="utf-8"))

def test_ledger_exists():
    assert (ROOT / "docs" / "MIGRATION_CONTROL_LEDGER.md").exists()

def _rename_result():
    return json.loads((OUT / "quarantine_rename_result.json").read_text(encoding="utf-8"))

def test_if_rename_success_legacy_absent():
    data = _rename_result()
    if data.get("rename_success"):
        assert not Path(r"C:\AI_VAULT").exists()

def test_if_rename_success_quarantine_exists():
    data = _rename_result()
    if data.get("rename_success"):
        assert Path(data["target_path"]).exists()

def test_if_rename_false_legacy_exists():
    data = _rename_result()
    if not data.get("rename_success"):
        assert Path(r"C:\AI_VAULT").exists()

def test_delete_performed_false():
    assert _rename_result().get("deletion_performed") is False

def test_copy_performed_false():
    assert _rename_result().get("copy_performed") is False

def test_sync_performed_false():
    assert _rename_result().get("sync_performed") is False

def test_canonical_memory_mutated_false():
    assert json.loads((OUT / "post_action_canonical_verify.json").read_text(encoding="utf-8")).get("canonical_memory_mutated") is False

def test_canonical_faiss_mutated_false():
    assert json.loads((OUT / "post_action_canonical_verify.json").read_text(encoding="utf-8")).get("canonical_faiss_mutated") is False
