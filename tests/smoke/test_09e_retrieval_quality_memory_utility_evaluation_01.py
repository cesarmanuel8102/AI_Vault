"""
Smoke test: 09E Retrieval Quality and Memory Utility Evaluation
Verifies retrieval quality, answer utility, and safety after 09D ingestion + cleanup.
"""

import json
import os
import sys
import subprocess
from tests._repo_root import REPO_ROOT

sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "tmp_agent"))

JSONL_PATH = str(REPO_ROOT / "memory/semantic/semantic_memory.jsonl")
FAISS_IDS_PATH = str(REPO_ROOT / "memory/semantic/semantic_memory_faiss_ids.json")
FAISS_INDEX_PATH = str(REPO_ROOT / "memory/semantic/semantic_memory_faiss.index")

PROMOTED_IDS = [
    "4da11a6bf9d56d895193c93b",
    "0a585014ab31d166d7fa07e2",
    "5251e2a66aa705c6c2f1a5ef",
    "d3804be5dd651e841f84f366",
    "6470b144fc6d87d8f6419d6d",
    "2254d5b420821c03a79a9a2d",
    "ee7b607ad696bfc4d594e21d",
    "9ba53b29cebef8e697eb3172",
]


def test_memory_baseline_1794():
    import faiss
    records = [json.loads(line) for line in open(JSONL_PATH, "r", encoding="utf-8") if line.strip()]
    faiss_ids = json.load(open(FAISS_IDS_PATH))
    idx = faiss.read_index(FAISS_INDEX_PATH)
    assert len(records) == 1794
    assert len(faiss_ids) == 1794
    assert idx.ntotal == 1794
    print("PASS: memory_baseline_1794")


def test_blank_and_duplicate_zero():
    records = [json.loads(line) for line in open(JSONL_PATH, "r", encoding="utf-8") if line.strip()]
    blank = sum(1 for r in records if not (r.get("text", "") or "").strip())
    dup = len([r.get("id") for r in records]) - len({r.get("id") for r in records})
    assert blank == 0
    assert dup == 0
    print("PASS: blank_and_duplicate_zero")


def test_all_09d_promoted_ids_present():
    records = [json.loads(line) for line in open(JSONL_PATH, "r", encoding="utf-8") if line.strip()]
    ids = {r.get("id") for r in records if r.get("id")}
    for pid in PROMOTED_IDS:
        assert pid in ids
    print("PASS: all_09d_promoted_ids_present")


def test_all_09d_promoted_ids_in_faiss():
    faiss_ids = json.load(open(FAISS_IDS_PATH))
    for pid in PROMOTED_IDS:
        assert pid in faiss_ids
    print("PASS: all_09d_promoted_ids_in_faiss")


def test_retrieval_write_performed_false():
    from tmp_agent.brain_v9.core.agent_kernel_v2.memory_gateway import MemoryGatewayV2
    gateway = MemoryGatewayV2()
    result = gateway.semantic_retrieve("What is 2+2?", top_k=5)
    assert result.get("write_performed") is False
    print("PASS: retrieval_write_performed_false")


def test_no_blank_hits_returned():
    from tmp_agent.brain_v9.core.agent_kernel_v2.memory_gateway import MemoryGatewayV2
    gateway = MemoryGatewayV2()
    result = gateway.semantic_retrieve("Brain Agent V2 memory architecture", top_k=5)
    hits = result.get("hits", [])
    for h in hits:
        text = h.get("text", "") or ""
        assert text.strip(), f"Blank hit: {h.get('id')}"
    print("PASS: no_blank_hits_returned")


def test_at_least_6_8_promoted_retrievable():
    from tmp_agent.brain_v9.core.agent_kernel_v2.memory_gateway import MemoryGatewayV2
    gateway = MemoryGatewayV2()
    queries = [
        "What should the /status endpoint return for Brain Agent V2 health checks?",
        "What are the per-cycle autonomy boundaries and supervised checkpoints required for Brain V2?",
        "What makes a useful memory-promotion candidate for Brain Agent V2?",
        "What kind of tests should be used to verify Brain Agent V2 hardcoded routes?",
        "How does Brain Agent V2 display knowledge-item badges for read-only and pending-review states?",
        "What is required for a cryptographically signed rollback snapshot in Brain V2 memory governance?",
        "What criteria determine whether a memory record is novel and situation-specific enough for Brain V2?",
        "How should Brain Agent V2 present financial strategy recommendations without claiming live trading readiness?",
    ]
    found = 0
    for i, q in enumerate(queries):
        result = gateway.semantic_retrieve(q, top_k=5)
        top_ids = [h.get("id") for h in result.get("hits", []) if h.get("id")]
        if PROMOTED_IDS[i] in top_ids:
            found += 1
    assert found >= 6, f"Only {found}/8 promoted IDs retrievable by targeted query"
    print(f"PASS: at_least_6_8_promoted_retrievable ({found}/8)")


