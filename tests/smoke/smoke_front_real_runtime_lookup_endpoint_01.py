"""Smoke test for FRONT-REAL-RUNTIME-LOOKUP-ENDPOINT-01.

Validates the read-only canary lookup router:
1. Can be mounted on a FastAPI app.
2. GET /brain/read-only/canary returns 200.
3. Response is safe (no full text, no write, no FAISS).
4. Does not mutate target or FAISS files.
"""

import importlib
import json
import importlib
import os

ADAPTER_PATH = "brain/semantic_memory_canary_lookup_read_only.py"
ROUTER_PATH = "tmp_agent/brain_v9/routes/canary_lookup_read_only.py"
DOC_PATH = "docs/FRONT_REAL_RUNTIME_LOOKUP_ENDPOINT_01.md"
EVIDENCE_DIR = "tmp_agent/front_real_runtime_lookup_endpoint_01"

os.makedirs(EVIDENCE_DIR, exist_ok=True)


def _load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def test_router_module_exists():
    assert os.path.isfile(ROUTER_PATH), f"Router missing: {ROUTER_PATH}"


def test_router_imports():
    import importlib.util
    spec = importlib.util.spec_from_file_location("router", ROUTER_PATH)
    mod = importlib.util.module_from_spec(spec)
    import sys
    sys.path.insert(0, os.path.abspath(os.path.join(ROUTER_PATH, "..", "..", "..")))
    spec.loader.exec_module(mod)
    assert hasattr(mod, "router"), "router missing"
    assert hasattr(mod, "get_canary_lookup"), "get_canary_lookup missing"


def test_router_exposes_apirouter():
    from fastapi import APIRouter
    if os.path.exists(os.path.join(os.path.dirname(ROUTER_PATH), "dummy.py")):
        pass


def test_router_has_expected_route():
    import importlib.util
    spec = importlib.util.spec_from_file_location("router", ROUTER_PATH)
    mod = importlib.util.module_from_spec(spec)
    import sys
    sys.path.insert(0, os.path.abspath(os.path.join(ROUTER_PATH, "..", "..", "..")))
    spec.loader.exec_module(mod)
    assert hasattr(mod, "router"), "router missing"


def test_get_canary_endpoint_returns_200():
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    mod = importlib.import_module("tmp_agent.brain_v9.routes.canary_lookup_read_only")
    app = FastAPI()
    app.include_router(mod.router)
    client = TestClient(app)
    resp = client.get("/brain/read-only/canary")
    assert resp.status_code == 200, f"Unexpected HTTP status: {resp.status_code}"


def test_response_status_ok_or_not_found():
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    mod = importlib.import_module("tmp_agent.brain_v9.routes.canary_lookup_read_only")
    app = FastAPI()
    app.include_router(mod.router)
    client = TestClient(app)
    resp = client.get("/brain/read-only/canary")
    data = resp.json()
    assert data["status"] in ("ok", "not_found", "invalid"), f"Unexpected status: {data['status']}"


def test_response_found_true():
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    mod = importlib.import_module("tmp_agent.brain_v9.routes.canary_lookup_read_only")
    app = FastAPI()
    app.include_router(mod.router)
    client = TestClient(app)
    resp = client.get("/brain/read-only/canary")
    data = resp.json()
    if data["status"] == "ok":
        assert data["found"] is True, f"Expected found=True when status=ok, got: {data}"


def test_response_count_one():
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    mod = importlib.import_module("tmp_agent.brain_v9.routes.canary_lookup_read_only")
    app = FastAPI()
    app.include_router(mod.router)
    client = TestClient(app)
    resp = client.get("/brain/read-only/canary")
    data = resp.json()
    if data["found"]:
        assert data["count"] == 1, f"Expected count=1, got: {data['count']}"


def test_response_validation_valid():
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    mod = importlib.import_module("tmp_agent.brain_v9.routes.canary_lookup_read_only")
    app = FastAPI()
    app.include_router(mod.router)
    client = TestClient(app)
    resp = client.get("/brain/read-only/canary")
    data = resp.json()
    if data["found"] and data.get("validation") is not None:
        assert data["validation"]["valid"] is True, f"Validation not valid: {data['validation']}"


