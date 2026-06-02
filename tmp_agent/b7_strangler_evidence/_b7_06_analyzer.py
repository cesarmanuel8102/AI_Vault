"""B7-06 AST inventory analyzer (read-only)."""
import ast
import json
import sys
from pathlib import Path

SESSION_PY = Path("tmp_agent/brain_v9/core/session.py")
src = SESSION_PY.read_text(encoding="utf-8")
lines = src.splitlines()
tree = ast.parse(src)


def get_decorator_names(node):
    names = []
    for d in getattr(node, "decorator_list", []):
        if isinstance(d, ast.Name):
            names.append(d.id)
        elif isinstance(d, ast.Attribute):
            names.append(d.attr)
        elif isinstance(d, ast.Call):
            f = d.func
            if isinstance(f, ast.Name):
                names.append(f.id)
            elif isinstance(f, ast.Attribute):
                names.append(f.attr)
    return names


def count_self_cls(node):
    self_n = 0
    cls_n = 0
    for sub in ast.walk(node):
        if isinstance(sub, ast.Name):
            if sub.id == "self":
                self_n += 1
            elif sub.id == "cls":
                cls_n += 1
    return self_n, cls_n


def method_size(node):
    end = getattr(node, "end_lineno", node.lineno)
    return end - node.lineno + 1, node.lineno, end


# Top-level classes / functions / constants / imports
top_classes = []
top_funcs = []
top_consts = []
top_imports = []

for node in tree.body:
    if isinstance(node, ast.ClassDef):
        end = getattr(node, "end_lineno", node.lineno)
        top_classes.append({"name": node.name, "line_start": node.lineno, "line_end": end, "size": end - node.lineno + 1})
    elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        end = getattr(node, "end_lineno", node.lineno)
        top_funcs.append({"name": node.name, "line_start": node.lineno, "line_end": end, "size": end - node.lineno + 1})
    elif isinstance(node, (ast.Assign, ast.AnnAssign)):
        targets = []
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name):
                    targets.append(t.id)
        else:
            if isinstance(node.target, ast.Name):
                targets.append(node.target.id)
        for tname in targets:
            top_consts.append({"name": tname, "line": node.lineno})
    elif isinstance(node, ast.Import):
        top_imports.append({"kind": "import", "names": [a.name for a in node.names], "line": node.lineno})
    elif isinstance(node, ast.ImportFrom):
        top_imports.append({"kind": "from", "module": node.module, "names": [a.name for a in node.names], "line": node.lineno})

# BrainSession class methods
brain_session = next((n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "BrainSession"), None)

methods = []
if brain_session:
    for node in brain_session.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            size, ls, le = method_size(node)
            sn, cn = count_self_cls(node)
            decos = get_decorator_names(node)
            args = [a.arg for a in node.args.args]
            methods.append({
                "name": node.name,
                "line_start": ls,
                "line_end": le,
                "size": size,
                "self_uses": sn,
                "cls_uses": cn,
                "decorators": decos,
                "is_async": isinstance(node, ast.AsyncFunctionDef),
                "first_arg": args[0] if args else None,
                "n_args": len(args),
            })

# Method group summaries by prefix
prefixes = ["_fmt_", "_format_", "_render_", "_extract_", "_truncate_", "_context_",
            "_cmd_", "_route_", "_save_", "_load_", "_build_", "_get_", "_set_",
            "_should_", "_is_", "_has_", "_looks_like_", "_prefers_", "_sanitize_",
            "_handle_", "_process_", "_run_", "_validate_", "_resolve_"]
groups = {}
for m in methods:
    for p in prefixes:
        if m["name"].startswith(p):
            groups.setdefault(p, {"count": 0, "total_size": 0, "methods": []})
            groups[p]["count"] += 1
            groups[p]["total_size"] += m["size"]
            groups[p]["methods"].append({"name": m["name"], "size": m["size"], "decos": m["decorators"], "self": m["self_uses"], "cls": m["cls_uses"]})
            break

# Pure candidates (self_uses==0 AND cls_uses==0, OR staticmethod/classmethod with low coupling)
pure_candidates = [m for m in methods if m["self_uses"] == 0 and ("staticmethod" in m["decorators"] or "classmethod" in m["decorators"] or m["first_arg"] not in ("self", "cls"))]

# Largest methods
largest = sorted(methods, key=lambda m: m["size"], reverse=True)[:20]

# fmt bundle full detail
fmt_methods = [m for m in methods if m["name"].startswith("_fmt_")]

# Look for _TOOL_FORMATTERS and _format_tool_result
fmt_dispatcher_meta = {}
for m in methods:
    if m["name"] in ("_format_tool_result", "_format_action_value"):
        # capture body text
        body = "\n".join(lines[m["line_start"]-1:m["line_end"]])
        fmt_dispatcher_meta[m["name"]] = {
            "size": m["size"], "line_start": m["line_start"], "line_end": m["line_end"],
            "decorators": m["decorators"], "self": m["self_uses"], "cls": m["cls_uses"],
            "uses_TOOL_FORMATTERS": "_TOOL_FORMATTERS" in body,
            "uses_getattr_cls": "getattr(cls" in body or "getattr(self" in body,
        }

# Find _TOOL_FORMATTERS as class attribute
tool_formatters_assign = None
if brain_session:
    for node in brain_session.body:
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id == "_TOOL_FORMATTERS":
                    end = getattr(node, "end_lineno", node.lineno)
                    body = "\n".join(lines[node.lineno-1:end])
                    tool_formatters_assign = {"line_start": node.lineno, "line_end": end, "size": end - node.lineno + 1, "snippet": body[:600]}

result = {
    "session_py_total_lines": len(lines),
    "top_level": {
        "classes": top_classes,
        "functions_count": len(top_funcs),
        "functions": top_funcs,
        "constants_count": len(top_consts),
        "constants": top_consts,
        "imports_count": len(top_imports),
        "imports": top_imports,
    },
    "brain_session": {
        "line_start": brain_session.lineno if brain_session else None,
        "line_end": getattr(brain_session, "end_lineno", None) if brain_session else None,
        "method_count": len(methods),
        "method_groups_by_prefix": groups,
    },
    "pure_candidates_count": len(pure_candidates),
    "pure_candidates_top20_by_size": sorted(pure_candidates, key=lambda m: m["size"], reverse=True)[:20],
    "largest_methods_top20": largest,
    "fmt_bundle": {
        "count": len(fmt_methods),
        "methods": fmt_methods,
        "total_size_lines": sum(m["size"] for m in fmt_methods),
    },
    "fmt_dispatcher_meta": fmt_dispatcher_meta,
    "tool_formatters_assign": tool_formatters_assign,
}

Path("tmp_agent/b7_strangler_evidence/_b7_06_inventory_raw.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
print("OK", len(lines), "lines;", len(methods), "methods;", len(fmt_methods), "_fmt_*;", len(pure_candidates), "pure")
