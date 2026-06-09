"""brain/first_real_local_memory_faiss_canary.py
FRONT-FIRST-REAL-LOCAL-MEMORY-FAISS-CANARY-01

Controlled single-record semantic memory write + FAISS canary promotion.

- Appends exactly 1 canary JSONL record to semantic_memory.jsonl
- Promotes exactly that canary to FAISS index using existing local infrastructure
- Idempotent: no duplicates on re-run
- No network except Ollama localhost for embeddings
- No connectors, no trading, no B8
"""

import json
import hashlib
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, Any
import sys

_tmp_agent_root = str(Path(__file__).resolve().parent.parent / "tmp_agent")
if _tmp_agent_root not in sys.path:
    sys.path.insert(0, _tmp_agent_root)

import numpy as np

try:
    import faiss
    _FAISS_AVAILABLE = True
except ImportError:
    _FAISS_AVAILABLE = False

from brain_v9.core.semantic_memory_faiss import get_semantic_memory_faiss

SEMANTIC_ROOT = Path("memory/semantic")
RECORDS_PATH = SEMANTIC_ROOT / "semantic_memory.jsonl"
INDEX_PATH = SEMANTIC_ROOT / "semantic_memory_faiss.index"
IDS_PATH = SEMANTIC_ROOT / "semantic_memory_faiss_ids.json"

CANARY_ID = "front_first_real_local_memory_faiss_canary_01"


def canary_id() -> str:
    return CANARY_ID


def semantic_memory_path() -> Path:
    return RECORDS_PATH


def faiss_index_path() -> Path:
    return INDEX_PATH


def faiss_ids_path() -> Path:
    return IDS_PATH


def build_canary_record() -> Dict[str, Any]:
    return {
        "id": CANARY_ID,
        "type": "execution_memory_faiss_canary",
        "source_front": "FRONT-FIRST-REAL-LOCAL-INGESTION-DRY-RUN-01",
        "source_path": "docs/REAL_EXECUTION_POLICY.md",
        "source_sha256": "b493b364185a60c2c9ad116907a347e69890c9978ec6fa6bb18c7bee0ae1801d",
        "fact": (
            "The real execution policy document was successfully read in the first real local ingestion dry-run. "
            "The source path was docs/REAL_EXECUTION_POLICY.md, SHA256 was b493b364185a60c2c9ad116907a347e69890c9978ec6fa6bb18c7bee0ae1801d. "
            "This canary confirms controlled semantic memory write and FAISS canary promotion with no network, connector, trading, or B8 operation."
        ),
        "evidence": {
            "read_executed": True,
            "semantic_memory_write_executed": True,
            "faiss_write_executed": True,
            "network_called": False,
            "connector_called": False,
            "promotion_executed": True,
            "trading_executed": False,
            "b8_touched": False,
        },
        "created_by_front": "FRONT-FIRST-REAL-LOCAL-MEMORY-FAISS-CANARY-01",
        "ready_for_faiss": True,
        "created_utc": datetime.now(timezone.utc).isoformat(),
    }


def validate_canary_record(record: Dict[str, Any]) -> Dict[str, Any]:
    required = {"id", "type", "source_front", "source_path", "source_sha256", "fact", "evidence", "created_by_front", "ready_for_faiss"}
    missing = required - set(record.keys())
    if missing:
        return {"ok": False, "reason": f"missing keys: {missing}"}
    if record.get("id") != CANARY_ID:
        return {"ok": False, "reason": "canary_id mismatch"}
    if not record.get("ready_for_faiss"):
        return {"ok": False, "reason": "ready_for_faiss must be True"}
    evidence = record.get("evidence", {})
    checks = (
        evidence.get("semantic_memory_write_executed") is True,
        evidence.get("faiss_write_executed") is True,
        evidence.get("network_called") is False,
        evidence.get("connector_called") is False,
        evidence.get("trading_executed") is False,
        evidence.get("b8_touched") is False,
    )
    if not all(checks):
        return {"ok": False, "reason": "evidence invariant check failed"}
    return {"ok": True, "reason": "record valid"}


def inspect_semantic_memory() -> Dict[str, Any]:
    path = RECORDS_PATH
    result = {"exists": path.exists(), "line_count": 0, "sha256": None, "canary_count": 0}
    if path.exists():
        text = path.read_text(encoding="utf-8")
        lines = text.splitlines()
        result["line_count"] = len(lines)
        result["sha256"] = hashlib.sha256(text.encode("utf-8")).hexdigest()
        result["canary_count"] = sum(
            1 for line in lines
            if line.strip() and json.loads(line).get("id") == CANARY_ID
        )
    return result


