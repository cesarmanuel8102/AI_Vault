from __future__ import annotations

import shutil
import hashlib
import json
import os
from pathlib import Path

from tmp_agent.brain_v9.memory.memory_snapshot import (
    ISOLATED_ARTIFACTS,
    _isolated_root_or_error,
    isolated_retrieval_root_or_error,
)

CANONICAL_DIR = Path("memory/semantic")
REQUIRED = ("semantic_memory.jsonl", "semantic_memory_faiss.index", "semantic_memory_faiss_ids.json")


def rollback_isolated_snapshot(
    isolated_root: Path, snapshot: dict[str, object], receipt_sha256: str
) -> dict[str, object]:
    """Restore a verified R6.2 temporary snapshot without touching canonical memory."""
    root, error = _isolated_root_or_error(isolated_root)
    if root is None:
        return {"ok": False, "reason": error}
    if not isinstance(snapshot, dict) or set(snapshot) != {
        "ok", "receipt_sha256", "snapshot_dir", "manifest"
    }:
        return {"ok": False, "reason": "snapshot_receipt_invalid"}
    if snapshot.get("ok") is not True or snapshot.get("receipt_sha256") != receipt_sha256:
        return {"ok": False, "reason": "snapshot_receipt_mismatch"}
    snapshot_dir = Path(str(snapshot.get("snapshot_dir") or "")).resolve()
    allowed_parent = (root / ".r6_2_snapshots").resolve()
    if snapshot_dir.parent != allowed_parent or not snapshot_dir.is_dir():
        return {"ok": False, "reason": "snapshot_path_invalid"}
    try:
        manifest = json.loads((snapshot_dir / "manifest.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"ok": False, "reason": "snapshot_manifest_invalid"}
    if manifest != snapshot.get("manifest") or manifest.get("receipt_sha256") != receipt_sha256:
        return {"ok": False, "reason": "snapshot_manifest_mismatch"}
    files = manifest.get("files")
    if not isinstance(files, dict) or set(files) != set(ISOLATED_ARTIFACTS):
        return {"ok": False, "reason": "snapshot_manifest_files_invalid"}
    staged: list[tuple[Path, Path]] = []
    try:
        for name in ISOLATED_ARTIFACTS:
            source = snapshot_dir / name
            expected = files[name]
            content = source.read_bytes()
            if not isinstance(expected, dict) or expected.get("sha256") != hashlib.sha256(content).hexdigest():
                return {"ok": False, "reason": "snapshot_artifact_hash_mismatch"}
            temporary = root / f".{name}.r6_2_restore"
            temporary.write_bytes(content)
            staged.append((temporary, root / name))
        for temporary, destination in staged:
            os.replace(temporary, destination)
    except OSError:
        for temporary, _ in staged:
            temporary.unlink(missing_ok=True)
        return {"ok": False, "reason": "isolated_rollback_io_failed"}
    return {"ok": True, "reason": "rollback_applied", "receipt_sha256": receipt_sha256}


def rollback_isolated_retrieval_snapshot(
    isolated_root: Path, snapshot: dict[str, object], receipt_sha256: str
) -> dict[str, object]:
    """Restore only a receipt-bound R6.3 isolated retrieval snapshot."""
    root, error = isolated_retrieval_root_or_error(isolated_root)
    if root is None:
        return {"ok": False, "reason": error}
    if not isinstance(snapshot, dict) or set(snapshot) != {
        "ok", "receipt_sha256", "snapshot_dir", "manifest"
    }:
        return {"ok": False, "reason": "retrieval_snapshot_receipt_invalid"}
    if snapshot.get("ok") is not True or snapshot.get("receipt_sha256") != receipt_sha256:
        return {"ok": False, "reason": "retrieval_snapshot_receipt_mismatch"}
    snapshot_dir = Path(str(snapshot.get("snapshot_dir") or "")).resolve()
    allowed_parent = (root / ".r6_3_snapshots").resolve()
    if snapshot_dir.parent != allowed_parent or not snapshot_dir.is_dir():
        return {"ok": False, "reason": "retrieval_snapshot_path_invalid"}
    try:
        manifest = json.loads((snapshot_dir / "manifest.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"ok": False, "reason": "retrieval_snapshot_manifest_invalid"}
    if manifest != snapshot.get("manifest") or manifest.get("receipt_sha256") != receipt_sha256:
        return {"ok": False, "reason": "retrieval_snapshot_manifest_mismatch"}
    files = manifest.get("files")
    if not isinstance(files, dict) or set(files) != set(ISOLATED_ARTIFACTS):
        return {"ok": False, "reason": "retrieval_snapshot_manifest_files_invalid"}
    staged: list[tuple[Path, Path]] = []
    try:
        for name in ISOLATED_ARTIFACTS:
            content = (snapshot_dir / name).read_bytes()
            expected = files[name]
            if not isinstance(expected, dict) or expected.get("sha256") != hashlib.sha256(content).hexdigest():
                return {"ok": False, "reason": "retrieval_snapshot_artifact_hash_mismatch"}
            temporary = root / f".{name}.r6_3_restore"
            temporary.write_bytes(content)
            staged.append((temporary, root / name))
        for temporary, destination in staged:
            os.replace(temporary, destination)
    except OSError:
        for temporary, _ in staged:
            temporary.unlink(missing_ok=True)
        return {"ok": False, "reason": "isolated_retrieval_rollback_io_failed"}
    return {"ok": True, "reason": "rollback_applied", "receipt_sha256": receipt_sha256}


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
