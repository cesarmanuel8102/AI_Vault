"""AST shim cleanliness audit for B7-STRANGLER-11.

Verifies that the three shim methods in BrainSession are clean 1-line delegators,
and that session_agent_render.py doesn't import session.py.
"""
import ast
import pathlib
import sys

SESSION_PY = pathlib.Path(r"tmp_agent/brain_v9/core/session.py")
NEW_MODULE = pathlib.Path(r"tmp_agent/brain_v9/core/session_agent_render.py")

SHIMS = [
    "_render_agent_failure_reply",
    "_summarize_action_output",
    "_render_operational_agent_summary",
]


def get_brain_session_body(src: str):
    tree = ast.parse(src)
    cls = next(
        (n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "BrainSession"),
        None,
    )
    if cls is None:
        raise RuntimeError("BrainSession class not found")
    return cls.body


def audit_shim(method: ast.FunctionDef, expected_call_prefix: str) -> list:
    errors = []
    dec_names = [ast.unparse(d) for d in method.decorator_list]
    if "classmethod" not in dec_names:
        errors.append(f"{method.name}: missing @classmethod")

    body = method.body
    idx = 0
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) and isinstance(body[0].value.value, str):
        idx = 1
    if len(body) - idx != 1:
        errors.append(f"{method.name}: expected 1 statement after docstring, got {len(body) - idx}")
    else:
        stmt = body[idx]
        if not isinstance(stmt, ast.Return):
            errors.append(f"{method.name}: expected Return, got {type(stmt).__name__}")
        else:
            call = stmt.value
            if not isinstance(call, ast.Call):
                errors.append(f"{method.name}: Return value is not a Call")
            else:
                call_str = ast.unparse(call.func)
                if not call_str.startswith(expected_call_prefix):
                    errors.append(f"{method.name}: expected call to {expected_call_prefix}*, got {call_str}")

    # Forbidden inline logic checks
    for node in ast.walk(method):
        if isinstance(node, ast.Call):
            func_str = ast.unparse(node.func)
            if "status_map" in func_str:
                errors.append(f"{method.name}: contains forbidden inline status_map")
            if "_sanitize_user_visible_response" in func_str and method.name != "_render_agent_failure_reply":
                errors.append(f"{method.name}: contains forbidden inline _sanitize_user_visible_response call")
            if "_contains_raw_tool_markup" in func_str and method.name != "_render_agent_failure_reply":
                errors.append(f"{method.name}: contains forbidden inline _contains_raw_tool_markup call")
            if "_looks_like_canned_failure" in func_str and method.name != "_render_agent_failure_reply":
                errors.append(f"{method.name}: contains forbidden inline _looks_like_canned_failure call")
            if "_format_tool_result" in func_str and method.name != "_summarize_action_output":
                errors.append(f"{method.name}: contains forbidden inline _format_tool_result call")
            if "_summarize_action_output" in func_str and method.name != "_render_operational_agent_summary":
                errors.append(f"{method.name}: contains forbidden inline _summarize_action_output call")
    return errors


def audit_new_module(src: str) -> list:
    errors = []
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if "session" in alias.name:
                    errors.append(f"new module imports {alias.name}")
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if "session" in module:
                errors.append(f"new module imports from {module}")
        if isinstance(node, ast.Name) and node.id == "BrainSession":
            errors.append("new module references BrainSession")
        if isinstance(node, ast.Attribute):
            if isinstance(node.value, ast.Name) and node.value.id == "BrainSession":
                errors.append("new module references BrainSession attribute")
    return errors


def main() -> int:
    session_src = SESSION_PY.read_text(encoding="utf-8")
    new_src = NEW_MODULE.read_text(encoding="utf-8")
    body = get_brain_session_body(session_src)
    methods = {n.name: n for n in body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    all_errors = []

    for name in SHIMS:
        if name not in methods:
            all_errors.append(f"{name}: method missing from BrainSession")
            continue
        prefix = f"_agent_render.{name.lstrip('_')}"
        all_errors.extend(audit_shim(methods[name], prefix))

    all_errors.extend(audit_new_module(new_src))

    if all_errors:
        print("SHIM_CLEANLINESS_AUDIT_FAILED")
        for e in all_errors:
            print(f"  - {e}")
        return 1
    else:
        print("SHIM_CLEANLINESS_AUDIT_OK")
        return 0


if __name__ == "__main__":
    sys.exit(main())
