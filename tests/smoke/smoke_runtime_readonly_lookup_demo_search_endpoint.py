"""Smoke/static checks for curated read-only demo-search endpoint."""

from __future__ import annotations

import hashlib
import importlib
import importlib.util
import re
import sys
from pathlib import Path

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[2]
BRAIN_V9 = ROOT / "tmp_agent" / "brain_v9"
MAIN_PY = ROOT / "tmp_agent" / "brain_v9" / "main.py"
DEMO_INDEX = ROOT / "tmp_agent" / "external_curated_ingestion_dry_run_demo_01_evidence" / "demo_readonly_lookup_index.jsonl"
SEMANTIC_DIR = ROOT / "memory" / "semantic"
FIXTURE_INDEX = ROOT / "tests" / "fixtures" / "readonly_lookup_index.jsonl"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(BRAIN_V9) not in sys.path:
    sys.path.insert(0, str(BRAIN_V9))


def _main_text() -> str:
    return MAIN_PY.read_text(encoding="utf-8")


def _endpoint_block(name: str) -> str:
    text = _main_text()
    marker = f"async def {name}("
    start = text.find(marker)
    assert start >= 0, f"{name} not found"
    next_route = text.find("\n@app.", start + 1)
    if next_route == -1:
        next_route = len(text)
    return text[start:next_route]


def _helper_block(name: str) -> str:
    text = _main_text()
    marker = f"def {name}("
    start = text.find(marker)
    assert start >= 0, f"{name} not found"
    next_def = text.find("\ndef ", start + 1)
    next_route = text.find("\n@app.", start + 1)
    candidates = [pos for pos in (next_def, next_route) if pos != -1]
    end = min(candidates) if candidates else len(text)
    return text[start:end]


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


def _import_main():
    tmp_agent = ROOT / "tmp_agent"
    for path in (str(ROOT), str(BRAIN_V9), str(tmp_agent)):
        while path in sys.path:
            sys.path.remove(path)
    sys.path.insert(0, str(ROOT))
    sys.path.insert(1, str(tmp_agent))
    cached_brain = sys.modules.get("brain")
    cached_path = str(getattr(cached_brain, "__file__", "")) if cached_brain else ""
    if cached_path and "tmp_agent" in cached_path and "brain_v9" in cached_path:
        for name in list(sys.modules):
            if name == "brain" or name.startswith("brain."):
                sys.modules.pop(name, None)
    importlib.invalidate_caches()
    module_name = "brain_v9_main_demo_search_smoke"
    sys.modules.pop(module_name, None)
    spec = importlib.util.spec_from_file_location(module_name, MAIN_PY)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _client() -> TestClient:
    main = _import_main()
    return TestClient(main.app)


def test_demo_search_endpoint_exists():
    assert '@app.post("/brain/curated-knowledge/demo-search")' in _main_text()


def test_demo_search_uses_operator_access():
    block = _endpoint_block("brain_curated_knowledge_demo_search")
    assert "_operator: OperatorAccess" in block


def test_request_model_contains_demo_fields():
    text = _main_text()
    assert "class CuratedKnowledgeDemoSearchRequest(BaseModel)" in text
    assert "demo_index_path: str" in text
    assert "demo_mode: bool = True" in text


def test_path_policy_rejects_dangerous_paths():
    main = _import_main()
    dangerous = [
        "../secret.jsonl",
        "memory/semantic/semantic_memory.jsonl",
        "tmp_agent/strategies/x.jsonl",
        "https://example.com/index.jsonl",
        "tmp_agent/demo.txt",
    ]
    for path in dangerous:
        with pytest.raises(HTTPException):
            main._resolve_demo_curated_index_path(path)


def test_path_policy_accepts_demo_evidence_index_if_present():
    assert DEMO_INDEX.exists(), "demo index fixture from dry-run demo is required"
    main = _import_main()
    resolved = main._resolve_demo_curated_index_path(str(DEMO_INDEX.relative_to(ROOT)))
    assert resolved == DEMO_INDEX.resolve()


def test_endpoint_calls_search_with_index_path():
    block = _endpoint_block("brain_curated_knowledge_demo_search")
    assert "search_curated_candidates" in block
    assert "index_path=resolved_demo_index_path" in block


def test_response_contains_demo_label_and_flags():
    block = _endpoint_block("brain_curated_knowledge_demo_search")
    assert "verified_curated_readonly_demo" in block
    assert '"real_write_allowed": False' in block
    assert '"faiss_write_allowed": False' in block
    assert '"global_config_mutated": False' in block
    assert '"automatic_context_injection": False' in block


def test_no_default_lookup_index_mutation():
    combined = _endpoint_block("brain_curated_knowledge_demo_search") + _helper_block("_resolve_demo_curated_index_path")
    assert "DEFAULT_LOOKUP_INDEX_PATH =" not in combined
    assert "DEFAULT_LOOKUP_INDEX_PATH" not in combined


def test_no_memory_semantic_or_faiss_writes():
    combined = _endpoint_block("brain_curated_knowledge_demo_search") + _helper_block("_resolve_demo_curated_index_path")
    forbidden = (
        r"write_text",
        r"open\(.+['\"]w",
        r"ingest_text",
        r"SemanticMemoryFAISS",
        r"write_index",
        r"semantic_memory_adapter_real",
        r"semantic_memory_bridge",
    )
    assert not any(re.search(pattern, combined) for pattern in forbidden)


def test_no_llm_fallback():
    block = _endpoint_block("brain_curated_knowledge_demo_search")
    forbidden = ("session.chat", "llm", "ollama", "openai", "_route_to_llm")
    assert not any(term in block.lower() for term in forbidden)


def test_productive_search_endpoint_still_exists():
    assert '@app.post("/brain/curated-knowledge/search")' in _main_text()


def test_chat_command_does_not_accept_path_by_chat():
    session_text = (ROOT / "tmp_agent" / "brain_v9" / "core" / "session.py").read_text(encoding="utf-8")
    assert "demo_index_path" not in session_text
    assert "busca en conocimiento curado demo" not in session_text


def test_demo_search_endpoint_readonly_response_and_no_mutation():
    before_semantic = _hash_path(SEMANTIC_DIR)
    before_demo = _hash_path(DEMO_INDEX)
    before_fixture = _hash_path(FIXTURE_INDEX)

    response = _client().post(
        "/brain/curated-knowledge/demo-search",
        json={
            "query": "concrete pavement traffic opening",
            "demo_index_path": str(DEMO_INDEX.relative_to(ROOT)),
            "top_k": 5,
            "demo_mode": True,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["label"] == "verified_curated_readonly_demo"
    assert payload["demo_mode"] is True
    assert payload["result_count"] >= 1
    assert payload["real_write_allowed"] is False
    assert payload["faiss_write_allowed"] is False
    assert payload["global_config_mutated"] is False
    assert payload["automatic_context_injection"] is False
    assert payload["results"][0]["label"] == "verified_curated_readonly"
    assert _hash_path(SEMANTIC_DIR) == before_semantic
    assert _hash_path(DEMO_INDEX) == before_demo
    assert _hash_path(FIXTURE_INDEX) == before_fixture


def test_demo_search_rejects_require_provenance_false():
    response = _client().post(
        "/brain/curated-knowledge/demo-search",
        json={
            "query": "concrete pavement traffic opening",
            "demo_index_path": str(DEMO_INDEX.relative_to(ROOT)),
            "require_provenance": False,
            "demo_mode": True,
        },
    )
    assert response.status_code == 400
