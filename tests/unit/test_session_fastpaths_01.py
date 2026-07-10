"""Tests for session_fastpaths extracted helpers.

Front: FRONT-B7-SESSION-STRANGLER-FASTPATHS-AGGRESSIVE-BATCH-08A
"""
import sys
import os
import ast
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "tmp_agent"))


def test_module_does_not_import_session():
    import inspect
    import tmp_agent.brain_v9.core.session_fastpaths as mod
    src = inspect.getsource(mod)
    lines = [l for l in src.splitlines() if l.strip().startswith("import ") or l.strip().startswith("from ")]
    for line in lines:
        assert "brain_v9.core.session " not in line and "brain_v9.core.session\"" not in line, f"must NOT import session.py: {line.strip()}"


def test_module_has_no_execution_trading_or_tool01():
    import inspect
    import tmp_agent.brain_v9.core.session_fastpaths as mod
    src = inspect.getsource(mod)
    forbidden = [
        "def _tool01",
        "_route_to_agent",
        "_route_to_llm",
        "_policy_route_decision",
        "_should_use_agent",
        "placeOrder",
        "submit_order",
        "order_submission_enabled",
    ]
    for token in forbidden:
        assert token not in src, f"forbidden token in fastpaths module: {token}"


def test_structural_fastpath_shims_are_thin():
    p = Path(__file__).resolve().parents[2] / "tmp_agent" / "brain_v9" / "core" / "session.py"
    txt = p.read_text(encoding="utf-8", errors="ignore")
    tree = ast.parse(txt)
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "BrainSession")
    methods = {n.name: n for n in cls.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    
    fastpath_count = 0
    for name in methods:
        if "fastpath" not in name.lower():
            continue
        fastpath_count += 1
        src = ast.get_source_segment(txt, methods[name])
        assert "_fastpaths." in src, f"{name} must delegate to _fastpaths"
        
        forbidden = ["read_json(", "SLASH_COMMANDS", "scorecard", "control_layer"]
        for token in forbidden:
            assert token not in src, f"forbidden token in {name}: {token}"
    
    assert fastpath_count >= 25, f"expected >=25 fastpath shims, got {fastpath_count}"


def test_all_fastpath_methods_accounted_for():
    p = Path(__file__).resolve().parents[2] / "tmp_agent" / "brain_v9" / "core" / "session.py"
    txt = p.read_text(encoding="utf-8", errors="ignore")
    tree = ast.parse(txt)
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "BrainSession")
    
    fastpath_names = []
    for n in cls.body:
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and "fastpath" in n.name.lower():
            fastpath_names.append(n.name)
    
    assert len(fastpath_names) == 30, f"expected 30 fastpath methods, got {len(fastpath_names)}"


if __name__ == "__main__":
    tests = [
        test_module_does_not_import_session,
        test_module_has_no_execution_trading_or_tool01,
        test_structural_fastpath_shims_are_thin,
        test_all_fastpath_methods_accounted_for,
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