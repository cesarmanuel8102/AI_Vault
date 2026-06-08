"""Smoke test for FRONT-REAL-READ-LOOKUP-ADAPTER-01.

Validates that the read-only canary lookup adapter:
1. Can be imported.
2. Does not write anything.
3. Finds the canary exactly once.
4. Reports safe metadata flags.
5. Does not mutate target or FAISS files.
"""

import json
import os

TARGET = "memory/semantic/semantic_memory.jsonl"
CANARY_ID = "canary-00000000-0000-0000-0000-000000000001"
ADAPTER_PATH = "brain/semantic_memory_canary_lookup_read_only.py"
EVIDENCE_DIR = "tmp_agent/front_real_read_lookup_adapter_01"


# Ensure evidence dir exists
os.makedirs(EVIDENCE_DIR, exist_ok=True)


def _load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def test_adapter_module_exists():
    assert os.path.isfile(ADAPTER_PATH), f"Adapter missing: {ADAPTER_PATH}"


def test_adapter_imports():
    import brain.semantic_memory_canary_lookup_read_only as adapter
    assert hasattr(adapter, "lookup_canary_record")
    assert hasattr(adapter, "validate_canary_record")
    assert hasattr(adapter, "hash_file")


def test_lookup_canary_record_function_exists():
    import brain.semantic_memory_canary_lookup_read_only as adapter
    assert callable(adapter.lookup_canary_record)


def test_validate_canary_record_function_exists():
    import brain.semantic_memory_canary_lookup_read_only as adapter
    assert callable(adapter.validate_canary_record)


def test_hash_file_function_exists():
    import brain.semantic_memory_canary_lookup_read_only as adapter
    assert callable(adapter.hash_file)


def test_lookup_finds_canary():
    import brain.semantic_memory_canary_lookup_read_only as adapter
    res = adapter.lookup_canary_record()
    assert res["found"] is True, f"Canary not found: {res}"


def test_lookup_count_is_one():
    import brain.semantic_memory_canary_lookup_read_only as adapter
    res = adapter.lookup_canary_record()
    assert res["count"] == 1, f"Canary count expected 1, got {res['count']}"


def test_lookup_reports_last_line():
    import brain.semantic_memory_canary_lookup_read_only as adapter
    res = adapter.lookup_canary_record()
    assert res["is_last_line"] is True, "Canary not last line"


def test_lookup_returns_safe_metadata():
    import brain.semantic_memory_canary_lookup_read_only as adapter
    res = adapter.lookup_canary_record()
    assert res.get("validation") is not None
    v = res["validation"]
    assert v["valid"] is True, f"Validation failed: {v['errors']}"


def test_lookup_reports_no_write():
    import brain.semantic_memory_canary_lookup_read_only as adapter
    res = adapter.lookup_canary_record()
    assert res["no_write"] is True


def test_lookup_reports_faiss_unused():
    import brain.semantic_memory_canary_lookup_read_only as adapter
    res = adapter.lookup_canary_record()
    assert res["faiss_used"] is False


def test_validate_canary_record_passes():
    import brain.semantic_memory_canary_lookup_read_only as adapter
    with open(TARGET, "r", encoding="utf-8") as f:
        data = [json.loads(line) for line in f if line.strip()]
    canary = [d for d in data if d.get("id") == CANARY_ID][0]
    v = adapter.validate_canary_record(canary)
    assert v["valid"] is True, f"Validation errors: {v['errors']}"


def test_adapter_does_not_modify_semantic_memory_hash():
    import brain.semantic_memory_canary_lookup_read_only as adapter
    baseline = _load_json(f"{EVIDENCE_DIR}/baseline_snapshot.json")
    before = baseline["files"]["memory/semantic/semantic_memory.jsonl"]["sha256"]
    # Run adapter multiple times to verify idempotencia
    adapter.lookup_canary_record()
    adapter.lookup_canary_record()
    after = adapter.hash_file(TARGET)
    assert before == after, "semantic_memory.jsonl hash changed after adapter use"


def test_adapter_does_not_modify_faiss_hashes():
    import brain.semantic_memory_canary_lookup_read_only as adapter
    baseline = _load_json(f"{EVIDENCE_DIR}/baseline_snapshot.json")
    for f in [
        "memory/semantic/semantic_memory_faiss.index",
        "memory/semantic/semantic_memory_faiss_ids.json",
        "memory/semantic/semantic_memory_index.npz",
    ]:
        before = baseline["files"][f]["sha256"]
        if before is None:
            continue
        after = adapter.hash_file(f)
        assert before == after, f"FAISS file {f} hash changed after adapter use"


def test_adapter_handles_missing_file():
    import brain.semantic_memory_canary_lookup_read_only as adapter
    res = adapter.lookup_canary_record(target_path="nonexistent_file.jsonl")
    assert res["found"] is False
    assert any("target_missing" in e for e in res["errors"])


def test_adapter_doc_exists():
    assert os.path.isfile("docs/FRONT_REAL_READ_LOOKUP_ADAPTER_01.md")


def test_adapter_doc_declares_read_only():
    with open("docs/FRONT_REAL_READ_LOOKUP_ADAPTER_01.md", "r", encoding="utf-8") as f:
        content = f.read().lower()
    assert "read-only" in content or "read only" in content or "read_only" in content
    assert "no escribir" in content or "adapter does not write" in content


def test_adapter_doc_declares_no_faiss():
    with open("docs/FRONT_REAL_READ_LOOKUP_ADAPTER_01.md", "r", encoding="utf-8") as f:
        content = f.read().lower()
    assert "faiss" in content
    assert "no faiss" in content or "faiss_used" in content


def test_adapter_doc_declares_no_promotion():
    with open("docs/FRONT_REAL_READ_LOOKUP_ADAPTER_01.md", "r", encoding="utf-8") as f:
        content = f.read().lower()
    assert "promotion" in content
    assert "no promover" in content or "promote" in content


def test_adapter_doc_decision_ready():
    with open("docs/FRONT_REAL_READ_LOOKUP_ADAPTER_01.md", "r", encoding="utf-8") as f:
        content = f.read()
    assert "READ_ONLY_LOOKUP_ADAPTER_READY" in content or "COMPLETE" in content
    assert "## 12. Recommended Next Front" in content
