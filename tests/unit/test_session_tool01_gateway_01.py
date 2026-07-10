"""Tests for session_tool01_gateway extracted helpers.

Front: FRONT-B7-SESSION-STRANGLER-TOOL01-GATEWAY-09A
"""
import sys
import os
import ast
import subprocess
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "tmp_agent"))

REPO_ROOT = Path(__file__).resolve().parents[2]
SESSION_PATH = REPO_ROOT / "tmp_agent" / "brain_v9" / "core" / "session.py"
PARENT_COMMIT = "806a75d"

MOVED_METHOD_NAMES = [
    "_tool01_get_risk_level",
    "_tool01_has_permission",
    "_tool01_request_permission",
    "_tool01_approve_permission",
    "_tool01_router",
    "_tool01_has_permission_grant",
    "_tool01_handle_permission_response",
    "_tool01_extract_path",
    "_tool01_policy_check_path",
    "_is_safe_workspace_path",
    "_tool01_extract_git_diff_targets",
    "_tool01_summarize_git_diff",
    "_tool01_extract_write_content",
    "_tool01_write_evidence",
    "_tool01_execute",
    "_should_delegate_tool01_to_orav",
    "_run_orav_as_approved_executor",
]


def _parse_session(txt):
    tree = ast.parse(txt)
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "BrainSession")
    return {n.name: n for n in cls.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}


def _signature(node):
    """Return a stable signature tuple for a FunctionDef/AsyncFunctionDef."""
    args = node.args
    is_async = isinstance(node, ast.AsyncFunctionDef)
    pos = [a.arg for a in args.args]
    pos_defaults = [ast.dump(d) for d in args.defaults]
    kwonly = [a.arg for a in args.kwonlyargs]
    kw_defaults = [ast.dump(d) if d else "None" for d in args.kw_defaults]
    vararg = args.vararg.arg if args.vararg else None
    kwarg = args.kwarg.arg if args.kwarg else None
    returns = ast.dump(node.returns) if node.returns else None
    # annotations
    pos_ann = [ast.dump(a.annotation) if a.annotation else None for a in args.posonlyargs + args.args]
    return (
        is_async,
        tuple(pos),
        tuple(pos_defaults),
        tuple(kwonly),
        tuple(kw_defaults),
        vararg,
        kwarg,
        returns,
        tuple(pos_ann),
    )


def test_module_does_not_import_session():
    import inspect
    import tmp_agent.brain_v9.core.session_tool01_gateway as mod
    src = inspect.getsource(mod)
    lines = [l for l in src.splitlines() if l.strip().startswith("import ") or l.strip().startswith("from ")]
    for line in lines:
        assert "brain_v9.core.session " not in line and "brain_v9.core.session'" not in line and "brain_v9.core.session\"" not in line, f"must NOT import session.py: {line.strip()}"


def test_module_has_no_forbidden_routing_or_governance_changes():
    import inspect
    import tmp_agent.brain_v9.core.session_tool01_gateway as mod
    src = inspect.getsource(mod)
    forbidden_exec = [
        "_route_to_agent(",
        "_route_to_llm(",
        "_policy_route_decision(",
        "_should_use_agent(",
        "chat(",
        "placeOrder",
        "submit_order",
        "faiss.add",
        "semantic_memory.append",
    ]
    for token in forbidden_exec:
        assert token not in src, f"forbidden execution token in tool01_gateway module: {token}"


def test_structural_tool01_shims_are_thin():
    txt = SESSION_PATH.read_text(encoding="utf-8", errors="ignore")
    tree = ast.parse(txt)
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "BrainSession")
    methods = {n.name: n for n in cls.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}

    tool01_count = 0
    for name in methods:
        if not ("tool01" in name.lower() or name == "_is_safe_workspace_path"):
            continue
        tool01_count += 1
        src = ast.get_source_segment(txt, methods[name]) or ""
        assert "_tool01_gateway." in src, f"{name} must delegate to _tool01_gateway"

        forbidden = ["read_json(", "SLASH_COMMANDS", "scorecard", "control_layer"]
        for token in forbidden:
            assert token not in src, f"forbidden token in {name}: {token}"

        if isinstance(methods[name], ast.AsyncFunctionDef):
            assert "return await" in src or "return _tool01_gateway" in src, f"async shim {name} must use return await"
        else:
            assert "return _tool01_gateway" in src, f"sync shim {name} must use return"

    assert tool01_count >= 16, f"expected >=16 tool01/orav shims, got {tool01_count}"


