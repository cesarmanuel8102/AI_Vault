import os
from typing import Any, Dict, List

SAFE_ROOT = r"C:\AI_VAULT"

def _safe_path(p: str) -> str:
    p = (p or "").strip()
    if not p:
        raise ValueError("path vacío")
    p_norm = os.path.normpath(p)
    safe_norm = os.path.normpath(SAFE_ROOT)

    # Asegurar que p_norm cae bajo SAFE_ROOT
    # commonpath lanza si las rutas están en drives distintos
    try:
        cp = os.path.commonpath([safe_norm, p_norm])
    except Exception:
        raise ValueError(f"Ruta fuera de SAFE_ROOT: {p_norm}")

    if cp != safe_norm:
        raise ValueError(f"Ruta fuera de SAFE_ROOT: {p_norm}")
    return p_norm

def _get_path_arg(args: Dict[str, Any]) -> str:
    """
    Acepta variantes comunes: path, file_path.
    """
    if not isinstance(args, dict):
        raise ValueError("args debe ser dict")
    p = args.get("path")
    if not p:
        p = args.get("file_path")
    return p

def tool_list_dir(args: Dict[str, Any]) -> Dict[str, Any]:
    path = _safe_path(_get_path_arg(args) or SAFE_ROOT)
    if not os.path.isdir(path):
        raise ValueError("No es directorio")
    items: List[Dict[str, Any]] = []
    for name in os.listdir(path):
        full = os.path.join(path, name)
        items.append({
            "name": name,
            "is_dir": os.path.isdir(full),
            "size": os.path.getsize(full) if os.path.isfile(full) else None,
        })
    return {"path": path, "items": items}

def tool_read_file(args: Dict[str, Any]) -> Dict[str, Any]:
    p = _get_path_arg(args)
    path = _safe_path(p)
    max_bytes = int(args.get("max_bytes", 200000))
    if not os.path.isfile(path):
        raise ValueError("No es archivo")
    with open(path, "rb") as f:
        b = f.read(max_bytes)
    text = b.decode("utf-8", errors="replace")
    return {"path": path, "content": text, "truncated": os.path.getsize(path) > max_bytes}

def tool_write_file(args):
    # P2_1_LF_ONLY_TOOLS_FS_V1
    from pathlib import Path

    path = args.get("path") or args.get("p") or args.get("file_path")
    if not path:
        return {"ok": False, "error": "MISSING_PATH"}

    text = args.get("content")
    if text is None:
        text = args.get("text")
    if text is None:
        text = ""
    if not isinstance(text, str):
        text = str(text)

    # Force LF-only everywhere
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    return {"ok": True, "path": str(p), "bytes": len(text.encode("utf-8"))}

def tool_append_file(args):
    # P2_1_LF_ONLY_TOOLS_FS_V1
    from pathlib import Path

    path = args.get("path") or args.get("p") or args.get("file_path")
    if not path:
        return {"ok": False, "error": "MISSING_PATH"}

    text = args.get("content")
    if text is None:
        text = args.get("text")
    if text is None:
        text = ""
    if not isinstance(text, str):
        text = str(text)

    # Force LF-only everywhere
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8", newline="\n") as f:
        f.write(text)
    return {"ok": True, "path": str(p), "bytes": len(text.encode("utf-8"))}

