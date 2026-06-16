import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
FRONT = ROOT / "tmp_agent/front_brain_agent_full_rebuild_langgraph_recursive_closeout_01"
sys.path.insert(0, str(ROOT / "tmp_agent"))

def j(name):
    return json.loads((FRONT / name).read_text(encoding="utf-8"))

def test_required_artifacts_and_docs_exist():
    for name in ["state_lock.json","memory_faiss_baseline.json","current_agent_failure_audit.json","langgraph_dependency_decision.json","agent_v2_architecture_contract.json","agent_v2_benchmark_final.json","endpoint_verification.json","memory_faiss_integrity_final.json"]:
        assert (FRONT / name).exists(), name
    for doc in ["docs/BRAIN_AGENT_KERNEL_V2.md","docs/BRAIN_AGENT_RUNTIME_CONTRACT_V2.md","docs/BRAIN_AGENT_TOOL_GATEWAY_V2.md","docs/BRAIN_AGENT_MIGRATION_FROM_LEGACY.md"]:
        assert (ROOT / doc).exists(), doc

def test_agent_v2_runtime_lifecycle_and_capabilities():
    from brain_v9.core.agent_kernel_v2.runtime import get_agent_runtime_v2, LANGGRAPH_USED
    rt = get_agent_runtime_v2()
    assert LANGGRAPH_USED is True
    assert rt.list_capabilities()
    r = rt.create_run("smoke create plan execute", mode="read_only", user_id="smoke")
    rt.plan_run(r["run_id"])
    out = rt.execute_run(r["run_id"])
    assert out["status"] == "completed"
    trace = rt.get_trace(r["run_id"])
    assert trace
    assert "chain-of-thought" not in json.dumps(trace).lower()
    p = rt.create_run("smoke lifecycle", mode="read_only", user_id="smoke")
    rt.pause_run(p["run_id"]); assert rt.get_run(p["run_id"])["status"] == "paused"
    rt.resume_run(p["run_id"]); assert rt.get_run(p["run_id"])["status"] == "running"
    rt.cancel_run(p["run_id"]); assert rt.get_run(p["run_id"])["status"] == "cancelled"

def test_memory_and_tool_gateways_safe():
    from brain_v9.core.agent_kernel_v2.memory_gateway import MemoryGatewayV2
    from brain_v9.core.agent_kernel_v2.tool_gateway import ToolGatewayV2
    from brain_v9.core.agent_kernel_v2.schemas import ToolCallRequest
    mem = MemoryGatewayV2()
    assert mem.integrity_check()["ids_equals_ntotal"] is True
    assert mem.semantic_retrieve("FAISS governance", 2)["write_performed"] is False
    res = ToolGatewayV2().call(ToolCallRequest(tool_name="file_patch_apply_approval_required", args={"path":"README.md"}, mode="read_only"))
    assert res.blocked is True and res.approval_required is True

def test_benchmark_endpoint_and_integrity_results():
    b = j("agent_v2_benchmark_final.json")
    assert b["threshold_met"] is True
    assert b["tasks_completed"] >= 11
    assert b["unauthorized_writes"] == 0
    assert b["raw_cot"] is False
    e = j("endpoint_verification.json")
    assert e["direct_app_route_registration"]["new_routes_registered"] is True
    m = j("memory_faiss_integrity_final.json")
    assert m["hashes_unchanged"] is True
    assert m["semantic_lines"] == j("memory_faiss_baseline.json")["semantic_lines"]

def test_scope_and_metadata_safe():
    final = j("final_report.json")
    assert final["safety"]["trading_touched"] is False
    assert final["safety"]["b8_touched"] is False
    assert final["safety"]["strategies_touched"] is False
    json.load(open(ROOT / "ROADMAP_STATUS.json", encoding="utf-8"))
    assert (ROOT / "docs/MIGRATION_CONTROL_LEDGER.md").exists()
    staged = subprocess.run(["git","diff","--cached","--name-only"], cwd=ROOT, text=True, capture_output=True, check=True).stdout
    for bad in [".env", "trading/", "B8/", "tmp_agent/strategies/", "memory/semantic/semantic_memory.jsonl", "memory/semantic/semantic_memory_faiss.index", "memory/semantic/semantic_memory_faiss_ids.json"]:
        assert bad not in staged
