from pathlib import Path

ROOT = Path(r"C:\AI_VAULT_CANONICAL")

def test_canonical_semantic_memory_lines():
    path = ROOT / "memory" / "semantic" / "semantic_memory.jsonl"
    assert path.exists()
    assert sum(1 for _ in path.open("r", encoding="utf-8")) == 1715

def test_canonical_faiss_ids_count():
    import json
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

def test_legacy_path_or_quarantine_exists():
    assert Path(r"C:\AI_VAULT").exists() or any(Path("C:/").glob("AI_VAULT_LEGACY_QUARANTINE*"))

def test_lock_diagnostic_artifact_exists():
    assert (ROOT / "tmp_agent" / "front_legacy_lock_diagnostic_manual_steps_01" / "lock_diagnostic_results.json").exists()

def test_lock_source_classification_artifact_exists():
    assert (ROOT / "tmp_agent" / "front_legacy_lock_diagnostic_manual_steps_01" / "lock_source_classification.json").exists()

def test_manual_lock_release_plan_exists():
    assert (ROOT / "tmp_agent" / "front_legacy_lock_diagnostic_manual_steps_01" / "manual_lock_release_plan.json").exists()

def test_next_retry_conditions_exists():
    assert (ROOT / "tmp_agent" / "front_legacy_lock_diagnostic_manual_steps_01" / "next_retry_conditions.json").exists()

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
    import json
    json.loads((ROOT / "ROADMAP_STATUS.json").read_text(encoding="utf-8"))

def test_ledger_exists():
    assert (ROOT / "docs" / "MIGRATION_CONTROL_LEDGER.md").exists()
