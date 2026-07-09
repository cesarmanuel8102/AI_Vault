"""Tests for session_command_handler extracted helpers.

Front: FRONT-B7-SESSION-STRANGLER-COMMAND-HANDLERS-07B
"""
import sys
import os
import ast
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "tmp_agent"))

from tmp_agent.brain_v9.core.session_command_handler import (
    handle_command,
    cmd_help,
    cmd_status,
    cmd_control,
    cmd_risk,
    cmd_governance,
    cmd_security,
    cmd_learning,
)


def test_module_does_not_import_session():
    import inspect
    import tmp_agent.brain_v9.core.session_command_handler as mod
    src = inspect.getsource(mod)
    lines = [l for l in src.splitlines() if l.strip().startswith("import ") or l.strip().startswith("from ")]
    for line in lines:
        assert "brain_v9.core.session " not in line and "brain_v9.core.session\"" not in line, f"must NOT import session.py: {line.strip()}"


def test_module_has_no_trading_imports():
    import inspect
    import tmp_agent.brain_v9.core.session_command_handler as mod
    src = inspect.getsource(mod)
    # Trading commands should NOT be implemented in this module
    assert "def cmd_trading_analysis" not in src
    assert "def cmd_schedule" not in src
    assert "def cmd_pipeline" not in src
    assert "def cmd_priority" not in src
    assert "def cmd_posttrade" not in src
    assert "def cmd_hypothesis" not in src


class FakeSession:
    """Minimal duck-typed session for command handler tests."""
    session_id = "test_session"
    dev_mode = False
    memory = type("FakeMem", (), {"clear": lambda self, x: None})()
    
    def _system_reply(self, text, success=True):
        return {"success": success, "content": text, "response": text}
    
    def _utility_score(self, utility):
        return utility.get("u_score", "N/A")
    
    def _utility_blockers(self, utility):
        gate = utility.get("promotion_gate") or {}
        blockers = gate.get("blockers")
        return blockers if isinstance(blockers, list) else []
    
    def _persist_chat_dev_mode_default(self, val):
        return True
    
    def _load_chat_dev_mode_default(self):
        return False
    
    # Blocked commands stay as stubs on session
    async def _cmd_trading_analysis(self):
        return {"success": True, "content": "trading"}
    
    def _cmd_schedule(self, arg):
        return {"success": True, "content": "schedule"}
    
    def _cmd_pipeline(self):
        return {"success": True, "content": "pipeline"}
    
    def _cmd_priority(self):
        return {"success": True, "content": "priority"}
    
    def _cmd_posttrade(self):
        return {"success": True, "content": "posttrade"}
    
    def _cmd_hypothesis(self):
        return {"success": True, "content": "hypothesis"}


def test_cmd_help():
    session = FakeSession()
    result = cmd_help(session)
    assert result["success"] is True
    assert "Comandos disponibles" in result["content"]


def test_cmd_status():
    session = FakeSession()
    result = cmd_status(session)
    assert result["success"] is True
    assert "Estado Brain" in result["content"]


def test_cmd_control():
    session = FakeSession()
    result = cmd_control(session)
    assert result["success"] is True
    assert "Control de Cambios" in result["content"]


def test_cmd_risk():
    session = FakeSession()
    result = cmd_risk(session)
    assert result["success"] is True


def test_cmd_governance():
    session = FakeSession()
    result = cmd_governance(session)
    assert result["success"] is True


def test_cmd_security():
    session = FakeSession()
    result = cmd_security(session)
    assert result["success"] is True


def test_cmd_learning():
    session = FakeSession()
    result = cmd_learning(session)
    assert result["success"] is True


def test_handle_command_unknown():
    """Unknown command should return system reply with help message."""
    import asyncio
    session = FakeSession()
    result = asyncio.get_event_loop().run_until_complete(handle_command(session, "/nonexistent"))
    assert result["success"] is True
    assert "desconocido" in result["content"]


def test_handle_command_help():
    import asyncio
    session = FakeSession()
    result = asyncio.get_event_loop().run_until_complete(handle_command(session, "/help"))
    assert result["success"] is True
    assert "Comandos disponibles" in result["content"]


def test_handle_command_trading_passthrough():
    """Trading commands should pass through to session methods."""
    import asyncio
    session = FakeSession()
    result = asyncio.get_event_loop().run_until_complete(handle_command(session, "/pipeline"))
    assert result["content"] == "pipeline"


def test_structural_command_shims_are_thin():
    """AST test: verify BrainSession command shims are thin delegates."""
    p = Path(__file__).resolve().parents[2] / "tmp_agent" / "brain_v9" / "core" / "session.py"
    txt = p.read_text(encoding="utf-8", errors="ignore")
    tree = ast.parse(txt)
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "BrainSession")
    
    safe_methods = [
        "_handle_command", "_cmd_help", "_cmd_status", "_cmd_control",
        "_cmd_freeze", "_cmd_unfreeze", "_cmd_dev", "_cmd_clear",
        "_cmd_model", "_cmd_autonomy", "_cmd_strategy", "_cmd_edge",
        "_cmd_ranking", "_cmd_trade", "_cmd_risk", "_cmd_governance",
        "_cmd_security", "_cmd_diagnostic", "_cmd_memory", "_cmd_learning",
        "_cmd_catalog", "_cmd_context_edge", "_cmd_mode", "_cmd_approve",
        "_cmd_reject", "_cmd_pending",
    ]
    
    methods = {n.name: n for n in cls.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    
    for name in safe_methods:
        assert name in methods, f"missing shim: {name}"
        src = ast.get_source_segment(txt, methods[name])
        assert "_cmd_handlers." in src, f"{name} must delegate to _cmd_handlers"
        
        # Check no old body tokens
        forbidden = ["read_json(", "SLASH_COMMANDS", "scorecard", "control_layer"]
        for token in forbidden:
            assert token not in src, f"forbidden token in {name}: {token}"


if __name__ == "__main__":
    tests = [
        test_module_does_not_import_session,
        test_module_has_no_trading_imports,
        test_cmd_help,
        test_cmd_status,
        test_cmd_control,
        test_cmd_risk,
        test_cmd_governance,
        test_cmd_security,
        test_cmd_learning,
        test_handle_command_unknown,
        test_handle_command_help,
        test_handle_command_trading_passthrough,
        test_structural_command_shims_are_thin,
    ]
    passed = 0
    for t in tests:
        try:
            t()
            print(f"PASS  {t.__name__}")
            passed += 1
        except AssertionError as e:
            print(f"FAIL  {t.__name__}: {e}")
        except Exception as e:
            print(f"ERROR {t.__name__}: {e}")
    print(f"\n{passed}/{len(tests)} passed")