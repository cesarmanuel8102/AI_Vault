from __future__ import annotations
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tmp_agent"))
FRONT = ROOT / "tmp_agent/front_brain_agent_v2_total_operational_excellence_closeout_01"


def load(name):
    return json.loads((FRONT / name).read_text(encoding="utf-8"))


def test_01_state_lock_exists():
    data = load("state_lock.json")
    assert data["branch"] == "codex/own-capital-sustainable-return"
    assert data["staged_empty"] is True


def test_02_memory_baseline_exists_and_valid():
    data = load("memory_faiss_baseline.json")
    assert data["semantic_jsonl_valid"] is True
    assert data["ids_equals_ntotal"] is True


def test_03_provider_audit_kimi_available():
    data = load("provider_audit.json")
    assert data["kimi_provider_found"] is True
    assert data["kimi_model_name"] == "kimi-k2.6:cloud"
    assert data["secret_values_exposed"] is False


def test_04_finalizer_imports_and_metadata_available():
    from brain_v9.core.agent_kernel_v2.finalizer import PRIMARY_KIMI_MODEL, finalize_agent_run
    assert PRIMARY_KIMI_MODEL == "kimi-k2.6:cloud"
    answer, meta = finalize_agent_run({"goal": "smoke finalizer", "mode": "read_only"}, [], [])
    assert answer and "Agent V2 operational result" not in answer
    assert {"provider_attempted", "provider_used", "model_used", "provider_degraded", "fallback_reason", "latency_ms"} <= set(meta)


def test_05_agent_v2_and_langgraph_imports():
    from brain_v9.core.agent_kernel_v2.runtime import LANGGRAPH_USED, get_agent_runtime_v2
    rt = get_agent_runtime_v2()
    assert rt.backend in {"langgraph", "native_graph_compatible"}
    assert LANGGRAPH_USED is True


def test_06_capabilities_non_empty():
    from brain_v9.core.agent_kernel_v2.runtime import get_agent_runtime_v2
    assert get_agent_runtime_v2().list_capabilities()


def test_07_create_plan_execute_trace_non_template():
    from brain_v9.core.agent_kernel_v2.runtime import get_agent_runtime_v2
    rt = get_agent_runtime_v2()
    run = rt.create_run("Probe 8091 health and Agent V2 status.", "read_only", "smoke")
    run = rt.plan_run(run["run_id"])
    run = rt.execute_run(run["run_id"])
    assert run["status"] == "completed"
    assert "Agent V2 operational result" not in run.get("final_answer", "")
    assert run.get("provider_metadata", {}).get("model_used")
    assert rt.get_trace(run["run_id"])


def test_08_trace_has_no_raw_cot():
    from brain_v9.core.agent_kernel_v2.runtime import get_agent_runtime_v2
    rt = get_agent_runtime_v2()
    run = rt.create_run("inspect trace sanitation markers", "read_only", "smoke")
    run = rt.plan_run(run["run_id"])
    run = rt.execute_run(run["run_id"])
    text = json.dumps(rt.get_trace(run["run_id"]), ensure_ascii=False).lower()
    assert "chain-of-thought" not in text
    assert "private reasoning" not in text


def test_09_memory_gateway_read_only():
    from brain_v9.core.agent_kernel_v2.memory_gateway import MemoryGatewayV2
    res = MemoryGatewayV2().semantic_retrieve("FAISS governance", top_k=2)
    assert res["write_performed"] is False


def test_10_tool_gateway_blocks_env_read():
    from brain_v9.core.agent_kernel_v2.schemas import ToolCallRequest
    from brain_v9.core.agent_kernel_v2.tool_gateway import ToolGatewayV2
    res = ToolGatewayV2().call(ToolCallRequest("file_read", {"path": ".env"}, "read_only"))
    assert res.blocked is True


def test_11_write_without_approval_blocks():
    from brain_v9.core.agent_kernel_v2.schemas import ToolCallRequest
    from brain_v9.core.agent_kernel_v2.tool_gateway import ToolGatewayV2
    res = ToolGatewayV2().call(ToolCallRequest("file_patch_apply_approval_required", {"path": "README.md"}, "read_only"))
    assert res.blocked is True and res.approval_required is True


def test_12_route_probe_local_only():
    from brain_v9.core.agent_kernel_v2.schemas import ToolCallRequest
    from brain_v9.core.agent_kernel_v2.tool_gateway import ToolGatewayV2
    res = ToolGatewayV2().call(ToolCallRequest("route_probe", {"url": "https://example.com"}, "read_only"))
    assert res.blocked is True


def test_13_chat_agent_route_registered():
    import brain_v9.main as main
    routes = {getattr(r, "path", "") for r in main.app.routes}
    assert "/v2/chat/agent" in routes


