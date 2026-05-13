import inspect
import brain_server

app = getattr(brain_server, "app", None)
if app is None:
    raise SystemExit("ERROR: brain_server.app no existe")

hits = []
for r in getattr(app, "routes", []):
    path = getattr(r, "path", None)
    methods = getattr(r, "methods", None)
    if path == "/v1/agent/mission":
        endpoint = getattr(r, "endpoint", None)
        src = None
        try:
            src = inspect.getsourcefile(endpoint) if endpoint else None
        except Exception:
            src = None
        name = getattr(endpoint, "__name__", None)
        hits.append((path, sorted(list(methods)) if methods else methods, name, src))

print("ROUTES for /v1/agent/mission:")
for h in hits:
    print(" -", h)

# También lista cualquier ruta que contenga "agent/mission" por si hay variantes
print("\nROUTES containing 'agent/mission':")
for r in getattr(app, "routes", []):
    path = getattr(r, "path", "") or ""
    if "agent/mission" in path:
        endpoint = getattr(r, "endpoint", None)
        src = None
        try:
            src = inspect.getsourcefile(endpoint) if endpoint else None
        except Exception:
            src = None
        methods = getattr(r, "methods", None)
        name = getattr(endpoint, "__name__", None)
        print(" -", path, sorted(list(methods)) if methods else methods, name, src)
