import re
from pathlib import Path

SERVER = r"C:\AI_VAULT\00_identity\brain_server.py"
p = Path(SERVER)
txt = p.read_text(encoding="utf-8")

BEGIN = "    # === REAL_GUARDRAIL_AGENT_RUNS_ROOT_V1 BEGIN ==="
END   = "    # === REAL_GUARDRAIL_AGENT_RUNS_ROOT_V1 END ==="

i0 = txt.find(BEGIN)
i1 = txt.find(END)
if i0 < 0 or i1 < 0 or i1 <= i0:
    raise SystemExit("No encuentro bloque REAL_GUARDRAIL_AGENT_RUNS_ROOT_V1 (BEGIN/END).")

# Reescribe SOLO el bloque interno (manteniendo markers)
new_block = r'''
    # === REAL_GUARDRAIL_AGENT_RUNS_ROOT_V1 BEGIN ===
    # Confine write operations to repo-safe subtree:
    #   C:\AI_VAULT\workspace\brainlab\_agent_runs\...
    # IMPORTANT:
    # - Use req.dest_dir (NOT local dest_dir var) because local dest_dir may be computed later.
    # - If tool_args.path is relative, req.dest_dir MUST be provided.
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
        # Prefer explicit req.dest_dir
        try:
            _dest = getattr(req, "dest_dir", None)
        except Exception:
            _dest = None

        # Read tool_args.path
        try:
            _p = tool_args.get("path") or tool_args.get("p")
        except Exception:
            _p = None

        # If dest_dir missing:
        # - allow only if path is absolute and under safe root
        # - deny if path is relative (prevents resolving to CWD like C:\AI_VAULT\00_identity)
        if not _dest:
            if isinstance(_p, str) and _p:
                try:
                    _pp = Path(_p)
                    if _pp.is_absolute():
                        _dest_res = _pp.parent.resolve()
                        _dest_res.relative_to(_REAL_SAFE_ROOT)
                    else:
                        raise HTTPException(status_code=400, detail="REAL_GUARDRAIL_DENY: relative path requires dest_dir")
                except HTTPException:
                    raise
                except Exception:
                    raise HTTPException(status_code=400, detail=f"REAL_GUARDRAIL_DENY: dest_dir missing or outside safe root (path={_p})")
            else:
                raise HTTPException(status_code=400, detail="REAL_GUARDRAIL_DENY: missing dest_dir/path for write op")
        else:
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
'''.strip("\n")

txt2 = txt[:i0] + new_block + "\n" + txt[i1+len(END):]
p.write_text(txt2, encoding="utf-8")
print("OK: guardrail fixed -> uses req.dest_dir, blocks relative path without dest_dir.")
