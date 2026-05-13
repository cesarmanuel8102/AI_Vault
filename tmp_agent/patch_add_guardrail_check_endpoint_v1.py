from pathlib import Path
import re

SERVER = r"C:\AI_VAULT\00_identity\brain_server.py"
p = Path(SERVER)
txt = p.read_text(encoding="utf-8")

MARK = "GUARDRAIL_CHECK_ENDPOINT_V1"
if MARK in txt:
    print("SKIP: guardrail_check endpoint already present")
    raise SystemExit(0)

# Anchor after plan_refresh (stable area) or after /healthz
anchor = None
m = re.search(r'@app\.post\("/v1/agent/plan_refresh"[^\n]*\)\s*\ndef\s+agent_plan_refresh\s*\(.*?\):\n', txt, flags=re.DOTALL)
if m:
    # insert after end of function
    start = m.end()
    tail = txt[start:]
    m2 = re.search(r"\n@app\.", tail)
    end = (start + m2.start()) if m2 else len(txt)
    anchor = end
else:
    m = re.search(r'@app\.get\("/healthz"[^\n]*\)\s*\ndef\s+healthz\s*\(.*?\):\n', txt, flags=re.DOTALL)
    if not m:
        raise SystemExit("No encuentro ancla (plan_refresh o healthz).")
    start = m.end()
    tail = txt[start:]
    m2 = re.search(r"\n@app\.", tail)
    end = (start + m2.start()) if m2 else len(txt)
    anchor = end

endpoint = r'''
# === GUARDRAIL_CHECK_ENDPOINT_V1 BEGIN ===
class GuardrailCheckRequest(BaseModel):
    # simulate a write intent
    mode: str = "propose"         # propose|apply
    tool_name: str = "append_file" # write_file|append_file
    kind: str = "new_file"        # new_file|modify
    dest_dir: Optional[str] = None
    repo_path: Optional[str] = None
    path: str = ""                # tool_args.path
    room_id: Optional[str] = None

class GuardrailCheckResponse(BaseModel):
    ok: bool = True
    allowed: bool = True
    detail: str = ""
    room_id: str = ""

@app.post("/v1/agent/guardrail_check", response_model=GuardrailCheckResponse)
def guardrail_check(req: GuardrailCheckRequest, request: Request):
    """
    Deterministic guardrail evaluation without mutating plan state.
    Returns allowed=True if the REAL guardrail would allow the write.
    """
    try:
        hdr_room = request.headers.get("x-room-id") or request.headers.get("X-Room-Id") or None
    except Exception:
        hdr_room = None

    room_id = (req.room_id or hdr_room or "default")

    # We reuse the same checks as REAL guardrail, but in a pure function style:
    from pathlib import Path
    safe_root = Path(r"C:\AI_VAULT\workspace\brainlab\_agent_runs").resolve()

    tool = (req.tool_name or "").strip()
    mode = (req.mode or "").strip().lower()
    kind = (req.kind or "").strip()

    if tool not in ("write_file","append_file") or mode not in ("propose","apply"):
        return {"ok": True, "allowed": True, "detail": "not-a-write-op", "room_id": room_id}

    dest = req.dest_dir
    pth = req.path

    # If no dest_dir, allow only absolute path whose parent is under safe root
    if not dest:
        if not isinstance(pth, str) or not pth:
            raise HTTPException(status_code=400, detail="REAL_GUARDRAIL_DENY: missing dest_dir/path for write op")
        pp = Path(pth)
        if not pp.is_absolute():
            raise HTTPException(status_code=400, detail="REAL_GUARDRAIL_DENY: relative path requires dest_dir")
        try:
            pp.parent.resolve().relative_to(safe_root)
        except Exception:
            raise HTTPException(status_code=400, detail=f"REAL_GUARDRAIL_DENY: dest_dir missing or outside safe root (path={pth})")
    else:
        try:
            Path(dest).resolve().relative_to(safe_root)
        except Exception:
            raise HTTPException(status_code=400, detail=f"REAL_GUARDRAIL_DENY: dest_dir outside safe root: {dest}")

    if kind == "modify":
        if not req.repo_path:
            raise HTTPException(status_code=400, detail="REAL_GUARDRAIL_DENY: modify requires repo_path")
        try:
            Path(req.repo_path).resolve().relative_to(safe_root)
        except Exception:
            raise HTTPException(status_code=400, detail=f"REAL_GUARDRAIL_DENY: repo_path outside safe root: {req.repo_path}")

    return {"ok": True, "allowed": True, "detail": "allowed", "room_id": room_id}
# === GUARDRAIL_CHECK_ENDPOINT_V1 END ===

'''

txt2 = txt[:anchor] + endpoint + txt[anchor:]
p.write_text(txt2, encoding="utf-8")
print("OK: added /v1/agent/guardrail_check (pure guardrail test endpoint)")
