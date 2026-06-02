"""B7-09 shim cleanliness AST audit.

Verifies that BrainSession._prefers_no_tool_analysis and
BrainSession._has_explicit_tool_target are clean staticmethod shims with:
  - @staticmethod decorator
  - body = optional docstring + single Return
  - Return calls _tap.<expected_name>(message)
  - no msg/any/re.search/_CODE_ANALYSIS_PATH_RE/tuple-of-markers inline

Also verifies session_tool_analysis_prefs.py contains the real logic and
does not import session/BrainSession.

Exit 0 = PASS, exit 1 = FAIL with details on stderr.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]  # .../AI_VAULT
SESSION_PY = ROOT / "tmp_agent" / "brain_v9" / "core" / "session.py"
TAP_PY = ROOT / "tmp_agent" / "brain_v9" / "core" / "session_tool_analysis_prefs.py"

EXPECTED_SHIMS = {
    "_prefers_no_tool_analysis": "prefers_no_tool_analysis",
    "_has_explicit_tool_target": "has_explicit_tool_target",
}


def _has_decorator(fn: ast.FunctionDef, name: str) -> bool:
    for d in fn.decorator_list:
        if isinstance(d, ast.Name) and d.id == name:
            return True
    return False


def audit_shim(fn: ast.FunctionDef, expected_target: str) -> list[str]:
    errs: list[str] = []
    if not _has_decorator(fn, "staticmethod"):
        errs.append(f"{fn.name}: missing @staticmethod decorator")
    body = list(fn.body)
    # strip leading docstring
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) and isinstance(body[0].value.value, str):
        body = body[1:]
    if len(body) != 1:
        errs.append(f"{fn.name}: effective body has {len(body)} stmts, expected 1 Return")
        return errs
    stmt = body[0]
    if not isinstance(stmt, ast.Return) or stmt.value is None:
        errs.append(f"{fn.name}: single stmt is not a Return")
        return errs
    call = stmt.value
    if not isinstance(call, ast.Call):
        errs.append(f"{fn.name}: Return value is not a Call")
        return errs
    func = call.func
    if not (isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name) and func.value.id == "_tap" and func.attr == expected_target):
        errs.append(f"{fn.name}: Return must call _tap.{expected_target}(...), got {ast.unparse(func)}")
    if len(call.args) != 1 or not isinstance(call.args[0], ast.Name) or call.args[0].id != "message":
        errs.append(f"{fn.name}: call must pass single Name 'message', got {[ast.unparse(a) for a in call.args]}")
    # Walk full original fn for forbidden constructs (excluding docstring)
    for node in ast.walk(fn):
        if isinstance(node, ast.Name) and node.id == "msg":
            errs.append(f"{fn.name}: forbidden ast.Name 'msg' present")
            break
    for node in ast.walk(fn):
        if isinstance(node, ast.Call):
            f = node.func
            if isinstance(f, ast.Name) and f.id == "any":
                errs.append(f"{fn.name}: forbidden any(...) call present")
            if isinstance(f, ast.Attribute) and f.attr == "search":
                # allow only inside the docstring? no — re.search / _CODE_ANALYSIS_PATH_RE.search forbidden anywhere
                errs.append(f"{fn.name}: forbidden .search(...) call present ({ast.unparse(f)})")
    for node in ast.walk(fn):
        if isinstance(node, ast.Tuple) and len(node.elts) >= 2 and all(isinstance(e, ast.Constant) and isinstance(e.value, str) for e in node.elts):
            errs.append(f"{fn.name}: forbidden inline tuple-of-string-markers present")
            break
    return errs


def main() -> int:
    src = SESSION_PY.read_text(encoding="utf-8")
    tree = ast.parse(src)
    brain_session = None
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "BrainSession":
            brain_session = node
            break
    if brain_session is None:
        print("FAIL: BrainSession class not found", file=sys.stderr)
        return 1

    found: dict[str, ast.FunctionDef] = {}
    for item in brain_session.body:
        if isinstance(item, ast.FunctionDef) and item.name in EXPECTED_SHIMS:
            found[item.name] = item

    all_errs: list[str] = []
    for shim_name, target in EXPECTED_SHIMS.items():
        if shim_name not in found:
            all_errs.append(f"{shim_name}: not found in BrainSession")
            continue
        all_errs.extend(audit_shim(found[shim_name], target))

    # Audit session_tool_analysis_prefs.py
    tap_src = TAP_PY.read_text(encoding="utf-8")
    tap_tree = ast.parse(tap_src)
    fn_names: set[str] = set()
    for node in ast.walk(tap_tree):
        if isinstance(node, ast.FunctionDef):
            fn_names.add(node.name)
    for needed in ("prefers_no_tool_analysis", "has_explicit_tool_target"):
        if needed not in fn_names:
            all_errs.append(f"session_tool_analysis_prefs.py: missing function {needed}")

    for node in ast.walk(tap_tree):
        if isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            if mod.endswith("session") or "BrainSession" in {a.name for a in node.names}:
                if mod.endswith(".session") or mod == "session" or "BrainSession" in {a.name for a in node.names}:
                    all_errs.append(f"session_tool_analysis_prefs.py: forbidden import from '{mod}' names={[a.name for a in node.names]}")
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.endswith(".session") or alias.name == "session":
                    all_errs.append(f"session_tool_analysis_prefs.py: forbidden import '{alias.name}'")

    # Check that BrainSession is not referenced in actual code (Name nodes),
    # only in docstrings/comments (which are fine for cross-reference docs).
    for node in ast.walk(tap_tree):
        if isinstance(node, ast.Name) and node.id == "BrainSession":
            all_errs.append("session_tool_analysis_prefs.py: code references BrainSession (ast.Name)")
        if isinstance(node, ast.Attribute) and getattr(node, "attr", None) == "BrainSession":
            all_errs.append("session_tool_analysis_prefs.py: code references .BrainSession (ast.Attribute)")

    if all_errs:
        print("B7_09_SHIM_CLEANLINESS_AST_AUDIT: FAIL", flush=True)
        for e in all_errs:
            print(f"  - {e}", file=sys.stderr)
        return 1
    print("B7_09_SHIM_CLEANLINESS_AST_AUDIT: PASS", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