def test_tool01_signatures_exact_match_parent():
    """Compare signatures of moved methods against parent commit 806a75d."""
    current_txt = SESSION_PATH.read_text(encoding="utf-8", errors="ignore")
    current_methods = _parse_session(current_txt)

    proc = subprocess.run(
        ["git", "show", f"{PARENT_COMMIT}:tmp_agent/brain_v9/core/session.py"],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert proc.returncode == 0, f"git show failed: {proc.stderr}"
    parent_methods = _parse_session(proc.stdout)

    mismatches = []
    for name in MOVED_METHOD_NAMES:
        if name not in current_methods:
            mismatches.append(f"{name}: missing in current")
            continue
        if name not in parent_methods:
            mismatches.append(f"{name}: missing in parent")
            continue
        cur_sig = _signature(current_methods[name])
        par_sig = _signature(parent_methods[name])
        if cur_sig != par_sig:
            mismatches.append(f"{name}: signature drift")

    assert not mismatches, "Signature mismatches:\n  " + "\n  ".join(mismatches)


def test_tool01_shims_preserve_async_sync():
    """Async shims must stay async; sync shims must stay sync."""
    txt = SESSION_PATH.read_text(encoding="utf-8", errors="ignore")
    current_methods = _parse_session(txt)

    proc = subprocess.run(
        ["git", "show", f"{PARENT_COMMIT}:tmp_agent/brain_v9/core/session.py"],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert proc.returncode == 0
    parent_methods = _parse_session(proc.stdout)

    mismatches = []
    for name in MOVED_METHOD_NAMES:
        cur_async = isinstance(current_methods[name], ast.AsyncFunctionDef)
        par_async = isinstance(parent_methods[name], ast.AsyncFunctionDef)
        if cur_async != par_async:
            mismatches.append(f"{name}: async={cur_async} parent_async={par_async}")

    assert not mismatches, "Async/sync drift:\n  " + "\n  ".join(mismatches)


def test_tool01_gateway_function_signatures_match_shims():
    """Each gateway top-level function must accept (session, ...) matching the shim's (self, ...) args."""
    import inspect
    import tmp_agent.brain_v9.core.session_tool01_gateway as mod

    # Map shim method names -> gateway function names
    mapping = {
        "_tool01_get_risk_level": "tool01_get_risk_level",
        "_tool01_has_permission": "tool01_has_permission",
        "_tool01_request_permission": "tool01_request_permission",
        "_tool01_approve_permission": "tool01_approve_permission",
        "_tool01_router": "tool01_router",
        "_tool01_has_permission_grant": "tool01_has_permission_grant",
        "_tool01_handle_permission_response": "tool01_handle_permission_response",
        "_tool01_extract_path": "tool01_extract_path",
        "_tool01_policy_check_path": "tool01_policy_check_path",
        "_is_safe_workspace_path": "is_safe_workspace_path",
        "_tool01_extract_git_diff_targets": "tool01_extract_git_diff_targets",
        "_tool01_summarize_git_diff": "tool01_summarize_git_diff",
        "_tool01_extract_write_content": "tool01_extract_write_content",
        "_tool01_write_evidence": "tool01_write_evidence",
        "_tool01_execute": "tool01_execute",
        "_should_delegate_tool01_to_orav": "should_delegate_tool01_to_orav",
        "_run_orav_as_approved_executor": "run_orav_as_approved_executor",
    }

    txt = SESSION_PATH.read_text(encoding="utf-8", errors="ignore")
    current_methods = _parse_session(txt)

    for shim_name, gw_name in mapping.items():
        gw_fn = getattr(mod, gw_name, None)
        assert gw_fn is not None, f"gateway missing function: {gw_name}"
        gw_sig = inspect.signature(gw_fn)
        gw_params = list(gw_sig.parameters.keys())
        assert gw_params[0] == "session", f"{gw_name} first param must be 'session', got {gw_params[0]}"

        shim_node = current_methods[shim_name]
        shim_params = [a.arg for a in shim_node.args.args]
        # First shim param is 'self'; gateway first param is 'session'. Rest must match.
        assert gw_params[1:] == shim_params[1:], (
            f"{shim_name} -> {gw_name}: param drift "
            f"shim={shim_params[1:]} gateway={gw_params[1:]}"
        )


def test_tool01_constant_attributes_preserved_on_class():
    """TOOL-01 class-level constants must remain on BrainSession (DI via session._TOOL01_*)."""
    txt = SESSION_PATH.read_text(encoding="utf-8", errors="ignore")
    for const in [
        "_TOOL01_ROUTER_PATTERNS",
        "_TOOL01_PUBLIC_NAMES",
        "_TOOL01_BLOCKED_PREFIXES",
        "_TOOL01_LOW_RISK_TOOLS",
        "_TOOL01_HIGH_RISK_TOOLS",
        "_ENABLE_ORAV_POST_APPROVAL",
    ]:
        assert const in txt, f"{const} must remain defined on BrainSession"


if __name__ == "__main__":
    tests = [
        test_module_does_not_import_session,
        test_module_has_no_forbidden_routing_or_governance_changes,
        test_structural_tool01_shims_are_thin,
        test_tool01_signatures_exact_match_parent,
        test_tool01_shims_preserve_async_sync,
        test_tool01_gateway_function_signatures_match_shims,
        test_tool01_constant_attributes_preserved_on_class,
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