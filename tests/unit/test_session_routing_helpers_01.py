"""B7-STRANGLER-10A routing helper extraction tests."""
from __future__ import annotations

import ast
import asyncio
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SESSION = ROOT / "tmp_agent" / "brain_v9" / "core" / "session.py"
HELPERS = ROOT / "tmp_agent" / "brain_v9" / "core" / "session_routing_helpers.py"
MOVED = {
    "_should_use_agent",
    "_route_to_llm",
    "_maybe_resume_pending_continuation",
    "_policy_route_decision",
}
BLOCKED = {"chat"}


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


def test_module_does_not_import_session() -> None:
    source = _read(HELPERS)
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            assert node.module != "brain_v9.core.session", node.module
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
            assert "brain_v9.core.session" not in names, names
    assert "BrainSession" not in source


def test_module_has_no_forbidden_cross_front_tokens() -> None:
    source = _read(HELPERS)
    forbidden = [
        "_tool01_gateway",
        "_fastpaths",
        "_cmd_handlers",
        "session_command_handler",
        "session_fastpaths",
        "session_tool01_gateway",
        "faiss.add",
        "semantic_memory.append",
        "placeOrder",
        "submit_order",
    ]
    hits = [token for token in forbidden if token in source]
    assert not hits, hits


def test_structural_routing_shims_are_thin() -> None:
    source = _read(SESSION)
    methods = _class_methods(source)
    for name in MOVED:
        node = methods[name]
        body = node.body
        assert len(body) == 2, name
        assert isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant), name
        ret = body[1]
        assert isinstance(ret, ast.Return), name
        call = ret.value
        if isinstance(node, ast.AsyncFunctionDef):
            assert isinstance(call, ast.Await), name
            call = call.value
        assert isinstance(call, ast.Call), name
        assert ast.unparse(call.func).startswith("_routing_helpers."), ast.unparse(call.func)
        assert name in ast.unparse(call.func), ast.unparse(call.func)
        shim_src = _source_segment(source, node)
        assert "B7-STRANGLER-10A shim" in shim_src
        for token in ["Tool01", "fastpath", "command handler", "write_text", ".write("]:
            assert token not in shim_src, (name, token)


def test_routing_signatures_exact_match_parent() -> None:
    parent = subprocess.check_output(
        ["git", "show", "24c8cc3:tmp_agent/brain_v9/core/session.py"],
        cwd=ROOT,
        text=True,
        encoding="utf-8",
        errors="ignore",
    )
    current = _read(SESSION)
    parent_methods = _class_methods(parent)
    current_methods = _class_methods(current)
    for name in MOVED:
        assert _signature(current_methods[name]) == _signature(parent_methods[name]), name


def test_blocked_methods_exact_match_parent() -> None:
    parent = subprocess.check_output(
        ["git", "show", "24c8cc3:tmp_agent/brain_v9/core/session.py"],
        cwd=ROOT,
        text=True,
        encoding="utf-8",
        errors="ignore",
    )
    current = _read(SESSION)
    parent_methods = _class_methods(parent)
    current_methods = _class_methods(current)
    for name in BLOCKED:
        assert _source_segment(current, current_methods[name]) == _source_segment(parent, parent_methods[name]), name


class FakeLLM:
    async def query(self, messages, model_priority="chat", max_time=90):
        return {"success": True, "content": f"ok:{model_priority}:{messages[-1]['content']}"}


class FakeSession:
    def __init__(self) -> None:
        self.logger = type("Log", (), {"info": lambda *a, **k: None})()
        self.llm = FakeLLM()
        self._pending_confirmed_action = None
        self._pending_continuation = None
        self.cleared = False

    def _prefers_no_tool_analysis(self, message):
        return "sin herramientas" in message.lower()

    def _has_explicit_tool_target(self, message):
        return "archivo" in message.lower()

    def _should_use_compact_chat_prompt(self, *args, **kwargs):
        return True

    def _is_abstract_reasoning_query(self, message):
        return False

    def _select_llm_chain(self, *args, **kwargs):
        return "fake-chain"

    def _context_budget(self, *args, **kwargs):
        return 512

    def _truncate_to_budget(self, history, budget_tokens=512):
        return history

    def _governed_self_improvement_eval_fallback(self, message):
        return None

    def _system_reply(self, text, success=True):
        return {"success": success, "content": text, "response": text}

    def _looks_like_canned_failure(self, text):
        return False

    def _sanitize_user_visible_response(self, text, **kwargs):
        return text

    def _sanitize_llm_chat_response(self, text):
        return text

    def _contains_raw_tool_markup(self, text):
        return False

    def _looks_like_placeholder_output(self, text):
        return False

    def _looks_like_forbidden_simulated_execution(self, text):
        return False

    def _contains_raw_reasoning_trace(self, text):
        return False

    def _contains_chain_of_thought_marker(self, text):
        return False

    def _contains_phantom_execution_claim(self, text):
        return False

    def _maybe_emit_capability_decline(self, message, sanitized):
        return None

    async def _route_to_agent(self, message, model_priority):
        return {"success": True, "content": "agent", "response": "agent"}

    async def chat(self, message, model_priority="chat"):
        return {"success": True, "content": message, "response": message}

    def _clear_pending_continuation(self):
        self.cleared = True
        self._pending_continuation = None
        self._pending_confirmed_action = None

    def _get_curated_ingestion_response(self):
        return "curated"


def test_functional_routing_helpers_with_fake_session() -> None:
    import sys
    sys.path.insert(0, str(ROOT / "tmp_agent"))
    from brain_v9.core import session_routing_helpers as helpers

    session = FakeSession()
    assert helpers._should_use_agent(session, "hola", "CONVERSATION") is False
    assert helpers._should_use_agent(session, "ejecuta tests del archivo", "COMMAND") is True

    policy = helpers._policy_route_decision(session, "qué significa el código HTTP 200")
    assert policy["kind"] == "conceptual_http"
    assert policy["local_response"]["success"] is True

    async def run_async() -> None:
        llm = await helpers._route_to_llm(session, "hola", "QUERY", [], "chat")
        assert llm["success"] is True
        assert "ok:fake-chain:hola" in llm["content"]
        session._pending_continuation = {"message": "continuar prueba", "attempts": 0, "model_priority": "chat"}
        resumed = await helpers._maybe_resume_pending_continuation(session, "sí")
        assert resumed["success"] is True
        assert session.cleared is True

    asyncio.run(run_async())


if __name__ == "__main__":
    tests = [
        test_module_does_not_import_session,
        test_module_has_no_forbidden_cross_front_tokens,
        test_structural_routing_shims_are_thin,
        test_routing_signatures_exact_match_parent,
        test_blocked_methods_exact_match_parent,
        test_functional_routing_helpers_with_fake_session,
    ]
    for test in tests:
        test()
    print(f"OK: {len(tests)} session routing helper tests passed")
