"""Smoke test for FRONT-REAL-RUNTIME-LOOKUP-ENDPOINT-INTEGRATION-01."""

import hashlib
import json
import os
import sys

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, "tmp_agent/brain_v9")
sys.path.insert(0, os.getcwd())

from routes.canary_lookup_read_only import router as canary_router

DOCUMENT_PATH = "docs/FRONT_REAL_RUNTIME_LOOKUP_ENDPOINT_INTEGRATION_01.md"
MAIN_PY_PATH = "tmp_agent/brain_v9/main.py"
SEMANTIC_MEMORY = "memory/semantic/semantic_memory.jsonl"


@pytest.fixture(scope="module")
def baseline_hashes():
    """Read baseline hashes from FASE B snapshot."""
    with open(
        "tmp_agent/front_real_runtime_lookup_endpoint_integration_01/baseline_snapshot.json",
        "r",
        encoding="utf-8",
    ) as f:
        data = json.load(f)
    return data["files"]


def test_main_py_exists():
    assert os.path.isfile(MAIN_PY_PATH)


def test_canary_router_is_importable():
    assert canary_router is not None


def test_main_contains_canary_router_import():
    with open(MAIN_PY_PATH, "r", encoding="utf-8") as f:
        content = f.read()
    assert "from brain_v9.routes.canary_lookup_read_only import router as canary_lookup_read_only_router" in content


def test_main_contains_include_router():
    with open(MAIN_PY_PATH, "r", encoding="utf-8") as f:
        content = f.read()
    assert "app.include_router(canary_lookup_read_only_router)" in content


def test_testclient_can_call_endpoint():
    app = FastAPI()
    app.include_router(canary_router)
    client = TestClient(app)
    response = client.get("/brain/read-only/canary")
    assert response.status_code == 200


def test_endpoint_returns_200():
    app = FastAPI()
    app.include_router(canary_router)
    client = TestClient(app)
    response = client.get("/brain/read-only/canary")
    assert response.status_code == 200


def test_endpoint_found_true():
    app = FastAPI()
    app.include_router(canary_router)
    client = TestClient(app)
    response = client.get("/brain/read-only/canary")
    data = response.json()
    assert data.get("found") is True


def test_endpoint_count_one():
    app = FastAPI()
    app.include_router(canary_router)
    client = TestClient(app)
    response = client.get("/brain/read-only/canary")
    data = response.json()
    assert data.get("count") == 1


def test_endpoint_validation_valid():
    app = FastAPI()
    app.include_router(canary_router)
    client = TestClient(app)
    response = client.get("/brain/read-only/canary")
    data = response.json()
    assert data.get("validation", {}).get("valid") is True


def test_endpoint_reports_no_write():
    app = FastAPI()
    app.include_router(canary_router)
    client = TestClient(app)
    response = client.get("/brain/read-only/canary")
    data = response.json()
    assert data.get("no_write") is True


def test_endpoint_reports_faiss_unused():
    app = FastAPI()
    app.include_router(canary_router)
    client = TestClient(app)
    response = client.get("/brain/read-only/canary")
    data = response.json()
    assert data.get("faiss_used") is False


def test_endpoint_does_not_expose_full_text():
    app = FastAPI()
    app.include_router(canary_router)
    client = TestClient(app)
    response = client.get("/brain/read-only/canary")
    data = response.json()
    assert "full_text" not in data


def test_doc_exists():
    assert os.path.isfile(DOCUMENT_PATH)


def test_doc_declares_read_only():
    with open(DOCUMENT_PATH, "r", encoding="utf-8") as f:
        content = f.read().lower()
    assert "read-only" in content


def test_doc_declares_no_faiss():
    with open(DOCUMENT_PATH, "r", encoding="utf-8") as f:
        content = f.read().lower()
    assert "no faiss" in content or "does not import faiss" in content


def test_doc_decision_integrated():
    with open(DOCUMENT_PATH, "r", encoding="utf-8") as f:
        content = f.read()
    assert "RUNTIME_LOOKUP_ENDPOINT_INTEGRATED" in content


def test_no_memory_or_faiss_staged():
    import subprocess
    staged = subprocess.run(
        ["git", "diff", "--cached", "--name-status"], capture_output=True, text=True
    ).stdout
    assert "memory/semantic/semantic_memory.jsonl" not in staged
    assert "semantic_memory_faiss" not in staged


def test_semantic_memory_hash_unchanged(baseline_hashes):
    with open(SEMANTIC_MEMORY, "rb") as f:
        current_hash = hashlib.sha256(f.read()).hexdigest()
    assert current_hash == baseline_hashes["semantic_memory.jsonl"]["sha256"]


def test_faiss_index_hash_unchanged(baseline_hashes):
    with open("memory/semantic/semantic_memory_faiss.index", "rb") as f:
        current_hash = hashlib.sha256(f.read()).hexdigest()
    assert current_hash == baseline_hashes["semantic_memory_faiss.index"]["sha256"]


def test_faiss_ids_hash_unchanged(baseline_hashes):
    with open("memory/semantic/semantic_memory_faiss_ids.json", "rb") as f:
        current_hash = hashlib.sha256(f.read()).hexdigest()
    assert current_hash == baseline_hashes["semantic_memory_faiss_ids.json"]["sha256"]


def test_faiss_npz_hash_unchanged(baseline_hashes):
    with open("memory/semantic/semantic_memory_index.npz", "rb") as f:
        current_hash = hashlib.sha256(f.read()).hexdigest()
    assert current_hash == baseline_hashes["semantic_memory_index.npz"]["sha256"]
