# diff_engine.py
from __future__ import annotations

import hashlib
import difflib
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Any, Optional


@dataclass
class DiffArtifact:
    ok: bool
    detail: str
    data: Dict[str, Any]


def sha256_bytes(b: bytes) -> str:
    h = hashlib.sha256()
    h.update(b)
    return h.hexdigest()


def read_bytes_safe(p: Path, max_bytes: int = 5_000_000) -> bytes:
    data = p.read_bytes()
    if len(data) > max_bytes:
        raise ValueError(f"FILE_TOO_LARGE: {p} size={len(data)}")
    return data


def unified_diff_text(
    old_text: str,
    new_text: str,
    fromfile: str,
    tofile: str,
    n: int = 3
) -> str:
    old_lines = old_text.splitlines(keepends=True)
    new_lines = new_text.splitlines(keepends=True)
    diff = difflib.unified_diff(old_lines, new_lines, fromfile=fromfile, tofile=tofile, n=n)
    return "".join(diff)


def diff_files(old_path: Path, new_path: Path) -> DiffArtifact:
    """
    Devuelve unified diff entre old_path y new_path.
    Si old_path no existe => diff tipo "new file" (old vacío).
    """
    try:
        old_exists = old_path.exists()
        new_exists = new_path.exists()
        if not new_exists:
            return DiffArtifact(False, "NEW_FILE_MISSING", {"new_path": str(new_path)})

        old_bytes = b"" if not old_exists else read_bytes_safe(old_path)
        new_bytes = read_bytes_safe(new_path)

        old_hash = sha256_bytes(old_bytes)
        new_hash = sha256_bytes(new_bytes)

        try:
            old_text = old_bytes.decode("utf-8")
        except Exception:
            old_text = old_bytes.decode("utf-8", errors="replace")

        try:
            new_text = new_bytes.decode("utf-8")
        except Exception:
            new_text = new_bytes.decode("utf-8", errors="replace")

        fromfile = str(old_path)
        tofile = str(new_path)

        diff_text = unified_diff_text(old_text, new_text, fromfile, tofile)

        # Si son iguales, diff será vacío
        changed = (old_hash != new_hash)

        return DiffArtifact(True, "OK", {
            "old_path": str(old_path),
            "new_path": str(new_path),
            "old_exists": old_exists,
            "old_sha256": old_hash,
            "new_sha256": new_hash,
            "changed": changed,
            "diff_text": diff_text
        })
    except Exception as e:
        return DiffArtifact(False, "ERROR", {"error": str(e), "old_path": str(old_path), "new_path": str(new_path)})
