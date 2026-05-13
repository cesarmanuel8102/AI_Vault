import ast, pathlib, json

def scan(path_str: str):
    p = pathlib.Path(path_str)
    src = p.read_text(encoding="utf-8", errors="replace")
    tree = ast.parse(src)
    classes = []
    funcs = []
    imports = []
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            classes.append(node.name)
        elif isinstance(node, ast.FunctionDef):
            funcs.append(node.name)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            # keep only a small head for readability
            seg = ast.get_source_segment(src, node) or ""
            if seg:
                imports.append(seg)
    return {
        "file": str(p),
        "classes": classes,
        "functions_head": funcs[:80],
        "imports_head": imports[:40],
        "len_chars": len(src),
    }

def runner_imports(path_str: str):
    p = pathlib.Path(path_str)
    src = p.read_text(encoding="utf-8", errors="replace")
    tree = ast.parse(src)
    out = []
    for node in tree.body:
        if isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            names = [n.name for n in node.names]
            if ("risk" in mod.lower()) or ("RiskEngine" in names):
                out.append({"module": mod, "names": names})
    return {"file": str(p), "imports": out}

data = {
    "repo_risk_engine": scan(r"C:\AI_VAULT\workspace\brainlab\brainlab\risk\risk_engine.py"),
    "tmp_smoke_risk_engine": scan(r"C:\AI_VAULT\tmp_agent\smoke_risk_engine.py"),
    "tmp_smoke_runner_imports": runner_imports(r"C:\AI_VAULT\tmp_agent\smoke_runner.py"),
}
print(json.dumps(data, ensure_ascii=False, indent=2))
