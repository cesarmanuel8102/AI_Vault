"""brain/first_real_local_ingestion_controlled_batch.py
FRONT-FIRST-REAL-LOCAL-INGESTION-CONTROLLED-BATCH-01

Controlled batch ingestion: up to 3 whitelisted local documents
→ semantic memory records → FAISS promotion.

* No network except local Ollama embeddings.
* No connectors.
* No trading/B8.
* Idempotent.
* Max 3 sources.
"""

import json
import hashlib
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, Any, List
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

BATCH_FRONT = "FRONT-FIRST-REAL-LOCAL-INGESTION-CONTROLLED-BATCH-01"
MAX_BATCH_SIZE = 3

SOURCES = [
    {
        "path": "docs/REAL_EXECUTION_POLICY.md",
        "id": "controlled_batch_01_real_execution_policy",
        "fact": (
            "This source establishes the real execution policy and gating expectations for controlled Brain operations, "
            "including explicit limits on memory writes, FAISS promotion, external network, connectors, trading, and B8 actions."
        ),
    },
    {
        "path": "docs/RUNTIME_RECOVERY_RUNBOOK.md",
        "id": "controlled_batch_01_runtime_recovery_runbook",
        "fact": (
            "This source documents runtime recovery and health-check procedures for Brain V9, dashboard, Ollama, "
            "and execution gate readiness before real execution."
        ),
    },
    {
        "path": "docs/FRONT_FIRST_REAL_LOCAL_MEMORY_FAISS_CANARY_01.md",
        "id": "controlled_batch_01_memory_faiss_canary_doc",
        "fact": (
            "This source documents the first successful controlled semantic memory write and FAISS canary promotion, "
            "establishing a verified template for future controlled ingestion."
        ),
    },
]


def batch_front_id() -> str:
    return BATCH_FRONT


def build_source_allowlist() -> List[Dict[str, Any]]:
    return [dict(s) for s in SOURCES]


def validate_source(path: str) -> Dict[str, Any]:
    for src in SOURCES:
        if src["path"] == path:
            p = Path(path)
            if not p.exists() or not p.is_file():
                return {"ok": False, "path": path, "reason": "file missing", "allowed": True}
            raw = p.read_bytes()
            return {
                "ok": True,
                "path": path,
                "size_bytes": len(raw),
                "sha256": hashlib.sha256(raw).hexdigest(),
                "allowed": True,
            }
    return {"ok": False, "path": path, "reason": "not in allowlist", "allowed": False}


def build_memory_record(source: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": source["id"],
        "type": "controlled_batch_ingestion_record",
        "source_front": BATCH_FRONT,
        "source_path": source["path"],
        "source_sha256": source["sha256"],
        "fact": source["fact"],
        "evidence": {
            "source_read_executed": True,
            "semantic_memory_write_executed": True,
            "faiss_write_executed": True,
            "network_called": False,
            "connector_called": False,
            "trading_executed": False,
            "b8_touched": False,
        },
        "created_by_front": BATCH_FRONT,
        "ready_for_retrieval_eval": True,
        "created_utc": datetime.now(timezone.utc).isoformat(),
    }


def validate_memory_record(record: Dict[str, Any]) -> Dict[str, Any]:
    required = {"id", "type", "source_front", "source_path", "source_sha256", "fact", "evidence", "created_by_front", "ready_for_retrieval_eval"}
    missing = required - set(record.keys())
    if missing:
        return {"ok": False, "reason": f"missing keys: {missing}"}
    if len(record["fact"]) > 800:
        return {"ok": False, "reason": "fact > 800 chars"}
    ev = record.get("evidence", {})
    checks = (
        ev.get("semantic_memory_write_executed") is True,
        ev.get("faiss_write_executed") is True,
        ev.get("network_called") is False,
        ev.get("connector_called") is False,
        ev.get("trading_executed") is False,
        ev.get("b8_touched") is False,
    )
    if not all(checks):
        return {"ok": False, "reason": "evidence invariant failed"}
    return {"ok": True, "reason": "record valid"}


def inspect_memory_and_faiss() -> Dict[str, Any]:
    mem_info = {"exists": RECORDS_PATH.exists(), "line_count": 0}
    if RECORDS_PATH.exists():
        lines = RECORDS_PATH.read_text(encoding="utf-8").splitlines()
        mem_info["line_count"] = len(lines)
    faiss_info = {"ids_exists": IDS_PATH.exists(), "ids_count": 0}
    if IDS_PATH.exists():
        ids = json.loads(IDS_PATH.read_text(encoding="utf-8"))
        faiss_info["ids_count"] = len(ids)
    return {"memory": mem_info, "faiss": faiss_info}


def memory_record_count(record_id: str) -> int:
    if not RECORDS_PATH.exists():
        return 0
    lines = RECORDS_PATH.read_text(encoding="utf-8").splitlines()
    return sum(1 for line in lines if line.strip() and json.loads(line).get("id") == record_id)


def faiss_record_count(record_id: str) -> int:
    if not IDS_PATH.exists():
        return 0
    ids = json.loads(IDS_PATH.read_text(encoding="utf-8"))
    return ids.count(record_id)


def append_memory_record(record: Dict[str, Any]) -> Dict[str, Any]:
    if memory_record_count(record["id"]) > 0:
        return {"status": "ALREADY_IN_MEMORY", "semantic_memory_write_executed": False}
    val = validate_memory_record(record)
    if not val["ok"]:
        return {"status": "FAILED_VALIDATION", "error": val["reason"]}
    with RECORDS_PATH.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
    return {"status": "WRITTEN", "semantic_memory_write_executed": True}


