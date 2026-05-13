import re
from pathlib import Path

SERVER = r"C:\AI_VAULT\00_identity\brain_server.py"
p = Path(SERVER)
txt = p.read_text(encoding="utf-8")

MARK = "REAL_GUARDRAIL_AGENT_RUNS_ROOT_V1"
if MARK in txt:
    print("SKIP: guardrail already present")
    raise SystemExit(0)

# Anchor inside agent_execute(req: AgentExecuteRequest)
m = re.search(r"^def\s+agent_execute\s*\(\s*req\s*:\s*AgentExecuteRequest\s*\)\s*:", txt, flags=re.MULTILINE)
if not m:
    raise SystemExit("No encuentro def agent_execute(req: AgentExecuteRequest):")

# Find a safe insertion point AFTER tool_name/tool_args/allowed gate, BEFORE write gating checks.
# We'll insert right after imports of tools_fs (stable line):
anchor = re.search(r"^\s*from\s+tools_fs\s+import\s+tool_list_dir,\s*tool_read_file,\s*tool_write_file,\s*tool_append_file\s*$",
                   txt, flags=re.MULTILINE)
if not anchor:
    raise SystemExit("No encuentro import de tools_fs dentro de agent_execute para anclar guardrail.")

insert_at = anchor.end()

block = r'''

    # === REAL_GUARDRAIL_AGENT_RUNS_ROOT_V1 BEGIN ===
    # Confine REAL write operations to repo-safe subtree:
    #   C:\AI_VAULT\workspace\brainlab\_agent_runs\...
    # This prevents accidental writes outside the safe perimeter.
    try:
        _REAL_SAFE_ROOT = Path(r"C:\AI_VAULT\workspace\brainlab\_agent_runs").resolve()
    except Exception:
        _REAL_SAFE_ROOT = None

    try:
        _mode_local = (req.mode or "").strip().lower()
    except Exception:
        _mode_local = ""

    try:
        _tool_local = (tool_name or "").strip()
    except Exception:
        _tool_local = ""

    if _REAL_SAFE_ROOT and _tool_local in ("write_file","append_file") and _mode_local in ("propose","apply"):
        # dest_dir is used by apply_gate; if absent, infer from tool_args.path (directory)
        _dest = None
        try:
            _dest = dest_dir
        except Exception:
            _dest = None

        if not _dest:
            try:
                _p = tool_args.get("path") or tool_args.get("p")
            except Exception:
                _p = None
            if isinstance(_p, str) and _p:
                try:
                    # If it's a file, take parent; if it's a dir, keep it
                    _pp = Path(_p)
                    _dest = str(_pp.parent if _pp.suffix else _pp)
                except Exception:
                    _dest = None

        if not _dest:
            raise HTTPException(status_code=400, detail="REAL_GUARDRAIL_DENY: missing dest_dir/path for write op")

        try:
            _dest_res = Path(_dest).resolve()
        except Exception:
            raise HTTPException(status_code=400, detail=f"REAL_GUARDRAIL_DENY: bad dest_dir={_dest}")

        try:
            _dest_res.relative_to(_REAL_SAFE_ROOT)
        except Exception:
            raise HTTPException(status_code=400, detail=f"REAL_GUARDRAIL_DENY: dest_dir outside safe root: {_dest_res}")

        # For modify, also enforce repo_path under safe root
        try:
            _kind_local = (req.kind or "").strip()
        except Exception:
            _kind_local = ""

        if _kind_local == "modify":
            try:
                _rp = req.repo_path
            except Exception:
                _rp = None
            if not isinstance(_rp, str) or not _rp:
                raise HTTPException(status_code=400, detail="REAL_GUARDRAIL_DENY: modify requires repo_path")
            try:
                _rp_res = Path(_rp).resolve()
                _rp_res.relative_to(_REAL_SAFE_ROOT)
            except Exception:
                raise HTTPException(status_code=400, detail=f"REAL_GUARDRAIL_DENY: repo_path outside safe root: {_rp}")
    # === REAL_GUARDRAIL_AGENT_RUNS_ROOT_V1 END ===
'''

txt2 = txt[:insert_at] + block + txt[insert_at:]
p.write_text(txt2, encoding="utf-8")
print("OK: inserted REAL guardrail (agent_execute) to confine writes under _agent_runs safe root.")
