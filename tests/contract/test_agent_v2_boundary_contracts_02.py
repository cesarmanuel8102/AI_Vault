import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tmp_agent"))


def test_chat_response_normalizer_preserves_required_top_level_contract():
    from brain_v9.core.agent_kernel_v2.response_normalizer import normalize_agent_v2_chat_response

    out = normalize_agent_v2_chat_response(
        {
            "run_id": "run_contract_001",
            "content": "respuesta",
            "provider_metadata": {"provider_used": "ollama_cloud", "model_used": "kimi-k2.6:cloud"},
            "classification": "direct_assistant",
        },
        backend="langgraph_parity",
        mode_requested="read_only",
    )

    required = {
        "ok",
        "canonical_agent_v2",
        "route",
        "run_id",
        "trace_url",
        "final_answer",
        "provider_metadata",
        "capability_metadata",
        "mode_requested",
        "mode_effective",
        "governance_decision",
        "tools_considered",
        "tools_executed",
        "tools_blocked",
        "backend_selected",
        "runtime_type",
        "error",
        "detail",
    }
    assert required.issubset(out.keys())
    assert out["route"] == "/v2/chat/agent"
    assert out["final_answer"] == "respuesta"
    assert out["backend_selected"] == "langgraph_parity"
    assert isinstance(out["provider_metadata"], dict)
    assert isinstance(out["capability_metadata"], dict)
    assert isinstance(out["tools_executed"], list)


def test_governance_policy_blocks_trading_and_gates_writes():
    from brain_v9.core.agent_kernel_v2.governance_policy import decide_governance

    trading = decide_governance("trading_broker_live", "read_only", "read_only")
    assert trading["governance_decision"] == "blocked"
    assert trading["safe_mode"] is True
    assert "trading" in trading["blocked_reason"].lower()

    write = decide_governance("code_change_request", "read_only", "read_only")
    assert write["governance_decision"] == "approval_required"
    assert write["required_permission"] == "build"
    assert write["approval_required"] is True

    autonomy = decide_governance("autonomy_dryrun", "auto", "auto")
    assert autonomy["governance_decision"] == "dry_run_only"
    assert autonomy["required_permission"] == "autonomy_dryrun"


def test_tool_gateway_capability_contract_and_read_only_write_block():
    from brain_v9.core.agent_kernel_v2.schemas import ToolCallRequest
    from brain_v9.core.agent_kernel_v2.tool_gateway import ToolGatewayV2

    gateway = ToolGatewayV2()
    caps = gateway.list_capabilities()
    names = {c["name"] for c in caps}

    assert {"repo_status_read", "file_read", "semantic_retrieve", "file_patch_apply_approval_required"}.issubset(names)
    for cap in caps:
        assert {"name", "description", "risk_level", "read_only", "requires_approval", "allowed_modes"}.issubset(cap)
        assert isinstance(cap["allowed_modes"], list)

    blocked = gateway.call(ToolCallRequest("file_patch_apply_approval_required", {"path": "README.md"}, "read_only"))
    assert blocked.ok is False
    assert blocked.blocked is True
    assert blocked.error == "write_tool_blocked_in_read_only_mode"


def test_memory_gateway_contract_is_read_only_with_jsonl_fallback(tmp_path, monkeypatch):
    from brain_v9.core.agent_kernel_v2 import memory_gateway as mg

    semantic_dir = tmp_path / "memory" / "semantic"
    semantic_dir.mkdir(parents=True)
    records = semantic_dir / "semantic_memory.jsonl"
    records.write_text(
        json.dumps(
            {
                "id": "mem_contract_001",
                "text": "FAISS governance requires snapshots and no direct writes.",
                "source": "contract",
                "kind": "lesson",
                "metadata": {"domain": "semantic_memory"},
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(mg, "ROOT", tmp_path)
    monkeypatch.setattr(mg, "SEM", records)
    monkeypatch.setattr(mg, "IDS", semantic_dir / "missing_ids.json")
    monkeypatch.setattr(mg, "IDX", semantic_dir / "missing.index")

    import brain_v9.core.semantic_memory_faiss as smf

    class FailingSemanticMemoryFAISS:
        def __init__(self, *args, **kwargs):
            raise RuntimeError("force_jsonl_fallback")

    monkeypatch.setattr(smf, "SemanticMemoryFAISS", FailingSemanticMemoryFAISS)

    gateway = mg.MemoryGatewayV2()
    result = gateway.semantic_retrieve("FAISS governance", top_k=2)
    assert result["ok"] is True
    assert result["write_performed"] is False
    assert result["backend"] == "jsonl_keyword"
    assert result["hits"]


def test_capability_report_contract_uses_truthful_safety_flags(monkeypatch):
    from brain_v9.core.agent_kernel_v2 import capability_registry as cr

    class RuntimeStub:
        backend = "langgraph_parity"
        backend_selected = "langgraph_parity"
        backend_default = "langgraph_parity"
        runtime_type = "LangGraphParityRuntimeV2"
        rollback_backend = "native_runtime"

    monkeypatch.setattr(cr, "_probe_ollama_reachable", lambda: True)
    report = cr.build_capability_report(RuntimeStub())

    assert report["ok"] is True
    assert report["canonical"] is True
    assert report["langgraph_default_active"] is True
    assert report["real_llm_available"] is True
    assert report["memory_read_available"] is True
    assert report["memory_write_allowed"] is False
    assert report["faiss_mutation_allowed"] is False
    assert report["trading_broker_allowed"] is False
    assert "kimi-k2.6:cloud" in report["provider_candidates"]
    assert report["available_tools_count"] == len(report["tools_available"])


def test_browser_ui_token_preflight_contract_static():
    html = (ROOT / "tmp_agent/brain_v9/ui/index.html").read_text(encoding="utf-8")

    assert "function requireOperatorTokenForChat()" in html
    assert "if (!requireOperatorTokenForChat()) return;" in html
    assert "'X-Brain-Token': getOperatorToken()" in html
    assert "AGENTV2_TEST_ADMIN_TOKEN_08F8_R1B" not in html

