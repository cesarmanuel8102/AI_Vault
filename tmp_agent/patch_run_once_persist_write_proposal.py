import re
from pathlib import Path

SERVER = r"C:\AI_VAULT\00_identity\brain_server.py"
p = Path(SERVER)
txt = p.read_text(encoding="utf-8")

MARK_END = "# === RUN_ONCE MARK READ DONE (FIX) END ==="
if MARK_END not in txt:
    raise SystemExit("No encuentro el marker END del bloque READ DONE; abortando.")

MARK2 = "RUN_ONCE PERSIST WRITE PROPOSAL (FIX)"
if MARK2 in txt:
    print("SKIP: ya existe PERSIST WRITE PROPOSAL")
    raise SystemExit(0)

# Insert block immediately after READ DONE block end
lines = txt.splitlines(True)
out = []
inserted = False

for ln in lines:
    out.append(ln)
    if (not inserted) and (MARK_END in ln):
        # derive indent from this line
        indent = re.match(r"(\s*)", ln).group(1)

        block = []
        block.append(f"{indent}# === {MARK2} BEGIN ===\n")
        block.append(f"{indent}# Persist write-step proposal_id/required_approve into per-room plan.json so APPLY can match.\n")
        block.append(f"{indent}if _is_write_tool(tool_name):\n")
        block.append(f"{indent}    try:\n")
        block.append(f"{indent}        pid = None\n")
        block.append(f"{indent}        try:\n")
        block.append(f"{indent}            pid = (res.get('result') or {{}}).get('proposal_id')\n")
        block.append(f"{indent}        except Exception:\n")
        block.append(f"{indent}            pid = None\n")
        block.append(f"{indent}        if pid:\n")
        block.append(f"{indent}            plan_disk = _load_room_plan(room_id) or {{}}\n")
        block.append(f"{indent}            steps_disk = plan_disk.get('steps', []) or []\n")
        block.append(f"{indent}            for _s in steps_disk:\n")
        block.append(f"{indent}                if isinstance(_s, dict) and str(_s.get('id')) == str(step_id):\n")
        block.append(f"{indent}                    _s['status'] = 'proposed'\n")
        block.append(f"{indent}                    _s['proposal_id'] = str(pid)\n")
        block.append(f"{indent}                    _s['required_approve'] = 'APPLY_' + str(pid)\n")
        block.append(f"{indent}                    break\n")
        block.append(f"{indent}            plan_disk['steps'] = steps_disk\n")
        block.append(f"{indent}            try:\n")
        block.append(f"{indent}                from datetime import datetime, timezone\n")
        block.append(f"{indent}                plan_disk['updated_at'] = datetime.now(timezone.utc).isoformat()\n")
        block.append(f"{indent}            except Exception:\n")
        block.append(f"{indent}                pass\n")
        block.append(f"{indent}            plan_disk.setdefault('room_id', room_id)\n")
        block.append(f"{indent}            _room_state_dir(room_id)\n")
        block.append(f"{indent}            _paths = _room_paths(room_id) or {{}}\n")
        block.append(f"{indent}            import json\n")
        block.append(f"{indent}            from pathlib import Path\n")
        block.append(f"{indent}            pp = _paths.get('plan')\n")
        block.append(f"{indent}            if pp:\n")
        block.append(f"{indent}                Path(pp).write_text(json.dumps(plan_disk, ensure_ascii=False, indent=2), encoding='utf-8')\n")
        block.append(f"{indent}            plan = plan_disk\n")
        block.append(f"{indent}            steps = plan.get('steps', []) or []\n")
        block.append(f"{indent}    except Exception:\n")
        block.append(f"{indent}        pass\n")
        block.append(f"{indent}# === {MARK2} END ===\n")

        out.extend(block)
        inserted = True

Path(SERVER).write_text("".join(out), encoding="utf-8")
print("OK: inserted write-proposal persistence block after READ DONE block")