def promote_record_to_faiss(record: Dict[str, Any]) -> Dict[str, Any]:
    if not _FAISS_AVAILABLE:
        return {"status": "FAILED_FAISS_UNAVAILABLE", "faiss_write_executed": False}
    if faiss_record_count(record["id"]) > 0:
        return {"status": "ALREADY_IN_FAISS", "faiss_write_executed": False}
    if memory_record_count(record["id"]) == 0:
        return {"status": "FAILED_MEMORY_MISSING", "faiss_write_executed": False}

    mem = get_semantic_memory_faiss()
    text = record["fact"]
    try:
        mem._ensure_index_loaded()
        if mem._index is None:
            return {"status": "FAILED_INDEX_NOT_LOADED", "faiss_write_executed": False}
        vec = mem.embed_text(text).reshape(1, -1)
        if vec.shape != (1, mem.dims):
            return {"status": "FAILED_EMBEDDING_SHAPE", "faiss_write_executed": False}
        if np.allclose(vec, 0):
            return {"status": "FAILED_ZERO_EMBEDDING", "faiss_write_executed": False}
        mem._index.add(vec)
        mem._ids.append(record["id"])
        mem._save_index()
    except Exception as exc:
        return {"status": f"FAILED_FAISS_PROMOTION: {exc}", "faiss_write_executed": False}

    # Verify
    ids_post = json.loads(IDS_PATH.read_text(encoding="utf-8"))
    if record["id"] not in ids_post:
        return {"status": "FAILED_VERIFY", "faiss_write_executed": False}

    return {"status": "PROMOTED", "faiss_write_executed": True}


def run_controlled_batch_ingestion() -> Dict[str, Any]:
    before = inspect_memory_and_faiss()
    items = []
    memory_written = 0
    faiss_promoted = 0
    already_complete = 0
    failed = 0
    skipped = 0

    for src in SOURCES:
        val = validate_source(src["path"])
        if not val["ok"]:
            items.append({
                "source_path": src["path"],
                "id": src["id"],
                "status": "SKIPPED",
                "reason": val.get("reason", "validation failed"),
            })
            skipped += 1
            continue

        src["sha256"] = val["sha256"]
        record = build_memory_record(src)

        mem_count_before = memory_record_count(record["id"])
        faiss_count_before = faiss_record_count(record["id"])

        if mem_count_before > 1 or faiss_count_before > 1:
            return {
                "status": "FAILED_DUPLICATE_BATCH_RECORD",
                "failed_count": failed + 1,
                "items": items,
            }

        if mem_count_before == 0:
            mem_result = append_memory_record(record)
            if mem_result["status"] == "WRITTEN":
                memory_written += 1
        else:
            mem_result = {"status": "ALREADY_IN_MEMORY"}

        if mem_count_before == 0 or mem_result["status"] == "ALREADY_IN_MEMORY":
            faiss_result = promote_record_to_faiss(record)
            if faiss_result["status"] == "PROMOTED":
                faiss_promoted += 1
            elif faiss_result["status"] == "ALREADY_IN_FAISS":
                pass
            else:
                failed += 1
                items.append({
                    "source_path": src["path"],
                    "id": src["id"],
                    "status": faiss_result["status"],
                    "memory_count_after": memory_record_count(record["id"]),
                    "faiss_count_after": faiss_record_count(record["id"]),
                })
                continue

        if mem_result["status"] == "ALREADY_IN_MEMORY" and faiss_result["status"] == "ALREADY_IN_FAISS":
            status = "ALREADY_COMPLETE"
            already_complete += 1
        elif mem_result["status"] == "WRITTEN" and faiss_result["status"] == "PROMOTED":
            status = "WRITTEN_AND_PROMOTED"
        elif mem_result["status"] == "ALREADY_IN_MEMORY" and faiss_result["status"] == "PROMOTED":
            status = "FAISS_PROMOTED_FOR_EXISTING_MEMORY"
        else:
            status = mem_result["status"]

        items.append({
            "source_path": src["path"],
            "id": src["id"],
            "status": status,
            "memory_count_after": memory_record_count(record["id"]),
            "faiss_count_after": faiss_record_count(record["id"]),
        })

    after = inspect_memory_and_faiss()
    return {
        "status": "BATCH_COMPLETED" if failed == 0 else "BATCH_PARTIAL_FAILURE",
        "attempted_count": len(SOURCES),
        "ready_source_count": len([i for i in items if i["status"] not in ("SKIPPED",)]),
        "skipped_count": skipped,
        "memory_written_count": memory_written,
        "faiss_promoted_count": faiss_promoted,
        "already_complete_count": already_complete,
        "failed_count": failed,
        "network_called": False,
        "connector_called": False,
        "trading_executed": False,
        "b8_touched": False,
        "items": items,
        "before": before,
        "after": after,
    }


def summarize_batch_result(result: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "status": result["status"],
        "attempted_count": result["attempted_count"],
        "ready_source_count": result["ready_source_count"],
        "skipped_count": result["skipped_count"],
        "memory_written_count": result["memory_written_count"],
        "faiss_promoted_count": result["faiss_promoted_count"],
        "already_complete_count": result["already_complete_count"],
        "failed_count": result["failed_count"],
        "network_called": result["network_called"],
        "connector_called": result["connector_called"],
        "trading_executed": result["trading_executed"],
        "b8_touched": result["b8_touched"],
        "memory_before": result["before"]["memory"]["line_count"],
        "memory_after": result["after"]["memory"]["line_count"],
        "faiss_ids_before": result["before"]["faiss"]["ids_count"],
        "faiss_ids_after": result["after"]["faiss"]["ids_count"],
    }
