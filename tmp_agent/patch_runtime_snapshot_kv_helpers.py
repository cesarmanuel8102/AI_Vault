import re
from pathlib import Path

SERVER = r"C:\AI_VAULT\00_identity\brain_server.py"
p = Path(SERVER)
txt = p.read_text(encoding="utf-8")

# Skip if already present
if "RUNTIME_SNAPSHOT_KV_HELPERS_V1" in txt:
    print("SKIP: helpers KV ya existen")
    raise SystemExit(0)

# Insert right after def _room_paths(...) block (before next top-level def)
m = re.search(r"^def\s+_room_paths\s*\(.*?\):", txt, flags=re.MULTILINE)
if not m:
    raise SystemExit("No encuentro def _room_paths(...)")

# find end of _room_paths function by next '^def ' at col 0 after it
tail = txt[m.end():]
m2 = re.search(r"^\ndef\s+", tail, flags=re.MULTILINE)
insert_at = (m.end() + m2.start()) if m2 else len(txt)

block = r'''

# === RUNTIME_SNAPSHOT_KV_HELPERS_V1 BEGIN ===
def _runtime_snapshot_file(room_id: str) -> str:
    """rooms/<rid>/runtime_snapshot.json"""
    from pathlib import Path
    _room_state_dir(room_id)
    paths = _room_paths(room_id) or {}
    fp = paths.get("runtime_snapshot")
    if fp:
        return str(fp)
    # fallback
    return str(Path(_room_state_dir(room_id)) / "runtime_snapshot.json")


def _runtime_snapshot_kv_load(room_id: str) -> dict:
    import json
    from pathlib import Path
    fp = _runtime_snapshot_file(room_id)
    f = Path(fp)
    if not f.exists():
        return {"kv": {}, "updated_at": None, "room_id": room_id}
    try:
        obj = json.loads(f.read_text(encoding="utf-8")) or {}
    except Exception:
        obj = {}
    kv = obj.get("kv")
    if not isinstance(kv, dict):
        kv = {}
    return {"kv": kv, "updated_at": obj.get("updated_at"), "room_id": room_id}


def _runtime_snapshot_kv_save(room_id: str, kv: dict) -> dict:
    import json
    from pathlib import Path
    from datetime import datetime, timezone
    fp = _runtime_snapshot_file(room_id)
    payload = {
        "kv": kv if isinstance(kv, dict) else {},
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "room_id": room_id,
    }
    Path(fp).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"ok": True, "file": fp}


def _runtime_snapshot_set_kv(room_id: str, path: str, value):
    obj = _runtime_snapshot_kv_load(room_id)
    kv = obj.get("kv") or {}
    kv[str(path or "")] = value
    res = _runtime_snapshot_kv_save(room_id, kv)
    return {"ok": True, "path": str(path or ""), "value": value, "file": res.get("file")}


def _runtime_snapshot_get_kv(room_id: str, path: str):
    obj = _runtime_snapshot_kv_load(room_id)
    kv = obj.get("kv") or {}
    key = str(path or "")
    if key not in kv:
        return {"ok": False, "error": "SNAPSHOT_KEY_MISSING", "path": key, "file": _runtime_snapshot_file(room_id), "kv_keys": list(kv.keys())[:50]}
    return {"ok": True, "path": key, "value": kv.get(key), "file": _runtime_snapshot_file(room_id)}
# === RUNTIME_SNAPSHOT_KV_HELPERS_V1 END ===

'''

txt2 = txt[:insert_at] + block + txt[insert_at:]
p.write_text(txt2, encoding="utf-8")
print("OK: inserted RUNTIME_SNAPSHOT_KV_HELPERS_V1")
