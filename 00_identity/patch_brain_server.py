# patch_brain_server.py
# Parche robusto: crea /v1/agent/step si no existe, sin depender de bloques exactos.

import io
import os
import re
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
TARGET = os.path.join(ROOT, "brain_server.py")


ENDPOINT_BLOCK = r'''
# ===================== AGENT ENDPOINTS (Planner/Executor/Evaluator) =====================
# NOTE: Safe minimal endpoint to execute 1 step through internal tools/router.
#       You can extend this later with mission/plan persistence.

from fastapi import Request
from fastapi.responses import JSONResponse

@app.post("/v1/agent/step")
async def agent_step(request: Request):
    """
    Execute one agent step.
    Expected JSON body (example):
      {
        "room_id": "646350",
        "goal": "Do X",
        "step": {"id":"s1","action":"list_dir","args":{"path":"C:\\AI_VAULT"}},
        "meta": {"dry_run": false}
      }

    Response:
      {
        "ok": true,
        "room_id": "...",
        "step_id": "...",
        "result": {...},
        "ts": 1234567890
      }
    """
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"ok": False, "error": "Invalid JSON body"}, status_code=400)

    room_id = str(body.get("room_id") or body.get("room") or "default")
    step = body.get("step") or {}
    step_id = str(step.get("id") or body.get("step_id") or "step_1")

    # This is intentionally minimal; integrate your real planner/executor later.
    # If you already have a tool runner/router function, call it here.
    # Example (adapt to your code):
    # result = await run_tool(step.get("action"), step.get("args", {}), room_id=room_id)

    action = (step.get("action") or "").strip()
    args = step.get("args") or {}

    # Minimal no-op behavior if no tool runner exists:
    result = {
        "action": action,
        "args": args,
        "note": "Endpoint installed. Wire this to your Executor/Tools next."
    }

    return {"ok": True, "room_id": room_id, "step_id": step_id, "result": result, "ts": int(time.time())}
# =================== END AGENT ENDPOINTS ===================
'''.lstrip("\n")


def read_text(path: str) -> str:
    with io.open(path, "r", encoding="utf-8") as f:
        return f.read()


def write_text(path: str, text: str) -> None:
    with io.open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def ensure_imports(src: str) -> str:
    """
    Ensure we have base imports: FastAPI, time. We avoid duplicating imports.
    We only add what is missing, in a conservative way.
    """
    # Ensure 'import time'
    if not re.search(r'^\s*import\s+time\s*$', src, flags=re.M):
        # put after other imports if possible
        m = re.search(r'(^\s*(from\s+\S+\s+import\s+.+|import\s+.+)\s*$)+', src, flags=re.M)
        if m:
            insert_at = m.end()
            src = src[:insert_at] + "\nimport time\n" + src[insert_at:]
        else:
            src = "import time\n" + src

    # Ensure FastAPI import exists
    if not re.search(r'from\s+fastapi\s+import\s+.*\bFastAPI\b', src):
        # If there's already "from fastapi import ..." append FastAPI; else add a new line.
        m = re.search(r'^from\s+fastapi\s+import\s+(.+)$', src, flags=re.M)
        if m:
            line = m.group(0)
            items = [x.strip() for x in m.group(1).split(",")]
            if "FastAPI" not in items:
                items.append("FastAPI")
                new_line = "from fastapi import " + ", ".join(sorted(set(items), key=lambda x: items.index(x) if x in items else 999))
                src = src.replace(line, new_line, 1)
        else:
            # insert near top with other imports
            m2 = re.search(r'(^\s*(from\s+\S+\s+import\s+.+|import\s+.+)\s*$)+', src, flags=re.M)
            if m2:
                insert_at = m2.end()
                src = src[:insert_at] + "\nfrom fastapi import FastAPI\n" + src[insert_at:]
            else:
                src = "from fastapi import FastAPI\n" + src

    return src


def endpoint_exists(src: str) -> bool:
    return bool(re.search(r'@app\.post\(\s*["\']\/v1\/agent\/step["\']\s*\)', src))


def find_insert_position(src: str) -> int:
    """
    Prefer insert right after 'app = FastAPI(...)' if exists.
    Otherwise insert near end.
    """
    m = re.search(r'^\s*app\s*=\s*FastAPI\s*\(.*?\)\s*$', src, flags=re.M)
    if m:
        # insert after that line
        line_end = src.find("\n", m.end())
        if line_end == -1:
            return len(src)
        return line_end + 1
    return len(src)


def patch():
    if not os.path.exists(TARGET):
        print(f"ERROR: No existe {TARGET}")
        sys.exit(1)

    src = read_text(TARGET)

    # quick normalize line endings for reliable regex
    src = src.replace("\r\n", "\n").replace("\r", "\n")

    if endpoint_exists(src):
        print("OK: /v1/agent/step ya existe. No se aplicó parche.")
        return

    src = ensure_imports(src)

    insert_at = find_insert_position(src)
    if insert_at < len(src) and not src.endswith("\n"):
        src += "\n"

    # Ensure there is a blank line before insertion when inserting in middle.
    prefix = src[:insert_at]
    suffix = src[insert_at:]
    if prefix and not prefix.endswith("\n\n"):
        prefix = prefix.rstrip("\n") + "\n\n"

    new_src = prefix + ENDPOINT_BLOCK + "\n" + suffix.lstrip("\n")

    write_text(TARGET, new_src)
    print("OK: Endpoint /v1/agent/step INSERTADO en brain_server.py")


if __name__ == "__main__":
    patch()