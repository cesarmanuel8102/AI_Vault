from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path

CANONICAL_FILES = (
    Path("memory/semantic/semantic_memory.jsonl"),
    Path("memory/semantic/semantic_memory_faiss.index"),
    Path("memory/semantic/semantic_memory_faiss_ids.json"),
)
SNAPSHOT_ROOT = Path("memory/rollback_snapshots")
ISOLATED_ROOT_MARKER = ".r6_2_isolated_root"
ISOLATED_ARTIFACTS = (
    "semantic_memory.jsonl",
    "semantic_memory_faiss.index",
    "semantic_memory_faiss_ids.json",
)


def _isolated_root_or_error(root: Path) -> tuple[Path | None, str]:
    resolved = Path(root).resolve()
    if resolved.name.lower() == "memory" or not resolved.exists():
        return None, "isolated_root_invalid"
    if not (resolved / ISOLATED_ROOT_MARKER).is_file():
        return None, "isolated_root_marker_missing"
    return resolved, ""


def create_isolated_memory_snapshot(isolated_root: Path, receipt_sha256: str) -> dict[str, object]:
    """Snapshot only a marker-bound temporary root for R6.2 contracts."""
    root, error = _isolated_root_or_error(isolated_root)
    if root is None:
        return {"ok": False, "reason": error}
    if not isinstance(receipt_sha256, str) or len(receipt_sha256) != 64:
        return {"ok": False, "reason": "receipt_sha256_invalid"}
    files: dict[str, dict[str, object]] = {}
    for name in ISOLATED_ARTIFACTS:
        artifact = root / name
        if not artifact.is_file():
            return {"ok": False, "reason": "isolated_artifact_missing"}
        content = artifact.read_bytes()
        files[name] = {"sha256": hashlib.sha256(content).hexdigest(), "size_bytes": len(content)}
    snapshots = root / ".r6_2_snapshots"
    snapshots.mkdir(exist_ok=True)
    snapshot_dir = Path(tempfile.mkdtemp(prefix="snapshot-", dir=snapshots))
    for name in ISOLATED_ARTIFACTS:
        shutil.copy2(root / name, snapshot_dir / name)
    manifest = {"schema_version": 1, "receipt_sha256": receipt_sha256, "files": files}
    (snapshot_dir / "manifest.json").write_text(
        json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8"
    )
    return {
        "ok": True,
        "receipt_sha256": receipt_sha256,
        "snapshot_dir": str(snapshot_dir),
        "manifest": manifest,
    }


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
