"""Smoke/static checks for curated read-only lookup endpoints."""

from __future__ import annotations

import hashlib
import importlib
import re
import sys
from pathlib import Path

from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[2]
MAIN_PY = ROOT / "tmp_agent" / "brain_v9" / "main.py"
BRAIN_V9 = ROOT / "tmp_agent" / "brain_v9"
FIXTURE_INDEX = ROOT / "tests" / "fixtures" / "readonly_lookup_index.jsonl"
SEMANTIC_DIR = ROOT / "memory" / "semantic"

if str(BRAIN_V9) not in sys.path:
    sys.path.insert(0, str(BRAIN_V9))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _main_text() -> str:
    return MAIN_PY.read_text(encoding="utf-8")


def _endpoint_block(func_name: str) -> str:
    text = _main_text()
    start = text.find(f"async def {func_name}(")
    assert start >= 0, f"{func_name} not found"
    next_route = text.find("\n@app.", start + 1)
    if next_route == -1:
        next_route = len(text)
    return text[start:next_route]


def _hash_path(path: Path) -> str:
    if not path.exists():
        return ""
    if path.is_file():
        return hashlib.sha256(path.read_bytes()).hexdigest()
    digest = hashlib.sha256()
    for item in sorted(path.rglob("*")):
        if item.is_file():
            digest.update(item.relative_to(path).as_posix().encode("utf-8"))
            digest.update(item.read_bytes())
    return digest.hexdigest()


def _client(monkeypatch) -> TestClient:
    for path in (str(ROOT), str(BRAIN_V9)):
        while path in sys.path:
            sys.path.remove(path)
    sys.path.insert(0, str(BRAIN_V9))
    sys.path.insert(0, str(ROOT))
    cached_brain = sys.modules.get("brain")
    cached_path = str(getattr(cached_brain, "__file__", "")) if cached_brain else ""
    if cached_path and "tmp_agent" in cached_path and "brain_v9" in cached_path:
        for name in list(sys.modules):
            if name == "brain" or name.startswith("brain."):
                sys.modules.pop(name, None)
    importlib.invalidate_caches()
    import brain.curated_runtime_lookup as lookup

    monkeypatch.setattr(lookup, "DEFAULT_LOOKUP_INDEX_PATH", FIXTURE_INDEX)
    cached_main = sys.modules.get("main")
    cached_main_path = str(getattr(cached_main, "__file__", "")) if cached_main else ""
    if cached_main_path and cached_main_path == str(ROOT / "main.py"):
        sys.modules.pop("main", None)
    for path in (str(ROOT), str(BRAIN_V9)):
        while path in sys.path:
            sys.path.remove(path)
    sys.path.insert(0, str(ROOT))
    sys.path.insert(0, str(BRAIN_V9))
    importlib.invalidate_caches()
    import main

    monkeypatch.setattr(main, "DEFAULT_LOOKUP_INDEX_PATH", FIXTURE_INDEX)
    return TestClient(main.app)


def test_main_contains_curated_status_endpoint():
    text = _main_text()
    assert '@app.get("/brain/curated-knowledge/status")' in text


def test_main_contains_curated_search_endpoint():
    text = _main_text()
    assert '@app.post("/brain/curated-knowledge/search")' in text


def test_curated_endpoints_use_operator_access():
    status_block = _endpoint_block("brain_curated_knowledge_status")
    search_block = _endpoint_block("brain_curated_knowledge_search")
    assert "_operator: OperatorAccess" in status_block
    assert "_operator: OperatorAccess" in search_block


def test_search_empty_query_raises_http_400(monkeypatch):
    response = _client(monkeypatch).post("/brain/curated-knowledge/search", json={"query": "   "})
    assert response.status_code == 400
    assert response.json()["detail"] == "query is required"


def test_curated_endpoints_have_no_llm_fallback():
    combined = (
        _endpoint_block("brain_curated_knowledge_status")
        + _endpoint_block("brain_curated_knowledge_search")
    ).lower()
    forbidden = ("llm", "model_priority", "session.chat", "openai", "ollama", "fallback")
    assert not any(term in combined for term in forbidden)


def test_curated_endpoints_do_not_write_memory_or_semantic():
    combined = _main_text()
    status_start = combined.find('def _curated_knowledge_status_payload(')
    search_end = combined.find('@app.get("/brain/semantic-memory/search")')
    block = combined[status_start:search_end]
    forbidden_patterns = (
        r"write_text",
        r"open\(.+['\"]w",
        r"ingest_text",
        r"semantic_memory_adapter_real",
        r"semantic_memory_bridge",
        r"SemanticMemoryFAISS",
    )
    assert not any(re.search(pattern, block) for pattern in forbidden_patterns)


def test_main_uses_load_curated_lookup_index():
    assert "load_curated_lookup_index" in _main_text()


def test_main_uses_search_curated_candidates():
    assert "search_curated_candidates" in _main_text()


def test_curated_endpoint_label_present():
    assert "verified_curated_readonly" in _main_text()


def test_curated_endpoint_write_flags_false():
    text = _main_text()
    assert '"real_write_allowed": REAL_WRITE_ALLOWED' in text
    assert '"faiss_write_allowed": FAISS_WRITE_ALLOWED' in text
    assert "REAL_WRITE_ALLOWED = True" not in text
    assert "FAISS_WRITE_ALLOWED = True" not in text


def test_curated_knowledge_status_readonly(monkeypatch):
    before_semantic = _hash_path(SEMANTIC_DIR)
    before_index = _hash_path(FIXTURE_INDEX)

    response = _client(monkeypatch).get("/brain/curated-knowledge/status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["label"] == "verified_curated_readonly"
    assert payload["index_exists"] is True
    assert payload["real_write_allowed"] is False
    assert payload["faiss_write_allowed"] is False
    assert payload["total_records"] >= payload["allowed_records"]
    assert _hash_path(SEMANTIC_DIR) == before_semantic
    assert _hash_path(FIXTURE_INDEX) == before_index


def test_curated_knowledge_search_readonly(monkeypatch):
    before_semantic = _hash_path(SEMANTIC_DIR)
    before_index = _hash_path(FIXTURE_INDEX)

    response = _client(monkeypatch).post(
        "/brain/curated-knowledge/search",
        json={"query": "promotion gate", "top_k": 5, "include_stale": True},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["label"] == "verified_curated_readonly"
    assert payload["real_write_allowed"] is False
    assert payload["faiss_write_allowed"] is False
    assert payload["result_count"] > 0
    for result in payload["results"]:
        assert result["label"] == "verified_curated_readonly"
        assert result["state"] in {"dry_run_verified", "ready_for_readonly_runtime_lookup"}
        assert result["evidence_refs"]
    assert _hash_path(SEMANTIC_DIR) == before_semantic
    assert _hash_path(FIXTURE_INDEX) == before_index
