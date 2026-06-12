from __future__ import annotations

import shutil
from pathlib import Path

CANONICAL_DIR = Path("memory/semantic")
REQUIRED = ("semantic_memory.jsonl", "semantic_memory_faiss.index", "semantic_memory_faiss_ids.json")


def verify_snapshot(snapshot_dir: Path) -> bool:
    return snapshot_dir.exists() and all((snapshot_dir / name).exists() for name in REQUIRED)


def rollback_from_snapshot(snapshot_dir: Path, dry_run: bool = True) -> dict[str, object]:
    if not verify_snapshot(snapshot_dir):
        return {"ok": False, "reason": "snapshot_incomplete", "dry_run": dry_run}
    if dry_run:
        return {"ok": True, "reason": "dry_run_verified", "dry_run": True}
    for name in REQUIRED:
        shutil.copy2(snapshot_dir / name, CANONICAL_DIR / name)
    return {"ok": True, "reason": "rollback_applied", "dry_run": False}
