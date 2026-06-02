"""B7-STRANGLER-04 inventory analyzer (read-only).

Scans tmp_agent/brain_v9/core/session.py and emits a structural inventory
JSON under tmp_agent/b7_strangler_evidence/.
"""
from __future__ import annotations

import ast
import json
import re
from pathlib import Path

ROOT = Path(r"C:\AI_VAULT")
SRC = ROOT / "tmp_agent" / "brain_v9" / "core" / "session.py"
EVID = ROOT / "tmp_agent" / "b7_strangler_evidence"

src_text = SRC.read_text(encoding="utf-8")
src_lines = src_text.splitlines()
total_lines = len(src_lines)

tree = ast.parse(src_text)

top_level_classes = []
top_level_functions = []
top_level_constants = []
imports = []

for node in tree.body:
    if isinstance(node, ast.ClassDef):
        top_level_classes.append({
            "name": node.name,
            "lineno": node.lineno,
            "end_lineno": node.end_lineno,
            "body_lines": (node.end_lineno - node.lineno + 1),
        })
    elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        top_level_functions.append({
            "name": node.name,
            "lineno": node.lineno,
            "end_lineno": node.end_lineno,
            "body_lines": (node.end_lineno - node.lineno + 1),
            "is_async": isinstance(node, ast.AsyncFunctionDef),
        })
    elif isinstance(node, ast.Assign):
        for tgt in node.targets:
            if isinstance(tgt, ast.Name):
                top_level_constants.append({
                    "name": tgt.id,
                    "lineno": node.lineno,
                    "end_lineno": node.end_lineno,
                })
    elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
        top_level_constants.append({
            "name": node.target.id,
            "lineno": node.lineno,
            "end_lineno": node.end_lineno,
        })
    elif isinstance(node, (ast.Import, ast.ImportFrom)):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append({"module": alias.name, "lineno": node.lineno, "kind": "import"})
        else:
            imports.append({
                "module": node.module or "",
                "lineno": node.lineno,
                "kind": "from",
                "names": [a.name for a in node.names],
                "level": node.level,
            })

# Inspect BrainSession class methods
brain_session_methods = []
brain_session_class = None
for node in tree.body:
    if isinstance(node, ast.ClassDef) and node.name == "BrainSession":
        brain_session_class = node
        for item in node.body:
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                # Inspect decorators
                deco_names = []
                for d in item.decorator_list:
                    if isinstance(d, ast.Name):
                        deco_names.append(d.id)
                    elif isinstance(d, ast.Attribute):
                        deco_names.append(ast.unparse(d))
                    elif isinstance(d, ast.Call):
                        try:
                            deco_names.append(ast.unparse(d.func))
                        except Exception:
                            deco_names.append("call")
                # arg names
                args = [a.arg for a in item.args.args]
                first_arg = args[0] if args else None
                # walk body for self./cls. usage and external module touches
                self_refs = 0
                cls_refs = 0
                external_attrs = set()
                for sub in ast.walk(item):
                    if isinstance(sub, ast.Attribute) and isinstance(sub.value, ast.Name):
                        if sub.value.id == "self":
                            self_refs += 1
                        elif sub.value.id == "cls":
                            cls_refs += 1
                brain_session_methods.append({
                    "name": item.name,
                    "lineno": item.lineno,
                    "end_lineno": item.end_lineno,
                    "body_lines": (item.end_lineno - item.lineno + 1),
                    "is_async": isinstance(item, ast.AsyncFunctionDef),
                    "decorators": deco_names,
                    "first_arg": first_arg,
                    "self_refs": self_refs,
                    "cls_refs": cls_refs,
                    "n_args": len(args),
                })
            elif isinstance(item, ast.Assign):
                for tgt in item.targets:
                    if isinstance(tgt, ast.Name):
                        brain_session_methods.append({
                            "name": tgt.id,
                            "kind": "class_attr",
                            "lineno": item.lineno,
                            "end_lineno": item.end_lineno,
                            "body_lines": (item.end_lineno - item.lineno + 1),
                        })

# Largest methods
methods_only = [m for m in brain_session_methods if "kind" not in m]
methods_only.sort(key=lambda m: m["body_lines"], reverse=True)
largest_methods = methods_only[:30]

# Static/class methods (low coupling candidates)
pure_methods = [m for m in methods_only if any(d in ("staticmethod", "classmethod") for d in m.get("decorators", []))]
pure_methods.sort(key=lambda m: m["body_lines"], reverse=True)

# Method-name-prefix groupings (heuristic)
def prefix_group(name: str) -> str:
    if name.startswith("_cmd_"):
        return "_cmd_*"
    if name.startswith("_fmt_"):
        return "_fmt_*"
    if name.startswith("_render_"):
        return "_render_*"
    if name.startswith("_format_"):
        return "_format_*"
    if name.startswith("_route_"):
        return "_route_*"
    if name.startswith("_run_tool"):
        return "_run_tool*"
    if name.startswith("_tool_"):
        return "_tool_*"
    if name.startswith("_handle_"):
        return "_handle_*"
    if name.startswith("_apply_"):
        return "_apply_*"
    if name.startswith("_select_"):
        return "_select_*"
    if name.startswith("_build_"):
        return "_build_*"
    if name.startswith("_get_") or name.startswith("_resolve_"):
        return "_get/_resolve_*"
    if name.startswith("_should_") or name.startswith("_is_") or name.startswith("_looks_") or name.startswith("_has_") or name.startswith("_prefers_"):
        return "_predicate_*"
    if name.startswith("_normalize_"):
        return "_normalize_*"
    if name.startswith("_summarize_"):
        return "_summarize_*"
    if name.startswith("_log_") or name.startswith("_record_"):
        return "_log/_record_*"
    if name.startswith("_persist_") or name.startswith("_save_") or name.startswith("_load_"):
        return "_persist/_save/_load_*"
    if name.startswith("_chat_") or name == "chat":
        return "_chat_*"
    if name.startswith("_maybe_"):
        return "_maybe_*"
    if name.startswith("_tool01"):
        return "_tool01_*"
    if name.startswith("__"):
        return "dunder"
    return "_other_"

