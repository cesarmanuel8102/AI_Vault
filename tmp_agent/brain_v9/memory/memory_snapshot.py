from __future__ import annotations

import shutil
from datetime import datetime, timezone
from pathlib import Path

CANONICAL_FILES = (
    Path("memory/semantic/semantic_memory.jsonl"),
    Path("memory/semantic/semantic_memory_faiss.index"),
    Path("memory/semantic/semantic_memory_faiss_ids.json"),
)
SNAPSHOT_ROOT = Path("memory/rollback_snapshots")


def create_memory_snapshot(reason: str, snapshot_root: Path = SNAPSHOT_ROOT) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    target = snapshot_root / stamp
    target.mkdir(parents=True, exist_ok=False)
    for src in CANONICAL_FILES:
        if src.exists():
            shutil.copy2(src, target / src.name)
    (target / "SNAPSHOT_REASON.txt").write_text(reason + "\n", encoding="utf-8")
    return target


def latest_snapshot(snapshot_root: Path = SNAPSHOT_ROOT) -> Path | None:
    if not snapshot_root.exists():
        return None
    candidates = sorted([p for p in snapshot_root.iterdir() if p.is_dir()])
    return candidates[-1] if candidates else None
