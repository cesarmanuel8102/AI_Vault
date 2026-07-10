"""B7-STRANGLER-10B agent route extraction tests."""
from __future__ import annotations

import ast
import asyncio
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SESSION = ROOT / "tmp_agent" / "brain_v9" / "core" / "session.py"
AGENT_ROUTE = ROOT / "tmp_agent" / "brain_v9" / "core" / "session_agent_route.py"
PARENT = "43de96a:tmp_agent/brain_v9/core/session.py"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def _class_methods(source: str) -> dict[str, ast.AST]:
    tree = ast.parse(source)
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "BrainSession")
    return {
        n.name: n
        for n in cls.body
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def _signature(node: ast.AST) -> str:
    kind = "async" if isinstance(node, ast.AsyncFunctionDef) else "sync"
    returns = ast.unparse(node.returns) if getattr(node, "returns", None) else ""
    return f"{kind} {node.name}({ast.unparse(node.args)}) -> {returns}"


def _source_segment(source: str, node: ast.AST) -> str:
    return ast.get_source_segment(source, node) or ""


def _parent_source() -> str:
    return subprocess.check_output(
        ["git", "show", PARENT],
        cwd=ROOT,
        text=True,
        encoding="utf-8",
        errors="ignore",
    )


def test_module_does_not_import_session() -> None:
    source = _read(AGENT_ROUTE)
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            assert node.module != "brain_v9.core.session", node.module
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
            assert "brain_v9.core.session" not in names, names
    assert "BrainSession" not in source


def test_module_has_no_forbidden_cross_front_imports() -> None:
    source = _read(AGENT_ROUTE)
    forbidden = [
        "session_fastpaths",
        "session_command_handler",
        "session_tool01_gateway",
        "session_routing_helpers",
    ]
    hits = [token for token in forbidden if token in source]
    assert not hits, hits


def test_structural_agent_route_shim_is_thin() -> None:
    source = _read(SESSION)
    methods = _class_methods(source)
    node = methods["_route_to_agent"]
    assert isinstance(node, ast.AsyncFunctionDef)
    assert len(node.body) == 2
    assert isinstance(node.body[0], ast.Expr) and isinstance(node.body[0].value, ast.Constant)
    ret = node.body[1]
    assert isinstance(ret, ast.Return)
    assert isinstance(ret.value, ast.Await)
    call = ret.value.value
    assert isinstance(call, ast.Call)
    assert ast.unparse(call.func) == "_agent_route._route_to_agent"
    shim_src = _source_segment(source, node)
    assert "B7-STRANGLER-10B shim" in shim_src
    for token in ["Tool ejecutada realmente", "MetaPlanner", "AgentLoop", "_dashboard_status_fastpath"]:
        assert token not in shim_src, token


def test_route_to_agent_signature_exact_match_parent() -> None:
    parent = _parent_source()
    current = _read(SESSION)
    parent_methods = _class_methods(parent)
    current_methods = _class_methods(current)
    assert _signature(current_methods["_route_to_agent"]) == _signature(parent_methods["_route_to_agent"])


def test_blocked_methods_exact_match_parent() -> None:
    parent = _parent_source()
    current = _read(SESSION)
    parent_methods = _class_methods(parent)
    current_methods = _class_methods(current)
    blocked = {
        "chat",
        "_route_to_llm",
        "_should_use_agent",
        "_policy_route_decision",
        "_maybe_resume_pending_continuation",
        "_handle_command",
        "_maybe_fastpath",
        "_tool01_execute",
    }
    for name in blocked:
        assert _source_segment(current, current_methods[name]) == _source_segment(parent, parent_methods[name]), name


def test_agent_route_module_static_safety() -> None:
    source = _read(AGENT_ROUTE)
    forbidden = [
        "placeOrder",
        "submit_order",
        "faiss.add",
        "semantic_memory.append",
        "write_text(",
        ".write(",
    ]
    hits = [token for token in forbidden if token in source]
    assert not hits, hits


class FakeLogger:
    def info(self, *args, **kwargs):
        return None

    def warning(self, *args, **kwargs):
        return None

    def error(self, *args, **kwargs):
        return None

    def exception(self, *args, **kwargs):
        return None


class FakeSession:
    def __init__(self):
        self.logger = FakeLogger()
        self.mode = "tool"

    async def _tool01_router(self, message):
        if self.mode == "tool":
            return {"success": True, "tool_name": "fake_tool", "blocked_by_policy": False}
        return None

    def _is_dashboard_query(self, msg):
        return self.mode == "dashboard"

    def _dashboard_status_fastpath(self):
        return {"success": True, "content": "dashboard ok"}

    def _cmd_edge(self): return {"success": True, "content": "edge"}
    def _cmd_ranking(self): return {"success": True, "content": "ranking"}
    def _cmd_hypothesis(self): return {"success": True, "content": "hypothesis"}
    def _cmd_posttrade(self): return {"success": True, "content": "posttrade"}
    def _cmd_security(self): return {"success": True, "content": "security"}
    def _cmd_memory(self): return {"success": True, "content": "memory"}
    def _cmd_control(self): return {"success": True, "content": "control"}
    def _cmd_autonomy(self): return {"success": True, "content": "autonomy"}
    def _cmd_status(self): return {"success": True, "content": "status"}
    def _cmd_learning(self): return {"success": True, "content": "learning"}
    def _cmd_catalog(self): return {"success": True, "content": "catalog"}
    def _cmd_validators(self): return {"success": True, "content": "validators"}
    def _cmd_mutations(self): return {"success": True, "content": "mutations"}
    def _cmd_governance(self): return {"success": True, "content": "governance"}
    def _cmd_risk(self): return {"success": True, "content": "risk"}
    def _cmd_health(self): return {"success": True, "content": "health"}
    def _render_operational_agent_summary(self, *args, **kwargs): return "summary"
    def _render_agent_failure_reply(self, *args, **kwargs): return {"success": False, "content": "failure", "response": "failure"}
    def _normalize_agent_result(self, result, *args, **kwargs): return result
    def _sanitize_user_visible_response(self, text, **kwargs): return text
    def _looks_like_canned_failure(self, text): return False
    def _contains_raw_tool_markup(self, text): return False
    def _contains_raw_reasoning_trace(self, text): return False
    def _contains_chain_of_thought_marker(self, text): return False
    def _contains_phantom_execution_claim(self, text): return False
    def _looks_like_placeholder_output(self, text): return False
    def _looks_like_forbidden_simulated_execution(self, text): return False
    def _maybe_emit_capability_decline(self, *args, **kwargs): return None


def test_functional_agent_route_tool01_and_dashboard_smoke() -> None:
    import sys
    sys.path.insert(0, str(ROOT / "tmp_agent"))
    from brain_v9.core import session_agent_route

    async def run() -> None:
        session = FakeSession()
        tool_result = await session_agent_route._route_to_agent(session, "ejecuta fake", "chat")
        assert tool_result["success"] is True
        assert tool_result["route"] == "tool01_router"
        assert tool_result["tool_name"] == "fake_tool"

        session.mode = "dashboard"
        dashboard = await session_agent_route._route_to_agent(session, "estado dashboard", "chat")
        assert dashboard["success"] is True
        assert dashboard["agent_status"] == "tool_backed_fastpath"
        assert dashboard["content"] == "dashboard ok"

    asyncio.run(run())


if __name__ == "__main__":
    tests = [
        test_module_does_not_import_session,
        test_module_has_no_forbidden_cross_front_imports,
        test_structural_agent_route_shim_is_thin,
        test_route_to_agent_signature_exact_match_parent,
        test_blocked_methods_exact_match_parent,
        test_agent_route_module_static_safety,
        test_functional_agent_route_tool01_and_dashboard_smoke,
    ]
    for test in tests:
        test()
    print(f"OK: {len(tests)} session agent route tests passed")
