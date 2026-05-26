from pathlib import Path
import json, re

root = Path("C:/AI_VAULT")
out_dir = root / "tmp_agent" / "dashboard_v2_r105_audit_evidence"
out_dir.mkdir(parents=True, exist_ok=True)

patterns = [
    "/dashboard",
    "dashboard",
    "unified_dashboard",
    "chat-product",
    "chat_v2",
    "chat v2",
    "v2",
    "R10.5",
    "Chat Excellence",
    "proposals",
    "pending",
]

results = []

for base in [
    root / "tmp_agent" / "brain_v9",
    root / "tmp_agent",
    root / "00_identity",
]:
    if not base.exists():
        continue
    for path in base.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix.lower() not in [".py", ".html", ".js", ".json", ".md", ".txt"]:
            continue
        try:
            if path.stat().st_size > 5_000_000:
                continue
            txt = path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue

        hits = []
        low = txt.lower()
        for p in patterns:
            if p.lower() in low:
                hits.append(p)

        if hits:
            lines = []
            for i, line in enumerate(txt.splitlines(), start=1):
                l = line.lower()
                if any(p.lower() in l for p in patterns):
                    lines.append({"line": i, "text": line[:500]})
                    if len(lines) >= 30:
                        break
            results.append({
                "path": str(path),
                "size": path.stat().st_size,
                "hits": sorted(set(hits)),
                "sample_lines": lines,
            })

(out_dir / "dashboard_file_inventory.json").write_text(
    json.dumps(results, indent=2, ensure_ascii=False),
    encoding="utf-8",
)

print(json.dumps({"files_with_hits": len(results), "output": str(out_dir / "dashboard_file_inventory.json")}, indent=2))
