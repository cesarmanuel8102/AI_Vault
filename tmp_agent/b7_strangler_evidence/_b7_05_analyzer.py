"""B7-STRANGLER-05 read-only AST inventory of session.py.

Writes intermediate JSON for the inventory + ranking phases. Does not
modify session.py or any productive code.
"""
from __future__ import annotations

import ast
import json
import os
import sys
from collections import defaultdict

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SESSION_PATH = os.path.join(ROOT, "tmp_agent", "brain_v9", "core", "session.py")
OUT_DIR = os.path.dirname(__file__)

src = open(SESSION_PATH, "r", encoding="utf-8").read()
lines = src.splitlines()
total_lines = len(lines)

tree = ast.parse(src)

top_classes = []
top_functions = []
top_constants = []
top_imports = []

for node in tree.body:
    if isinstance(node, ast.ClassDef):
        top_classes.append({
            "name": node.name,
            "lineno": node.lineno,
            "end_lineno": getattr(node, "end_lineno", None),
            "size": (getattr(node, "end_lineno", node.lineno) - node.lineno + 1),
        })
    elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        top_functions.append({
            "name": node.name,
            "lineno": node.lineno,
            "end_lineno": getattr(node, "end_lineno", None),
            "size": (getattr(node, "end_lineno", node.lineno) - node.lineno + 1),
            "is_async": isinstance(node, ast.AsyncFunctionDef),
        })
    elif isinstance(node, ast.Assign):
        for tgt in node.targets:
            if isinstance(tgt, ast.Name):
                top_constants.append({"name": tgt.id, "lineno": node.lineno})
    elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
        top_constants.append({"name": node.target.id, "lineno": node.lineno, "annotated": True})
    elif isinstance(node, (ast.Import, ast.ImportFrom)):
        if isinstance(node, ast.Import):
            for a in node.names:
                top_imports.append({"kind": "import", "name": a.name, "asname": a.asname, "lineno": node.lineno})
        else:
            for a in node.names:
                top_imports.append({
                    "kind": "from",
                    "module": node.module,
                    "name": a.name,
                    "asname": a.asname,
                    "level": node.level,
                    "lineno": node.lineno,
                })

# Find BrainSession class
brain = None
for c in tree.body:
    if isinstance(c, ast.ClassDef) and c.name == "BrainSession":
        brain = c
        break

methods = []
if brain is not None:
    for item in brain.body:
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
            decorators = []
            for d in item.decorator_list:
                if isinstance(d, ast.Name):
                    decorators.append(d.id)
                elif isinstance(d, ast.Attribute):
                    decorators.append(ast.unparse(d))
                else:
                    try:
                        decorators.append(ast.unparse(d))
                    except Exception:
                        decorators.append("<expr>")
            args = item.args
            arg_names = [a.arg for a in args.args]
            first_arg = arg_names[0] if arg_names else None
            kind = "method"
            if "staticmethod" in decorators:
                kind = "staticmethod"
            elif "classmethod" in decorators:
                kind = "classmethod"
            elif first_arg == "cls":
                kind = "classmethod_implicit"
            elif first_arg != "self":
                kind = "function_in_class"

            # count self./cls. attribute usages
            self_uses = 0
            cls_uses = 0
            for sub in ast.walk(item):
                if isinstance(sub, ast.Attribute) and isinstance(sub.value, ast.Name):
                    if sub.value.id == "self":
                        self_uses += 1
                    elif sub.value.id == "cls":
                        cls_uses += 1

            size = (getattr(item, "end_lineno", item.lineno) - item.lineno + 1)
            methods.append({
                "name": item.name,
                "lineno": item.lineno,
                "end_lineno": getattr(item, "end_lineno", None),
                "size": size,
                "kind": kind,
                "decorators": decorators,
                "is_async": isinstance(item, ast.AsyncFunctionDef),
                "self_uses": self_uses,
                "cls_uses": cls_uses,
            })

# Sort methods by size desc and by name patterns
methods_by_size = sorted(methods, key=lambda m: -m["size"])
top_30_by_size = methods_by_size[:30]

# Group by prefix patterns
prefix_groups = defaultdict(list)
for m in methods:
    n = m["name"]
    if n.startswith("_fmt_"):
        prefix_groups["_fmt_"].append(m)
    elif n.startswith("_format_"):
        prefix_groups["_format_"].append(m)
    elif n.startswith("_render_"):
        prefix_groups["_render_"].append(m)
    elif n.startswith("_cmd_"):
        prefix_groups["_cmd_"].append(m)
    elif n.startswith("_should_"):
        prefix_groups["_should_"].append(m)
    elif n.startswith("_handle_"):
        prefix_groups["_handle_"].append(m)
    elif n.startswith("_sanitize_"):
        prefix_groups["_sanitize_"].append(m)
    elif n.startswith("_extract_"):
        prefix_groups["_extract_"].append(m)
    elif n.startswith("_route_"):
        prefix_groups["_route_"].append(m)
    elif n.startswith("_emit_") or n.startswith("_log_"):
        prefix_groups["_emit_log_"].append(m)
    elif n.startswith("_save_") or n.startswith("_load_"):
        prefix_groups["_save_load_"].append(m)
    else:
        prefix_groups["_other_"].append(m)

prefix_summary = {
    k: {
        "count": len(v),
        "total_lines": sum(m["size"] for m in v),
        "names": [m["name"] for m in v],
    }
    for k, v in sorted(prefix_groups.items())
}

# Pure-ish methods: staticmethod/classmethod with low self/cls usage
pure_candidates = [
    m for m in methods
    if m["kind"] in ("staticmethod", "classmethod", "classmethod_implicit")
    and m["self_uses"] == 0
]
pure_candidates_sorted = sorted(pure_candidates, key=lambda m: -m["size"])

inventory = {
    "session_py_path": SESSION_PATH.replace("\\", "/"),
    "session_py_lines": total_lines,
    "cumulative_reduction": {
        "pre_b7_02": 7637,
        "post_b7_02": 6140,
        "post_b7_03": 5925,
        "post_b7_04": total_lines,
        "delta_b7_02": 7637 - 6140,
        "delta_b7_03": 6140 - 5925,
        "delta_b7_04": 5925 - total_lines,
        "total_reduction_lines": 7637 - total_lines,
        "total_reduction_pct": round((7637 - total_lines) / 7637 * 100, 2),
    },
    "top_level_classes": top_classes,
    "top_level_functions_count": len(top_functions),
    "top_level_functions": top_functions,
    "top_level_constants_count": len(top_constants),
    "top_level_constants": top_constants,
    "top_level_imports_count": len(top_imports),
    "top_level_imports_sample": top_imports[:60],
    "brain_session_method_count": len(methods),
    "brain_session_method_prefix_groups": prefix_summary,
    "top_30_methods_by_size": top_30_by_size,
    "pure_static_classmethod_candidates": pure_candidates_sorted,
}

with open(os.path.join(OUT_DIR, "b7_05_session_inventory.json"), "w", encoding="utf-8") as f:
    json.dump(inventory, f, indent=2)

print("INVENTORY_OK", total_lines, "methods=", len(methods),
      "pure_candidates=", len(pure_candidates_sorted))
