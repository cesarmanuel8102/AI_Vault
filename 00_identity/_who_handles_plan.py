import inspect
import re
import sys

import brain_server

app = getattr(brain_server, "app", None)
if app is None:
    raise SystemExit("ERROR: brain_server.app no existe")

hits = []
for r in getattr(app, "routes", []):
    path = getattr(r, "path", None)
    methods = getattr(r, "methods", None)
    if path == "/v1/agent/plan":
        endpoint = getattr(r, "endpoint", None)
        src = None
        try:
            src = inspect.getsourcefile(endpoint) if endpoint else None
        except Exception:
            src = None
        name = getattr(endpoint, "__name__", None)
        hits.append((path, sorted(list(methods)) if methods else methods, name, src))

print("ROUTES for /v1/agent/plan:")
for h in hits:
    print(" -", h)

# Mostrar snippet del source real del endpoint
print("\nENDPOINT SOURCE CHECK:")
for (path, methods, name, src) in hits:
    try:
        ep = None
        for r in getattr(app, "routes", []):
            if getattr(r, "path", None) == path and getattr(r, "endpoint", None) and getattr(r.endpoint, "__name__", None) == name:
                ep = r.endpoint
                break
        if ep is None:
            continue
        code = inspect.getsource(ep)
        has_v3 = "PLAN_RESET_HARD_V3" in code
        has_meta = "_meta" in code
        print(f" - {path} {methods} {name} file={src}")
        print(f"   contains PLAN_RESET_HARD_V3={has_v3}, contains _meta={has_meta}")
        # imprime 80 líneas alrededor del marcador si existe, si no, las primeras 60
        lines = code.splitlines()
        idx = None
        for i, ln in enumerate(lines):
            if "PLAN_RESET_HARD_V3" in ln:
                idx = i
                break
        if idx is None:
            print("   --- first 60 lines ---")
            for ln in lines[:60]:
                print("   " + ln)
        else:
            lo = max(0, idx - 20)
            hi = min(len(lines), idx + 60)
            print(f"   --- context lines {lo+1}-{hi} (around PLAN_RESET_HARD_V3) ---")
            for ln in lines[lo:hi]:
                print("   " + ln)
    except Exception as e:
        print(" - ERROR inspecting endpoint:", repr(e))

# También listar rutas relacionadas, por si hay duplicado / override
print("\nROUTES containing 'agent/plan':")
for r in getattr(app, "routes", []):
    path = getattr(r, "path", "") or ""
    if "agent/plan" in path:
        endpoint = getattr(r, "endpoint", None)
        src = None
        try:
            src = inspect.getsourcefile(endpoint) if endpoint else None
        except Exception:
            src = None
        methods = getattr(r, "methods", None)
        name = getattr(endpoint, "__name__", None)
        print(" -", path, sorted(list(methods)) if methods else methods, name, src)
