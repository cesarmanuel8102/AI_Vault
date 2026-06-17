"""
Smoke test for FRONT-BRAIN-AGENT-V2-MANDATORY-MULTITOOL-PLANNER-HOTFIX-01
"""
import json
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))
EVIDENCE = os.path.join(ROOT, 'tmp_agent/front_brain_agent_v2_mandatory_multitool_planner_hotfix_01')

def _read_json(path):
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)

def test_evidence_dir_exists():
    assert os.path.isdir(EVIDENCE), f"Evidence dir missing: {EVIDENCE}"

def test_state_lock_exists():
    assert os.path.exists(os.path.join(EVIDENCE, 'state_lock.json'))

def test_mandatory_parser_exists():
    assert os.path.exists(os.path.join(ROOT, 'tmp_agent/brain_v9/core/agent_kernel_v2/mandatory_tools.py'))

def test_mandatory_parser_detects_mandatory():
    sys.path.insert(0, ROOT)
    from tmp_agent.brain_v9.core.agent_kernel_v2.mandatory_tools import parse_mandatory_tool_requests
    goal = "MANDATORY TOOL TEST.\nYou must perform all of these checks:\n1. Probe http://127.0.0.1:8091/v2/agent/status.\n2. Read repo status.\n3. Search code for kimi-k2.6 finalizer.\n4. Retrieve memory about FAISS governance."
    result = parse_mandatory_tool_requests(goal)
    assert result['mandatory_detected'] is True
    assert len(result['requested_checks']) >= 4

def test_mandatory_parser_produces_checks():
    sys.path.insert(0, ROOT)
    from tmp_agent.brain_v9.core.agent_kernel_v2.mandatory_tools import parse_mandatory_tool_requests
    goal = "MANDATORY TOOL TEST.\nYou must perform all of these checks:\n1. Probe http://127.0.0.1:8091/v2/agent/status.\n2. Probe http://127.0.0.1:8091/v2/agent/capabilities.\n3. Read repo status.\n4. Search code for kimi-k2.6 finalizer.\n5. Search code for /v2/chat/agent.\n6. Retrieve memory about FAISS governance."
    result = parse_mandatory_tool_requests(goal)
    assert len(result['requested_checks']) >= 6
    tools = [c['tool_name'] for c in result['requested_checks']]
    assert 'route_probe' in tools
    assert 'repo_status_read' in tools
    assert 'grep_search' in tools
    assert 'semantic_retrieve' in tools

def test_build_plan_returns_mandatory_multitool():
    sys.path.insert(0, ROOT)
    from tmp_agent.brain_v9.core.agent_kernel_v2.planner import build_plan
    goal = "MANDATORY TOOL TEST. You must perform all of these checks: probe http://127.0.0.1:8091/v2/agent/status, read repo status, search for kimi-k2.6, retrieve FAISS governance."
    classification, plan, metadata = build_plan(goal, 'read_only')
    assert classification == 'mandatory_multitool'
    assert len(plan) >= 5

def test_build_plan_includes_route_probe_status():
    sys.path.insert(0, ROOT)
    from tmp_agent.brain_v9.core.agent_kernel_v2.planner import build_plan
    goal = "MANDATORY TOOL TEST.\n1. Probe http://127.0.0.1:8091/v2/agent/status."
    cls, plan, meta = build_plan(goal, 'read_only')
    tools = [s.get('tool_name') for s in plan]
    assert 'route_probe' in tools

def test_build_plan_includes_route_probe_capabilities():
    sys.path.insert(0, ROOT)
    from tmp_agent.brain_v9.core.agent_kernel_v2.planner import build_plan
    goal = "MANDATORY TOOL TEST.\n1. Probe http://127.0.0.1:8091/v2/agent/capabilities."
    cls, plan, meta = build_plan(goal, 'read_only')
    tools = [s.get('tool_name') for s in plan]
    assert 'route_probe' in tools

def test_build_plan_includes_repo_status_read():
    sys.path.insert(0, ROOT)
    from tmp_agent.brain_v9.core.agent_kernel_v2.planner import build_plan
    goal = "MANDATORY TOOL TEST.\n1. Read repo status."
    cls, plan, meta = build_plan(goal, 'read_only')
    tools = [s.get('tool_name') for s in plan]
    assert 'repo_status_read' in tools

def test_build_plan_includes_grep_search_kimi():
    sys.path.insert(0, ROOT)
    from tmp_agent.brain_v9.core.agent_kernel_v2.planner import build_plan
    goal = "MANDATORY TOOL TEST.\n1. Search code for kimi-k2.6 finalizer."
    cls, plan, meta = build_plan(goal, 'read_only')
    tools = [s.get('tool_name') for s in plan]
    assert 'grep_search' in tools

def test_build_plan_includes_grep_search_chat_agent():
    sys.path.insert(0, ROOT)
    from tmp_agent.brain_v9.core.agent_kernel_v2.planner import build_plan
    goal = "MANDATORY TOOL TEST.\n1. Search code for /v2/chat/agent route."
    cls, plan, meta = build_plan(goal, 'read_only')
    tools = [s.get('tool_name') for s in plan]
    assert 'grep_search' in tools

def test_build_plan_includes_semantic_retrieve():
    sys.path.insert(0, ROOT)
    from tmp_agent.brain_v9.core.agent_kernel_v2.planner import build_plan
    goal = "MANDATORY TOOL TEST.\n1. Retrieve memory about FAISS governance."
    cls, plan, meta = build_plan(goal, 'read_only')
    tools = [s.get('tool_name') for s in plan]
    assert 'semantic_retrieve' in tools

