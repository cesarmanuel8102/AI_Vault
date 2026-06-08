"""
brain/semantic_memory_faiss_promotion.py
FRONT-REAL-MEMORY-FAISS-PROMOTION-01

Controlled single-record promotion adapter.
Promotes ONLY the canary record from semantic_memory.jsonl to FAISS index.
No writes to semantic_memory.jsonl.
No mass promotions.
Uses existing SemanticMemoryFAISS infrastructure with Ollama embeddings.
"""

import json
import hashlib
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional

import sys
from pathlib import Path

_tmp_agent_root = str(Path(__file__).resolve().parent.parent / "tmp_agent")
if _tmp_agent_root not in sys.path:
    sys.path.insert(0, _tmp_agent_root)

import numpy as np
try:
    import faiss
    _FAISS_AVAILABLE = True
except ImportError:
    _FAISS_AVAILABLE = False

from brain_v9.core.semantic_memory_faiss import (
    get_semantic_memory_faiss,
    SemanticMemoryFAISS,
)

SEMANTIC_ROOT = Path("memory/semantic")
RECORDS_PATH = SEMANTIC_ROOT / "semantic_memory.jsonl"
INDEX_PATH = SEMANTIC_ROOT / "semantic_memory_faiss.index"
IDS_PATH = SEMANTIC_ROOT / "semantic_memory_faiss_ids.json"
NPZ_PATH = SEMANTIC_ROOT / "semantic_memory_index.npz"

CANARY_ID = "canary-00000000-0000-0000-0000-000000000001"


def _sha256_file(path: Path) -> str:
    """Return SHA-256 hex digest of a file."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(65536)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def load_canary_record(jsonl_path: Path = RECORDS_PATH, canary_id: str = CANARY_ID) -> Optional[Dict[str, Any]]:
    """Read-only load of the canary record from JSONL."""
    if not jsonl_path.is_file():
        return None
    with open(jsonl_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                if obj.get("id") == canary_id:
                    return obj
            except (json.JSONDecodeError,):
                continue
    return None


def load_faiss_ids(ids_path: Path = IDS_PATH) -> List[str]:
    """Load FAISS id mapping list from JSON."""
    if not ids_path.is_file():
        return []
    with open(ids_path, "r", encoding="utf-8") as f:
        return json.load(f)


def canary_already_promoted(ids: List[str], canary_id: str = CANARY_ID) -> bool:
    """Check if canary id is already present in the FAISS ids list."""
    return canary_id in ids


def promote_canary_to_faiss(
    mem: SemanticMemoryFAISS,
    canary_id: str = CANARY_ID,
    records_path: Path = RECORDS_PATH,
) -> Dict[str, Any]:
    """
    Promote a single canary record into the FAISS index.
    Does NOT modify semantic_memory.jsonl.
    If already present, returns no-op.
    """
    result = {
        "canary_id": canary_id,
        "promoted": False,
        "already_present": False,
        "error": None,
        "semantic_memory_jsonl_modified": False,
        "faiss_write_executed": False,
        "no_write_to_jsonl": True,
    }

    canary = load_canary_record(records_path, canary_id)
    if canary is None:
        result["error"] = "canary_not_found_in_jsonl"
        return result

    existing_ids = load_faiss_ids(mem.ids_path)
    if canary_already_promoted(existing_ids, canary_id):
        result["already_present"] = True
        result["promoted"] = False
        return result

    if not _FAISS_AVAILABLE:
        result["error"] = "faiss_not_available"
        return result

    # Compute embedding via Ollama
    text = str(canary.get("text", "")).strip()
    if not text:
        result["error"] = "canary_text_empty"
        return result

    try:
        vec = mem.embed_text(text).reshape(1, -1)
        if vec.shape != (1, mem.dims):
            result["error"] = f"embedding_shape_mismatch: expected (1,{mem.dims}), got {vec.shape}"
            return result
        if np.allclose(vec, 0):
            result["error"] = "embedding_zero_vector"
            return result
    except Exception as exc:
        result["error"] = f"embedding_exception: {exc}"
        return result

    # Load existing index, add single vector, save
    try:
        mem._ensure_index_loaded()
        if mem._index is None:
            result["error"] = "faiss_index_not_loaded"
            return result

        mem._index.add(vec)
        mem._ids.append(canary_id)
        mem._save_index()

        result["promoted"] = True
        result["faiss_write_executed"] = True
        result["ids_after_count"] = len(mem._ids)
        result["index_ntotal"] = mem._index.ntotal

    except Exception as exc:
        result["error"] = f"faiss_write_exception: {exc}"
        return result

    # Verify id now present in ids
    ids_post = load_faiss_ids(mem.ids_path)
    if canary_id not in ids_post:
        result["promoted"] = False
        result["error"] = "canary_id_not_found_after_write"
        return result

    result["already_present"] = False
    return result


def validate_post_promotion(
    baseline_snapshot: Dict[str, Any],
    result: Dict[str, Any],
    canary_id: str = CANARY_ID,
    records_path: Path = RECORDS_PATH,
    index_path: Path = INDEX_PATH,
    ids_path: Path = IDS_PATH,
) -> Dict[str, Any]:
    """Validate hashes, single canary id, semantic_memory unchanged."""
    validation = {
        "semantic_memory_jsonl_unchanged": False,
        "canary_unique_in_ids": False,
        "canary_exactly_once": False,
        "invalid": False,
    }

    # Check semantic_memory.jsonl hash unchanged
    if records_path.is_file():
        current_sha = _sha256_file(records_path)
        baseline_sha = baseline_snapshot.get("semantic_memory_jsonl", {}).get("sha256")
        validation["semantic_memory_jsonl_unchanged"] = (current_sha == baseline_sha)

    # Check id uniqueness in ids
    ids = load_faiss_ids(ids_path)
    canary_count = ids.count(canary_id)
    validation["canary_unique_in_ids"] = (canary_count <= 1)
    validation["canary_exactly_once"] = (canary_count == 1)

    # If any failure
    if not validation["semantic_memory_jsonl_unchanged"]:
        validation["invalid"] = True
        return validation
    if result.get("promoted") and not validation["canary_exactly_once"]:
        validation["invalid"] = True
        return validation

    return validation


def restore_from_backup(
    backup_dir: Path,
    records_path: Path = RECORDS_PATH,
    index_path: Path = INDEX_PATH,
    ids_path: Path = IDS_PATH,
    npz_path: Path = NPZ_PATH,
) -> Dict[str, Any]:
    """Restore FAISS/index files from backups. Does NOT restore memory JSONL."""
    result = {
        "restored": False,
        "files_restored": [],
        "errors": [],
    }
    for src, dst in [
        (backup_dir / index_path.name, index_path),
        (backup_dir / ids_path.name, ids_path),
        (backup_dir / npz_path.name, npz_path),
    ]:
        if src.is_file():
            try:
                shutil.copy2(src, dst)
                result["files_restored"].append(str(dst))
            except Exception as exc:
                result["errors"].append(f"{dst}: {exc}")
    if all(
        dst.exists()
        for _, dst in [
            (backup_dir / index_path.name, index_path),
            (backup_dir / ids_path.name, ids_path),
            (backup_dir / npz_path.name, npz_path),
        ]
    ):
        result["restored"] = True
    return result
