"""B7-06 Phase A/B/C analyzer extension. Read-only."""
from __future__ import annotations
import ast, json, re
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SESSION = ROOT / "tmp_agent" / "brain_v9" / "core" / "session.py"
EVID = ROOT / "tmp_agent" / "b7_strangler_evidence"

src = SESSION.read_text(encoding="utf-8")
tree = ast.parse(src)

# Find BrainSession class
bs = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "BrainSession")

methods = []
for n in bs.body:
    if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
        decos = [ast.unparse(d) for d in n.decorator_list]
        first_arg = n.args.args[0].arg if n.args.args else None
        # count self/cls uses in body
        self_uses = sum(1 for x in ast.walk(n) if isinstance(x, ast.Name) and x.id == "self")
        cls_uses = sum(1 for x in ast.walk(n) if isinstance(x, ast.Name) and x.id == "cls")
        # also count attribute access self.X / cls.X
        self_attr = sum(1 for x in ast.walk(n) if isinstance(x, ast.Attribute) and isinstance(x.value, ast.Name) and x.value.id == "self")
        cls_attr = sum(1 for x in ast.walk(n) if isinstance(x, ast.Attribute) and isinstance(x.value, ast.Name) and x.value.id == "cls")
        methods.append({
            "name": n.name,
            "line_start": n.lineno,
            "line_end": n.end_lineno,
            "size": n.end_lineno - n.lineno + 1,
            "decorators": decos,
            "is_async": isinstance(n, ast.AsyncFunctionDef),
            "first_arg": first_arg,
            "self_uses_total": self_uses + self_attr,
            "cls_uses_total": cls_uses + cls_attr,
        })

# group by prefix (token before first underscore, with leading _ marker)
def prefix_of(name: str) -> str:
    if name.startswith("__"): return "__dunder__"
    if name.startswith("_"):
        rest = name[1:]
        return "_" + rest.split("_", 1)[0]
    return name.split("_", 1)[0]

groups = defaultdict(list)
for m in methods:
    groups[prefix_of(m["name"])].append(m)

group_summary = []
for pfx, ms in sorted(groups.items(), key=lambda kv: -sum(x["size"] for x in kv[1])):
    pure = [m for m in ms if m["self_uses_total"] == 0 and ("staticmethod" in m["decorators"] or "classmethod" in m["decorators"])]
    group_summary.append({
        "prefix": pfx,
        "method_count": len(ms),
        "total_lines": sum(m["size"] for m in ms),
        "pure_count": len(pure),
        "pure_total_lines": sum(m["size"] for m in pure),
        "first_line": min(m["line_start"] for m in ms),
        "last_line": max(m["line_end"] for m in ms),
        "names_sample": [m["name"] for m in ms[:6]],
    })

# -------- _fmt_* bodies deep analysis --------
fmt_methods = [m for m in methods if m["name"].startswith("_fmt_")]
fmt_bodies = []
fmt_node_map = {n.name: n for n in bs.body if isinstance(n, ast.FunctionDef) and n.name.startswith("_fmt_")}

EXCEPTION_NAMES = set()
BUILTIN_CALLS = Counter()
CROSS_FMT_CALLS = Counter()
USES_SELF = Counter()
USES_CLS_ATTR = Counter()
EXTERNAL_NAMES = Counter()

for name, node in fmt_node_map.items():
    info = {"name": name, "calls_external": [], "uses_cls_attr": [], "uses_self": False,
            "exceptions": [], "raises": [], "imports_inside": [], "string_literal_count": 0,
            "returns_str": True}
    for child in ast.walk(node):
        if isinstance(child, ast.Call):
            f = child.func
            if isinstance(f, ast.Name):
                BUILTIN_CALLS[f.id] += 1
                info["calls_external"].append(f.id)
            elif isinstance(f, ast.Attribute):
                if isinstance(f.value, ast.Name) and f.value.id == "cls":
                    info["uses_cls_attr"].append(f.attr)
                    if f.attr.startswith("_fmt_"):
                        CROSS_FMT_CALLS[(name, f.attr)] += 1
        elif isinstance(child, ast.Name) and child.id == "self":
            info["uses_self"] = True
            USES_SELF[name] += 1
        elif isinstance(child, ast.Attribute) and isinstance(child.value, ast.Name) and child.value.id == "cls":
            USES_CLS_ATTR[name] += 1
        elif isinstance(child, ast.Try):
            for h in child.handlers:
                if h.type is not None:
                    info["exceptions"].append(ast.unparse(h.type))
        elif isinstance(child, ast.Raise) and child.exc is not None:
            info["raises"].append(ast.unparse(child.exc))
        elif isinstance(child, (ast.Import, ast.ImportFrom)):
            info["imports_inside"].append(ast.unparse(child))
        elif isinstance(child, ast.Constant) and isinstance(child.value, str):
            info["string_literal_count"] += 1
    fmt_bodies.append(info)

# external callers of _fmt_* names anywhere in session.py (besides dispatcher)
fmt_names = set(fmt_node_map.keys())
caller_hits = []
for fname in fmt_names:
    pat = re.compile(rf"\b{re.escape(fname)}\b")
    for i, line in enumerate(src.splitlines(), 1):
        if pat.search(line):
            caller_hits.append({"name": fname, "line": i, "text": line.strip()})

# scan whole repo for external imports/usages of _fmt_*
external_callers_repo = []
for p in (ROOT / "tmp_agent" / "brain_v9").rglob("*.py"):
    if p.resolve() == SESSION.resolve():
        continue
    try:
        text = p.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        continue
    for fname in fmt_names:
        if fname in text:
            external_callers_repo.append({"file": str(p.relative_to(ROOT)), "name": fname})

# also _format_tool_result / _format_action_value / _TOOL_FORMATTERS external usage
for sym in ("_format_tool_result", "_format_action_value", "_TOOL_FORMATTERS"):
    for p in (ROOT / "tmp_agent" / "brain_v9").rglob("*.py"):
        if p.resolve() == SESSION.resolve():
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        if sym in text:
            external_callers_repo.append({"file": str(p.relative_to(ROOT)), "name": sym})

result = {
    "session_total_lines": len(src.splitlines()),
    "brain_session_class": {"line_start": bs.lineno, "line_end": bs.end_lineno, "method_count": len(methods)},
    "method_prefix_groups": group_summary,
    "all_methods": methods,
    "fmt_bodies_analysis": fmt_bodies,
    "fmt_builtin_calls": BUILTIN_CALLS.most_common(30),
    "fmt_cross_calls": [{"caller": k[0], "callee": k[1], "n": v} for k, v in CROSS_FMT_CALLS.items()],
    "fmt_uses_self_count": dict(USES_SELF),
    "fmt_uses_cls_attr_count": dict(USES_CLS_ATTR),
    "fmt_local_caller_lines": caller_hits,
    "fmt_and_dispatcher_external_callers_repo": external_callers_repo,
}

(EVID / "_b7_06_inventory_extra.json").write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
print("WROTE", EVID / "_b7_06_inventory_extra.json")
print("methods_total:", len(methods))
print("groups:", len(group_summary))
print("fmt_count:", len(fmt_methods))
print("fmt_cross_calls:", len(CROSS_FMT_CALLS))
print("fmt_uses_self:", sum(USES_SELF.values()))
print("fmt_uses_cls_attr:", sum(USES_CLS_ATTR.values()))
print("local_caller_lines:", len(caller_hits))
print("external_callers_repo:", len(external_callers_repo))