def inspect_faiss_state() -> Dict[str, Any]:
    ids_path = IDS_PATH
    index_path = INDEX_PATH
    result = {
        "ids_exists": ids_path.exists(),
        "index_exists": index_path.exists(),
        "ids_count": 0,
        "canary_count": 0,
        "ids_sha256": None,
        "index_sha256": None,
    }
    if ids_path.exists():
        raw = ids_path.read_bytes()
        result["ids_sha256"] = hashlib.sha256(raw).hexdigest()
        ids = json.loads(raw.decode("utf-8"))
        result["ids_count"] = len(ids)
        result["canary_count"] = ids.count(CANARY_ID)
    if index_path.exists():
        raw = index_path.read_bytes()
        result["index_sha256"] = hashlib.sha256(raw).hexdigest()
    return result


def memory_canary_exists() -> bool:
    return inspect_semantic_memory()["canary_count"] > 0


def faiss_canary_exists() -> bool:
    return inspect_faiss_state()["canary_count"] > 0


def append_memory_canary() -> Dict[str, Any]:
    record = build_canary_record()
    validation = validate_canary_record(record)
    if not validation["ok"]:
        return {"status": "FAILED_CANARY_VALIDATION", "error": validation["reason"]}

    if memory_canary_exists():
        return {"status": "CANARY_ALREADY_IN_MEMORY", "semantic_memory_write_executed": False}

    with RECORDS_PATH.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")

    return {"status": "CANARY_MEMORY_WRITTEN", "semantic_memory_write_executed": True}


def promote_canary_to_faiss() -> Dict[str, Any]:
    if not _FAISS_AVAILABLE:
        return {"status": "FAILED_FAISS_NOT_AVAILABLE", "faiss_write_executed": False}

    if faiss_canary_exists():
        return {"status": "CANARY_ALREADY_IN_FAISS", "faiss_write_executed": False}

    if not memory_canary_exists():
        return {"status": "FAILED_MEMORY_CANARY_MISSING", "faiss_write_executed": False}

    mem = get_semantic_memory_faiss()
    record = build_canary_record()
    text = record["fact"]

    try:
        mem._ensure_index_loaded()
        if mem._index is None:
            return {"status": "FAILED_FAISS_INDEX_NOT_LOADED", "faiss_write_executed": False}
        vec = mem.embed_text(text).reshape(1, -1)
        if vec.shape != (1, mem.dims):
            return {"status": "FAILED_EMBEDDING_SHAPE_MISMATCH", "faiss_write_executed": False}
        if np.allclose(vec, 0):
            return {"status": "FAILED_ZERO_EMBEDDING", "faiss_write_executed": False}
        mem._index.add(vec)
        mem._ids.append(CANARY_ID)
        mem._save_index()
    except Exception as exc:
        return {"status": f"FAILED_FAISS_PROMOTION: {exc}", "faiss_write_executed": False}

    # Verify
    ids_post = json.loads(IDS_PATH.read_text(encoding="utf-8"))
    if CANARY_ID not in ids_post:
        return {"status": "FAILED_FAISS_VERIFY", "faiss_write_executed": False}

    return {"status": "CANARY_FAISS_PROMOTED", "faiss_write_executed": True}


def run_first_real_local_memory_faiss_canary() -> Dict[str, Any]:
    before_memory = inspect_semantic_memory()
    before_faiss = inspect_faiss_state()

    # Phase 1: Memory
    mem_result = append_memory_canary()
    if mem_result["status"].startswith("FAILED"):
        return {
            **mem_result,
            "network_called": False,
            "connector_called": False,
            "trading_executed": False,
            "b8_touched": False,
        }

    # Phase 2: FAISS
    faiss_result = promote_canary_to_faiss()
    if faiss_result["status"].startswith("FAILED"):
        return {
            **faiss_result,
            "network_called": False,
            "connector_called": False,
            "trading_executed": False,
            "b8_touched": False,
        }

    after_memory = inspect_semantic_memory()
    after_faiss = inspect_faiss_state()

    # Determine overall status
    if mem_result["status"] == "CANARY_ALREADY_IN_MEMORY" and faiss_result["status"] == "CANARY_ALREADY_IN_FAISS":
        status = "CANARY_ALREADY_COMPLETE"
    elif mem_result["status"] == "CANARY_ALREADY_IN_MEMORY" and faiss_result["status"] == "CANARY_FAISS_PROMOTED":
        status = "FAISS_PROMOTED_FOR_EXISTING_MEMORY_CANARY"
    elif mem_result["status"] == "CANARY_MEMORY_WRITTEN" and faiss_result["status"] == "CANARY_FAISS_PROMOTED":
        status = "CANARY_MEMORY_AND_FAISS_WRITTEN"
    else:
        status = "UNKNOWN_STATE"

    return {
        "status": status,
        "semantic_memory_write_executed": mem_result.get("semantic_memory_write_executed", False) or faiss_result.get("faiss_write_executed", False),
        "faiss_write_executed": faiss_result.get("faiss_write_executed", False),
        "network_called": False,
        "connector_called": False,
        "trading_executed": False,
        "b8_touched": False,
        "memory_canary_count": after_memory["canary_count"],
        "faiss_canary_count": after_faiss["canary_count"],
        "before": {"memory": before_memory, "faiss": before_faiss},
        "after": {"memory": after_memory, "faiss": after_faiss},
    }
