from __future__ import annotations

import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

CANONICAL_FILES = (
    Path("memory/semantic/semantic_memory.jsonl"),
    Path("memory/semantic/semantic_memory_faiss.index"),
    Path("memory/semantic/semantic_memory_faiss_ids.json"),
)
SNAPSHOT_ROOT = Path("memory/rollback_snapshots")


def create_memory_snapshot(
    reason: str,
    snapshot_root: Path = SNAPSHOT_ROOT,
    canonical_root: Path = Path("."),
) -> Path:
    """Copy canonical memory artifacts with a verifiable, relative-path manifest."""
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    target = snapshot_root / stamp
    target.mkdir(parents=True, exist_ok=False)
    files = {}
    for relative_path in CANONICAL_FILES:
        src = Path(canonical_root) / relative_path
        if src.exists():
            copied = target / src.name
            shutil.copy2(src, copied)
            files[relative_path.as_posix()] = {
                "sha256": hashlib.sha256(src.read_bytes()).hexdigest(),
                "size_bytes": src.stat().st_size,
            }
    (target / "SNAPSHOT_REASON.txt").write_text(reason + "\n", encoding="utf-8")
    (target / "memory_snapshot_manifest.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "created_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                "reason": reason,
                "files": files,
            },
            sort_keys=True,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return target


def latest_snapshot(snapshot_root: Path = SNAPSHOT_ROOT) -> Path | None:
    if not snapshot_root.exists():
        return None
    candidates = sorted([p for p in snapshot_root.iterdir() if p.is_dir()])
    return candidates[-1] if candidates else None
