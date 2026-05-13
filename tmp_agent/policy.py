import os
import json
from typing import Any, Dict, List

VAULT_ROOT = r"C:\AI_VAULT"
STATE_ROOT = os.path.join(VAULT_ROOT, "state")

DEFAULT_POLICY = {
    "allowed_read_roots": [
        r"C:\AI_VAULT\workspace\brainlab",
        r"C:\AI_VAULT\state",
        r"C:\AI_VAULT\logs"
    ],
    "allowed_write_roots": [
        r"C:\AI_VAULT\workspace\brainlab"
    ],
    "deny_contains": [
        r"\secrets\\",
        "api_key",
        ".key",
        ".pem",
        ".pfx"
    ],
    "max_write_bytes_per_call": 200000
}

def _policy_path(room_id: str) -> str:
    return os.path.join(STATE_ROOT, room_id, "policy.json")

def load_policy(room_id: str) -> Dict[str, Any]:
    p = _policy_path(room_id)
    if not os.path.exists(p):
        return DEFAULT_POLICY.copy()
    try:
        with open(p, "r", encoding="utf-8") as f:
            obj = json.load(f)
        # merge defaults
        merged = DEFAULT_POLICY.copy()
        merged.update(obj if isinstance(obj, dict) else {})
        return merged
    except Exception:
        return DEFAULT_POLICY.copy()

def save_policy(room_id: str, policy: Dict[str, Any]) -> None:
    os.makedirs(os.path.join(STATE_ROOT, room_id), exist_ok=True)
    p = _policy_path(room_id)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(policy, f, ensure_ascii=False, indent=2)

def _norm(p: str) -> str:
    return os.path.normpath(p)

def _starts_with_any(path: str, roots: List[str]) -> bool:
    path_n = _norm(path)
    for r in roots:
        r_n = _norm(r)
        try:
            cp = os.path.commonpath([r_n, path_n])
        except Exception:
            continue
        if cp == r_n:
            return True
    return False

def _deny_hit(path: str, deny_contains: List[str]) -> bool:
    p = path.lower()
    for token in deny_contains:
        if token.lower() in p:
            return True
    return False

def enforce_policy(room_id: str, tool: str, args: Dict[str, Any]) -> None:
    """
    Levanta ValueError si viola policy.
    """
    policy = load_policy(room_id)
    tool = (tool or "").strip()

    # path puede venir como path o file_path
    path = None
    if isinstance(args, dict):
        path = args.get("path") or args.get("file_path")

    # tools sin path explícito: list_dir puede caer en SAFE_ROOT por default,
    # pero aquí exigimos path explícito para gobernanza estricta.
    if tool in ("list_dir", "read_file", "write_file", "append_file"):
        if not path:
            raise ValueError("POLICY: falta args.path")
        if _deny_hit(path, policy.get("deny_contains", [])):
            raise ValueError(f"POLICY: ruta denegada por patrón: {path}")

    if tool in ("list_dir", "read_file"):
        if not _starts_with_any(path, policy.get("allowed_read_roots", [])):
            raise ValueError(f"POLICY: lectura fuera de roots permitidos: {path}")

    if tool in ("write_file", "append_file"):
        if not _starts_with_any(path, policy.get("allowed_write_roots", [])):
            raise ValueError(f"POLICY: escritura fuera de roots permitidos: {path}")
        content = args.get("content", "") if isinstance(args, dict) else ""
        maxb = int(policy.get("max_write_bytes_per_call", 200000))
        if isinstance(content, str) and len(content.encode("utf-8")) > maxb:
            raise ValueError(f"POLICY: write demasiado grande ({len(content.encode('utf-8'))} bytes > {maxb})")
