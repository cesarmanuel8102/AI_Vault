from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping
from uuid import uuid4

from .canonical import canonical_bytes


@dataclass(frozen=True)
class ManifestReceipt:
    bundle_id: str
    path: Path
    manifest_sha256: str
    file_count: int


class AuditExporter:
    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def publish(self, records: Mapping[str, object]) -> ManifestReceipt:
        if not records:
            raise ValueError("at least one audit record is required")
        for name in records:
            _validate_name(name)

        staging = self.root / f".{uuid4().hex}-staging"
        staging.mkdir(exist_ok=False)
        try:
            files: dict[str, str] = {}
            for name in sorted(records):
                payload = canonical_bytes(records[name])
                (staging / name).write_bytes(payload)
                files[name] = hashlib.sha256(payload).hexdigest()

            bundle_digest = hashlib.sha256(canonical_bytes(files)).hexdigest()
            bundle_id = f"audit-{bundle_digest[:24]}"
            manifest = {
                "schema": "AUDIT_EXPORT_MANIFEST_V1",
                "bundle_id": bundle_id,
                "bundle_sha256": bundle_digest,
                "files": files,
            }
            manifest_bytes = canonical_bytes(manifest)
            manifest_sha256 = hashlib.sha256(manifest_bytes).hexdigest()
            (staging / "manifest.json").write_bytes(manifest_bytes)
            _make_files_read_only(staging)

            final = self.root / bundle_id
            if final.exists():
                existing = final / "manifest.json"
                if not existing.is_file() or hashlib.sha256(
                    existing.read_bytes()
                ).hexdigest() != manifest_sha256:
                    raise FileExistsError(f"bundle identity collision: {bundle_id}")
                _make_files_writable(staging)
                shutil.rmtree(staging)
            else:
                os.replace(staging, final)
            return ManifestReceipt(
                bundle_id=bundle_id,
                path=final,
                manifest_sha256=manifest_sha256,
                file_count=len(files),
            )
        except Exception:
            if staging.exists():
                _make_files_writable(staging)
                shutil.rmtree(staging)
            raise


def _validate_name(name: str) -> None:
    path = Path(name)
    if (
        not name
        or path.name != name
        or name in {"manifest.json", ".", ".."}
        or path.suffix.lower() != ".json"
    ):
        raise ValueError(f"unsafe audit record name: {name!r}")


def _make_files_read_only(directory: Path) -> None:
    for path in directory.iterdir():
        if path.is_file():
            path.chmod(stat.S_IREAD)


def _make_files_writable(directory: Path) -> None:
    for path in directory.iterdir():
        if path.is_file():
            path.chmod(stat.S_IREAD | stat.S_IWRITE)
