from pathlib import Path
import json, subprocess

out_dir = Path("C:/AI_VAULT/tmp_agent/dashboard_v2_r105_audit_evidence")
out_dir.mkdir(parents=True, exist_ok=True)

def probe(url, timeout):
    try:
        p = subprocess.run(
            ["curl", f"--max-time={timeout}", "-s", url],
            capture_output=True, text=False, timeout=timeout+5,
        )
        raw = p.stdout or b""
        return {"url": url, "rc": p.returncode, "raw_preview": raw.decode("utf-8", errors="replace")[:2000]}
    except Exception as e:
        return {"url": url, "error": f"{type(e).__name__}: {e}"}

# Try openapi directly to a file so we don't truncate
openapi_path = out_dir / "openapi_raw.json"
try:
    p = subprocess.run(
        ["curl", "--max-time=25", "-s", "http://127.0.0.1:8090/openapi.json"],
        capture_output=True, text=False, timeout=30,
    )
    open_raw = p.stdout or b""
    openapi_path.write_bytes(open_raw)
    openapi_text = open_raw.decode("utf-8", errors="replace")
    openapi_json = json.loads(openapi_text) if open_raw else None
except Exception as e:
    openapi_json = None
    openapi_text = f"ERROR: {e}"

h = probe("http://127.0.0.1:8090/health", 10)

routes = []
if openapi_json and isinstance(openapi_json, dict):
    paths = openapi_json.get("paths", {})
    for path, methods in sorted(paths.items()):
        routes.append({
            "path": path,
            "methods": sorted(methods.keys()),
            "dashboard_related": any(x in path.lower() for x in ["dashboard","chat","proposal","v2","r10"]),
        })

out = {
    "health": h,
    "openapi_size_bytes": len(open_raw) if openapi_json else 0,
    "openapi_available": openapi_json is not None,
    "route_count": len(routes),
    "routes": routes,
}

(out_dir / "dashboard_route_inventory.json").write_text(
    json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8"
)

print(json.dumps(out, indent=2, ensure_ascii=False)[:6000])