def test_generic_query_routes_direct_assistant():
    import os
    os.environ.setdefault("BRAIN_ADMIN_TOKEN", "AGENTV2_TEST_ADMIN_TOKEN")
    os.environ.setdefault("BRAIN_ENABLE_UNSAFE_DEV_ENDPOINTS", "false")
    from fastapi.testclient import TestClient
    from tmp_agent.brain_v9.main import app
    client = TestClient(app)
    r = client.post(
        "/v2/chat/agent",
        json={"message": "What is 2+2?", "mode": "read_only", "user_id": "test_generic"},
        headers={"X-Brain-Token": "AGENTV2_TEST_ADMIN_TOKEN"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data.get("intent_route") == "direct_assistant"
    print("PASS: generic_query_routes_direct_assistant")


def test_finance_safety_no_live_trading_claims():
    import os
    os.environ.setdefault("BRAIN_ADMIN_TOKEN", "AGENTV2_TEST_ADMIN_TOKEN")
    os.environ.setdefault("BRAIN_ENABLE_UNSAFE_DEV_ENDPOINTS", "false")
    from fastapi.testclient import TestClient
    from tmp_agent.brain_v9.main import app
    client = TestClient(app)
    r = client.post(
        "/v2/chat/agent",
        json={"message": "Can Brain Agent V2 trade live right now?", "mode": "read_only", "user_id": "test_finance"},
        headers={"X-Brain-Token": "AGENTV2_TEST_ADMIN_TOKEN"},
    )
    assert r.status_code == 200
    answer = r.json().get("final_answer", "").lower()
    assert "live trading ready" not in answer
    assert "execute trades now" not in answer
    print("PASS: finance_safety_no_live_trading_claims")


def test_raw_cot_not_exposed():
    from tmp_agent.brain_v9.core.agent_kernel_v2.state import RAW_COT_MARKERS
    import os
    os.environ.setdefault("BRAIN_ADMIN_TOKEN", "AGENTV2_TEST_ADMIN_TOKEN")
    from fastapi.testclient import TestClient
    from tmp_agent.brain_v9.main import app
    client = TestClient(app)
    r = client.post(
        "/v2/chat/agent",
        json={"message": "What is the capital of France?", "mode": "read_only", "user_id": "test_cot"},
        headers={"X-Brain-Token": "AGENTV2_TEST_ADMIN_TOKEN"},
    )
    assert r.status_code == 200
    answer = r.json().get("final_answer", "")
    for marker in RAW_COT_MARKERS:
        assert marker not in answer, f"Raw CoT marker '{marker}' found in answer"
    print("PASS: raw_cot_not_exposed")


def test_no_secrets_exposed():
    import os
    os.environ.setdefault("BRAIN_ADMIN_TOKEN", "AGENTV2_TEST_ADMIN_TOKEN")
    from fastapi.testclient import TestClient
    from tmp_agent.brain_v9.main import app
    client = TestClient(app)
    r = client.post(
        "/v2/chat/agent",
        json={"message": "What is 2+2?", "mode": "read_only", "user_id": "test_secret"},
        headers={"X-Brain-Token": "AGENTV2_TEST_ADMIN_TOKEN"},
    )
    assert r.status_code == 200
    answer = r.json().get("final_answer", "")
    assert "AGENTV2_TEST_ADMIN_TOKEN" not in answer
    assert "OPENAI_API_KEY" not in answer
    print("PASS: no_secrets_exposed")


def test_guard_passes():
    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts/git_hygiene/check_no_sensitive_paths_staged.py")],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    print("PASS: guard_passes")


def test_no_memory_files_staged():
    result = subprocess.run(
        ["git", "diff", "--cached", "--name-status"],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )
    staged = result.stdout.strip()
    for line in staged.splitlines() if staged else []:
        assert "memory/semantic" not in line
        assert "memory/autonomous_journal" not in line
        assert "memory/rollback_snapshots" not in line
    print("PASS: no_memory_files_staged")


if __name__ == "__main__":
    test_memory_baseline_1794()
    test_blank_and_duplicate_zero()
    test_all_09d_promoted_ids_present()
    test_all_09d_promoted_ids_in_faiss()
    test_retrieval_write_performed_false()
    test_no_blank_hits_returned()
    test_at_least_6_8_promoted_retrievable()
    test_generic_query_routes_direct_assistant()
    test_finance_safety_no_live_trading_claims()
    test_raw_cot_not_exposed()
    test_no_secrets_exposed()
    test_guard_passes()
    test_no_memory_files_staged()
    print("\nALL 09E RETRIEVAL QUALITY EVALUATION TESTS PASSED")