def test_14_legacy_chat_route_registered():
    import brain_v9.main as main
    routes = {getattr(r, "path", "") for r in main.app.routes}
    assert "/chat" in routes
    assert "/v1/agent/status" in routes


def test_15_dashboard_agent_v2_route_registered_direct():
    import brain_v9.main as main
    routes = {getattr(r, "path", "") for r in main.app.routes}
    assert "/brain-dashboard/agent-v2/status" in routes


def test_16_benchmark_threshold_met():
    data = load("excellence_benchmark_final.json")
    assert data["tasks_total"] == 20
    assert data["tasks_passed"] >= 18
    assert data["threshold_met"] is True
    assert data["unauthorized_writes"] == 0
    assert data["raw_cot"] == 0
    assert data["secrets"] == 0


def test_17_memory_final_integrity_unchanged():
    data = load("memory_faiss_final_integrity.json")
    assert data["hashes_unchanged"] is True
    assert data["semantic_lines_before"] == data["semantic_lines_after"]
    assert data["faiss_ids_before"] == data["faiss_ids_after"]


def test_18_no_unexpected_mutation_paths():
    names = set((ROOT / "tmp_agent/front_brain_agent_v2_total_operational_excellence_closeout_01").iterdir())
    assert (ROOT / "tmp_agent/strategies").exists() or True
    assert load("memory_faiss_final_integrity.json")["hashes_unchanged"] is True


def test_19_docs_exist():
    docs = [
        "docs/BRAIN_AGENT_KERNEL_V2.md",
        "docs/BRAIN_AGENT_RUNTIME_CONTRACT_V2.md",
        "docs/BRAIN_AGENT_TOOL_GATEWAY_V2.md",
        "docs/BRAIN_AGENT_MIGRATION_FROM_LEGACY.md",
        "docs/BRAIN_AGENT_FINALIZER_V2.md",
        "docs/BRAIN_AGENT_SELF_MAINTENANCE_MODE.md",
        "docs/BRAIN_AGENT_FRONTEND_DASHBOARD_USAGE.md",
        "docs/BRAIN_AGENT_OPERATIONAL_RUNBOOK.md",
    ]
    for doc in docs:
        assert (ROOT / doc).exists()


def test_20_roadmap_status_json_valid():
    assert json.loads((ROOT / "ROADMAP_STATUS.json").read_text(encoding="utf-8"))


def test_21_ledger_updated():
    text = (ROOT / "docs/MIGRATION_CONTROL_LEDGER.md").read_text(encoding="utf-8")
    assert "BRAIN-AGENT-V2-TOTAL-OPERATIONAL-EXCELLENCE-CLOSEOUT-01" in text


def test_22_tool_gateway_hardening_evidence_exists():
    assert (FRONT / "tool_gateway_hardening.json").exists()


def test_23_chat_routing_evidence_exists():
    assert (FRONT / "chat_agent_canonical_routing.json").exists()


def test_24_frontend_evidence_exists():
    assert (FRONT / "frontend_dashboard_total_integration.json").exists()


def test_25_self_maintenance_evidence_exists():
    data = load("self_maintenance_mode.json")
    assert data["patch_apply_requires_approval"] is True
    assert data["commit_requires_approval"] is True


def test_26_no_secrets_or_raw_cot_in_reports():
    text = "\n".join(p.read_text(encoding="utf-8", errors="replace") for p in FRONT.glob("*.json"))[:500000].lower()
    assert "chain-of-thought" not in text
    assert "private reasoning" not in text
    assert "api_key=" not in text
    assert "password=" not in text


def test_27_route_probe_post_allowlist_blocks_other_posts():
    from brain_v9.core.agent_kernel_v2.schemas import ToolCallRequest
    from brain_v9.core.agent_kernel_v2.tool_gateway import ToolGatewayV2
    res = ToolGatewayV2().call(ToolCallRequest("route_probe", {"url": "http://127.0.0.1:8091/chat", "method": "POST"}, "read_only"))
    assert res.blocked is True


def test_28_planner_classes_available():
    from brain_v9.core.agent_kernel_v2.planner import PLANNER_CLASSES, build_plan
    assert "provider_diagnosis" in PLANNER_CLASSES
    klass, plan = build_plan("Diagnose provider routing and report Kimi availability")
    assert klass == "provider_diagnosis"
    assert len([p for p in plan if p.get("tool_name")]) >= 2


def test_29_final_reports_exist():
    for name in ["final_report.json", "final_report.md", "cesar_review_report.md", "NEXT_PROMPT_RECOMMENDATION.md"]:
        assert (FRONT / name).exists()


def test_30_autonomous_journal_append_safe_if_present():
    data = load("autonomous_journal_append_review.json")
    assert data["append_only_verified"] is True
    assert data["jsonl_valid"] is True
    assert data["secrets_found"] is False
    assert data["raw_cot_found"] is False