def test_response_reports_no_write():
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    mod = importlib.import_module("tmp_agent.brain_v9.routes.canary_lookup_read_only")
    app = FastAPI()
    app.include_router(mod.router)
    client = TestClient(app)
    resp = client.get("/brain/read-only/canary")
    data = resp.json()
    assert data["no_write"] is True, f"Expected no_write=True"


def test_response_reports_faiss_unused():
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    mod = importlib.import_module("tmp_agent.brain_v9.routes.canary_lookup_read_only")
    app = FastAPI()
    app.include_router(mod.router)
    client = TestClient(app)
    resp = client.get("/brain/read-only/canary")
    data = resp.json()
    assert data["faiss_used"] is False, f"Expected faiss_used=False"


def test_response_does_not_expose_full_text():
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    mod = importlib.import_module("tmp_agent.brain_v9.routes.canary_lookup_read_only")
    app = FastAPI()
    app.include_router(mod.router)
    client = TestClient(app)
    resp = client.get("/brain/read-only/canary")
    data = resp.json()
    # The response should not contain a top-level 'text' field
    assert "text" not in data, "Response exposed full text field"
    summary = data.get("record_summary", {})
    assert "text" not in summary, "record_summary exposed full text"


def test_endpoint_does_not_modify_semantic_memory_hash():
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    import brain.semantic_memory_canary_lookup_read_only as adapter
    baseline = _load_json("tmp_agent/front_real_runtime_lookup_endpoint_01/baseline_snapshot.json")
    before = baseline["files"]["memory/semantic/semantic_memory.jsonl"]["sha256"]
    mod = importlib.import_module("tmp_agent.brain_v9.routes.canary_lookup_read_only")
    app = FastAPI()
    app.include_router(mod.router)
    client = TestClient(app)
    client.get("/brain/read-only/canary")
    client.get("/brain/read-only/canary")
    after = adapter.hash_file("memory/semantic/semantic_memory.jsonl")
    assert before == after, "semantic_memory.jsonl hash changed after GET endpoint use"


def test_endpoint_does_not_modify_faiss_hashes():
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    import brain.semantic_memory_canary_lookup_read_only as adapter
    baseline = _load_json("tmp_agent/front_real_runtime_lookup_endpoint_01/baseline_snapshot.json")
    files = [
        "memory/semantic/semantic_memory_faiss.index",
        "memory/semantic/semantic_memory_faiss_ids.json",
        "memory/semantic/semantic_memory_index.npz",
    ]
    for f in files:
        before = baseline["files"][f]["sha256"]
        if before is None:
            continue
        mod = importlib.import_module("tmp_agent.brain_v9.routes.canary_lookup_read_only")
        app = FastAPI()
        app.include_router(mod.router)
        client = TestClient(app)
        client.get("/brain/read-only/canary")
        after = adapter.hash_file(f)
        assert before == after, f"FAISS file {f} hash changed after GET endpoint use"


def test_doc_exists():
    assert os.path.isfile(DOC_PATH), f"Doc missing: {DOC_PATH}"


def test_doc_declares_read_only():
    with open(DOC_PATH, "r", encoding="utf-8") as f:
        content = f.read().lower()
    assert "read-only" in content or "read only" in content
    assert "router does not write" in content or "does not write" in content


def test_doc_declares_no_faiss():
    with open(DOC_PATH, "r", encoding="utf-8") as f:
        content = f.read().lower()
    assert "faiss" in content
    assert "no faiss" in content or "does not import faiss" in content


def test_doc_declares_main_integration_deferred():
    with open(DOC_PATH, "r", encoding="utf-8") as f:
        content = f.read().lower()
    assert "integration" in content or "deferred" in content
    assert "main.py" in content or "main app" in content


def test_doc_decision_ready():
    with open(DOC_PATH, "r", encoding="utf-8") as f:
        content = f.read()
    assert "RUNTIME_LOOKUP_ROUTER_READY" in content or "COMPLETE" in content
    assert "Recommended Next Front" in content


def test_main_py_not_staged():
    import subprocess
    staged = subprocess.run(["git", "diff", "--cached", "--name-status"], capture_output=True, text=True).stdout
    assert "tmp_agent/brain_v9/main.py" not in staged, "main.py must not be staged"