def test_finalizer_prompt_has_distinction():
    sys.path.insert(0, ROOT)
    from tmp_agent.brain_v9.core.agent_kernel_v2.finalizer import build_finalizer_prompt
    prompt = build_finalizer_prompt(
        {"goal": "test", "mode": "read_only", "classification": "mandatory_multitool"},
        [], [],
        requested_checks=[{"tool_name": "route_probe", "description": "probe"}],
        scheduled_tools=["route_probe"],
        executed_tools=["route_probe"],
    )
    assert "tool_distinction" in prompt or "requested" in prompt.lower()
    assert "Do NOT say tools are unavailable" in prompt or "unavailable" in prompt.lower()

def test_tool_gateway_route_probe_local_only():
    sys.path.insert(0, ROOT)
    from tmp_agent.brain_v9.core.agent_kernel_v2.tool_gateway import ToolGatewayV2
    from tmp_agent.brain_v9.core.agent_kernel_v2.schemas import ToolCallRequest
    gw = ToolGatewayV2()
    res = gw.call(ToolCallRequest(tool_name="route_probe", args={"url": "http://127.0.0.1:8091/health"}, mode="read_only"))
    assert res.ok is True

def test_tool_gateway_grep_search():
    sys.path.insert(0, ROOT)
    from tmp_agent.brain_v9.core.agent_kernel_v2.tool_gateway import ToolGatewayV2
    from tmp_agent.brain_v9.core.agent_kernel_v2.schemas import ToolCallRequest
    gw = ToolGatewayV2()
    res = gw.call(ToolCallRequest(tool_name="grep_search", args={"pattern": "kimi-k2.6", "glob": "*.py"}, mode="read_only"))
    assert res.ok is True
    assert len((res.result or {}).get("matches", [])) > 0

def test_tool_gateway_semantic_retrieve_readonly():
    sys.path.insert(0, ROOT)
    from tmp_agent.brain_v9.core.agent_kernel_v2.tool_gateway import ToolGatewayV2
    from tmp_agent.brain_v9.core.agent_kernel_v2.schemas import ToolCallRequest
    gw = ToolGatewayV2()
    res = gw.call(ToolCallRequest(tool_name="semantic_retrieve", args={"query": "FAISS governance", "top_k": 3}, mode="read_only"))
    assert res.ok is True
    assert (res.result or {}).get("hits") is not None

def test_env_read_blocked():
    sys.path.insert(0, ROOT)
    from tmp_agent.brain_v9.core.agent_kernel_v2.tool_gateway import ToolGatewayV2
    from tmp_agent.brain_v9.core.agent_kernel_v2.schemas import ToolCallRequest
    gw = ToolGatewayV2()
    res = gw.call(ToolCallRequest(tool_name="file_read", args={"path": ".env"}, mode="read_only"))
    assert res.blocked is True

def test_write_without_approval_blocked():
    sys.path.insert(0, ROOT)
    from tmp_agent.brain_v9.core.agent_kernel_v2.tool_gateway import ToolGatewayV2
    from tmp_agent.brain_v9.core.agent_kernel_v2.schemas import ToolCallRequest
    gw = ToolGatewayV2()
    res = gw.call(ToolCallRequest(tool_name="file_patch_apply_approval_required", args={"path": "README.md"}, mode="read_only"))
    assert res.blocked is True
    assert res.approval_required is True

def test_exact_retest_evidence_exists():
    assert os.path.exists(os.path.join(EVIDENCE, 'exact_failed_prompt_retest.json'))

def test_exact_retest_classification_mandatory():
    data = _read_json(os.path.join(EVIDENCE, 'exact_failed_prompt_retest.json'))
    assert data['result']['classification'] == 'mandatory_multitool'

def test_exact_retest_uses_kimi():
    data = _read_json(os.path.join(EVIDENCE, 'exact_failed_prompt_retest.json'))
    assert data['result']['model_used'] == 'kimi-k2.6:cloud'
    assert data['result']['provider_degraded'] is False

def test_exact_retest_final_answer_not_unavailable():
    data = _read_json(os.path.join(EVIDENCE, 'exact_failed_prompt_retest.json'))
    answer = data['result']['final_answer'].lower()
    assert "unavailable" not in answer or "not unavailable" in answer

def test_regression_results_exists():
    assert os.path.exists(os.path.join(EVIDENCE, 'regression_results.json'))

def test_regression_threshold_met():
    data = _read_json(os.path.join(EVIDENCE, 'regression_results.json'))
    assert data['summary']['threshold_met'] is True
    assert data['summary']['unauthorized_writes'] == 0
    assert data['summary']['raw_cot_exposed'] == 0

def test_memory_faiss_unchanged():
    baseline = _read_json(os.path.join(EVIDENCE, 'memory_faiss_baseline.json'))
    import faiss
    idx = faiss.read_index(os.path.join(ROOT, 'memory/semantic/semantic_memory_faiss.index'))
    assert idx.ntotal == baseline['faiss_ntotal']
    with open(os.path.join(ROOT, 'memory/semantic/semantic_memory.jsonl'), 'rb') as f:
        lines = f.read().decode('utf-8', errors='replace').count('\n')
    assert lines == baseline['semantic_jsonl']['lines_or_bytes']

def test_docs_updated():
    assert os.path.exists(os.path.join(ROOT, 'docs/BRAIN_AGENT_RUNTIME_CONTRACT_V2.md'))

def test_roadmap_updated():
    data = _read_json(os.path.join(ROOT, 'ROADMAP_STATUS.json'))
    assert 'front_brain_agent_v2_mandatory_multitool_planner_hotfix_01' in data or any('mandatory' in k for k in data.keys())

if __name__ == '__main__':
    import pytest
    pytest.main([__file__, '-v'])
