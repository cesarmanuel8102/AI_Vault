"""
Smoke test: read-only lookup does not mutate anything.
"""
import hashlib
from pathlib import Path

from brain.curated_runtime_lookup import (
    format_curated_lookup_for_chat,
    load_curated_lookup_index,
    search_curated_candidates,
)

FIXTURE_INDEX = Path("tests/fixtures/readonly_lookup_index.jsonl")
SEMANTIC_DIR = Path("memory/semantic")


def _hash_file(path: Path) -> str:
    if not path.exists():
        return ""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _hash_dir(path: Path) -> str:
    if not path.exists():
        return ""
    h = hashlib.sha256()
    for p in sorted(path.rglob("*")):
        if p.is_file():
            h.update(p.read_bytes())
    return h.hexdigest()


def test_smoke_load_index_no_mutation():
    """Loading index does not modify semantic memory."""
    before = _hash_dir(SEMANTIC_DIR)
    records = load_curated_lookup_index(FIXTURE_INDEX)
    assert len(records) > 0
    after = _hash_dir(SEMANTIC_DIR)
    assert before == after, "semantic memory was mutated"


def test_smoke_search_no_mutation():
    """Searching does not modify semantic memory."""
    before = _hash_dir(SEMANTIC_DIR)
    record = search_curated_candidates("chat-ops", index_path=FIXTURE_INDEX)
    assert record.total_available > 0
    after = _hash_dir(SEMANTIC_DIR)
    assert before == after, "semantic memory was mutated by search"


def test_smoke_format_no_mutation():
    """Formatting does not modify semantic memory."""
    before = _hash_dir(SEMANTIC_DIR)
    record = search_curated_candidates("", index_path=FIXTURE_INDEX, top_k=2, include_stale=True)
    formatted = format_curated_lookup_for_chat(record)
    assert "verified_curated_readonly" in formatted
    after = _hash_dir(SEMANTIC_DIR)
    assert before == after, "semantic memory was mutated by format"


def test_smoke_blocked_states_not_returned():
    """Blocked/rejected/promoted records never appear."""
    record = search_curated_candidates("", index_path=FIXTURE_INDEX, top_k=10, include_stale=True)
    forbidden_states = {"blocked", "rejected", "deprecated", "promoted_real_write", "active_write", "discovered"}
    for r in record.results:
        assert r.state not in forbidden_states, f"forbidden state {r.state!r} returned"


def test_smoke_empty_index_controlled_response():
    """Non-existent index returns empty tuple, not error."""
    records = load_curated_lookup_index("nonexistent.jsonl")
    assert records == ()


def test_smoke_label_present():
    """Every result has the readonly label."""
    record = search_curated_candidates("", index_path=FIXTURE_INDEX, top_k=3, include_stale=True)
    for r in record.results:
        assert r.label == "verified_curated_readonly"


def test_smoke_provenance_required():
    """Records without provenance are filtered."""
    record = search_curated_candidates("", index_path=FIXTURE_INDEX, top_k=10, include_stale=True)
    for r in record.results:
        assert r.provenance_bundle, f"missing provenance for {r.candidate_id}"
        assert r.provenance_bundle.get("source_type"), f"missing source_type for {r.candidate_id}"


def test_smoke_faiss_unchanged():
    """FAISS index (if exists) is not modified."""
    faiss_path = SEMANTIC_DIR / "faiss_index.bin"
    if faiss_path.exists():
        before = _hash_file(faiss_path)
        search_curated_candidates("chat-ops", index_path=FIXTURE_INDEX)
        after = _hash_file(faiss_path)
        assert before == after, "FAISS index was mutated"
