import re
from pathlib import Path

SERVER = r"C:\AI_VAULT\00_identity\brain_server.py"
p = Path(SERVER)
txt = p.read_text(encoding="utf-8")

BEGIN = "# === EXECUTE_STEP PERSIST PLAN (FIX) BEGIN ==="
END   = "# === EXECUTE_STEP PERSIST PLAN (FIX) END ==="

i0 = txt.find(BEGIN)
i1 = txt.find(END)
if i0 < 0 or i1 < 0 or i1 < i0:
    raise SystemExit("No encuentro el bloque EXECUTE_STEP PERSIST PLAN (FIX).")

block = txt[i0:i1]

# 1) Quitar el def _extract_proposal_id completo (si existe)
block2 = re.sub(
    r"\n[ \t]*def _extract_proposal_id\(\)\s*->\s*str:\n(?:[ \t].*\n)+?[ \t]*return ''\n",
    "\n",
    block,
    count=1,
    flags=re.MULTILINE
)

# 2) Reemplazar la línea pid = _extract_proposal_id() por extracción en mismo scope
#    (mismo indent que esa línea)
def repl_pid(m):
    indent = m.group(1)
    return (
        f"{indent}# extract proposal_id from execute_step result (scope-safe)\n"
        f"{indent}pid = ''\n"
        f"{indent}for _name in ('res','result','out','resp','response','payload','r'):\n"
        f"{indent}    try:\n"
        f"{indent}        _obj = locals().get(_name)\n"
        f"{indent}    except Exception:\n"
        f"{indent}        _obj = None\n"
        f"{indent}    # IMPORTANT: locals() here is agent_execute_step scope (we are not inside a nested func)\n"
        f"{indent}    if _obj is None:\n"
        f"{indent}        try:\n"
        f"{indent}            _obj = eval(_name)\n"
        f"{indent}        except Exception:\n"
        f"{indent}            _obj = None\n"
        f"{indent}    if isinstance(_obj, dict):\n"
        f"{indent}        _pid = _obj.get('proposal_id')\n"
        f"{indent}        if _pid:\n"
        f"{indent}            pid = str(_pid)\n"
        f"{indent}            break\n"
        f"{indent}        _inner = _obj.get('result')\n"
        f"{indent}        if isinstance(_inner, dict) and _inner.get('proposal_id'):\n"
        f"{indent}            pid = str(_inner.get('proposal_id'))\n"
        f"{indent}            break\n"
    )

block3, n = re.subn(
    r"\n([ \t]*)pid\s*=\s*_extract_proposal_id\(\)\n",
    lambda m: "\n" + repl_pid(m),
    block2,
    count=1,
    flags=re.MULTILINE
)

if n == 0:
    raise SystemExit("No encontré 'pid = _extract_proposal_id()' para reemplazar. El bloque no coincide con el esperado.")

txt2 = txt[:i0] + block3 + txt[i1:]
p.write_text(txt2, encoding="utf-8")
print("OK: fixed proposal_id extraction in EXECUTE_STEP persist block (scope-safe).")