groups = {}
for m in methods_only:
    g = prefix_group(m["name"])
    groups.setdefault(g, {"count": 0, "total_lines": 0, "names": []})
    groups[g]["count"] += 1
    groups[g]["total_lines"] += m["body_lines"]
    groups[g]["names"].append(m["name"])

groups_sorted = sorted(groups.items(), key=lambda kv: kv[1]["total_lines"], reverse=True)

# Search for SLASH_COMMANDS dict / Tool01 references / regex constants
text_search = {
    "SLASH_COMMANDS_def_count": len(re.findall(r"^\s*SLASH_COMMANDS\s*=", src_text, re.M)),
    "AGENT_INTENTS_def_count": len(re.findall(r"^\s*AGENT_INTENTS\s*=", src_text, re.M)),
    "AGENT_KEYWORDS_def_count": len(re.findall(r"^\s*AGENT_KEYWORDS\s*=", src_text, re.M)),
    "_CODE_ANALYSIS_PATH_RE_def_count": len(re.findall(r"^\s*_CODE_ANALYSIS_PATH_RE\s*=", src_text, re.M)),
    "_LEAK_TAIL_RE_def_count": len(re.findall(r"^\s*_LEAK_TAIL_RE\s*=", src_text, re.M)),
    "_PROCESS_START_TIME_def_count": len(re.findall(r"^\s*_PROCESS_START_TIME\s*=", src_text, re.M)),
    "_CONTINUE_WORDS_RE_def_count": len(re.findall(r"^\s*_CONTINUE_WORDS_RE\s*=", src_text, re.M)),
    "_CORRECTION_RE_def_count": len(re.findall(r"^\s*_CORRECTION_RE\s*=", src_text, re.M)),
    "Tool01_class_count": len(re.findall(r"^\s*class\s+Tool01\b", src_text, re.M)),
    "tool01_method_count": sum(1 for m in methods_only if "tool01" in m["name"].lower()),
    "_cmd_method_count": sum(1 for m in methods_only if m["name"].startswith("_cmd_")),
    "_fmt_method_count": sum(1 for m in methods_only if m["name"].startswith("_fmt_")),
    "_render_method_count": sum(1 for m in methods_only if m["name"].startswith("_render_")),
    "_format_method_count": sum(1 for m in methods_only if m["name"].startswith("_format_")),
    "_normalize_method_count": sum(1 for m in methods_only if m["name"].startswith("_normalize_")),
    "predicate_shim_count": sum(1 for m in methods_only if m["body_lines"] <= 3 and any(d in ("staticmethod","classmethod") for d in m.get("decorators", []))),
}

# Lines of constants block at top
# capture all top-level constants between line 1 and first class
first_class_line = min((c["lineno"] for c in top_level_classes), default=total_lines)

# Locate exact line ranges of key candidate blocks
def find_block(name_pattern: str):
    rx = re.compile(r"^(\s*)" + name_pattern + r"\s*=", re.M)
    out = []
    for m in rx.finditer(src_text):
        line_no = src_text.count("\n", 0, m.start()) + 1
        out.append({"name": name_pattern, "line": line_no})
    return out

candidate_constants = {}
for name in [
    "AGENT_INTENTS","AGENT_KEYWORDS","_AGENT_PATTERNS",
    "_CODE_ANALYSIS_PATH_RE","_LEAK_TAIL_RE","_PROCESS_START_TIME",
    "_CONTINUE_WORDS_RE","_CORRECTION_RE","SLASH_COMMANDS",
    "_CONFIRM_PATTERNS","_TEMPORAL_QUERY_RE","_RECENT_ACTIVITY_PATTERNS",
    "DEFAULT_PRIORITY","CHAT_DEV_MODE","CHAT_DEV_DEFAULTS",
]:
    candidate_constants[name] = find_block(re.escape(name))

inventory = {
    "session_py": str(SRC),
    "total_lines": total_lines,
    "cumulative_reduction": {
        "pre_b7_02_lines": 7637,
        "post_b7_02_lines": 6140,
        "post_b7_03_lines": total_lines,
        "delta_b7_02": 7637 - 6140,
        "delta_b7_03": 6140 - total_lines,
        "delta_total": 7637 - total_lines,
    },
    "imports_count": len(imports),
    "top_level_classes": top_level_classes,
    "top_level_functions": top_level_functions,
    "top_level_constants": top_level_constants,
    "first_class_line": first_class_line,
    "brain_session": {
        "exists": brain_session_class is not None,
        "lineno": brain_session_class.lineno if brain_session_class else None,
        "end_lineno": brain_session_class.end_lineno if brain_session_class else None,
        "method_count": len(methods_only),
        "class_attrs_count": sum(1 for m in brain_session_methods if m.get("kind") == "class_attr"),
    },
    "method_groups_by_prefix": [
        {"group": g, "count": v["count"], "total_lines": v["total_lines"], "sample_names": v["names"][:8]}
        for g, v in groups_sorted
    ],
    "largest_methods_top30": largest_methods,
    "pure_methods_top30": pure_methods[:30],
    "candidate_constant_locations": candidate_constants,
    "text_search": text_search,
}

EVID.mkdir(parents=True, exist_ok=True)
out_json = EVID / "b7_04_session_inventory.json"
out_json.write_text(json.dumps(inventory, indent=2, default=str), encoding="utf-8")
print("WROTE", out_json, "lines", total_lines)
