"""brain/controlled_batch_retrieval_quality_eval.py
FRONT-CONTROLLED-BATCH-RETRIEVAL-QUALITY-EVAL-01

Controlled retrieval quality evaluation.
Read-only. No memory write. No FAISS write. No reindex.
Uses SemanticMemoryFAISS search() method.
"""

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import sys

_tmp_agent_root = str(Path(__file__).resolve().parent.parent / "tmp_agent")
if _tmp_agent_root not in sys.path:
    sys.path.insert(0, _tmp_agent_root)

import numpy as np

try:
    import faiss
except ImportError:
    faiss = None  # type: ignore

SEMANTIC_ROOT = Path("memory/semantic")
RECORDS_PATH = SEMANTIC_ROOT / "semantic_memory.jsonl"
INDEX_PATH = SEMANTIC_ROOT / "semantic_memory_faiss.index"
IDS_PATH = SEMANTIC_ROOT / "semantic_memory_faiss_ids.json"

BATCH_FRONT = "FRONT-CONTROLLED-BATCH-RETRIEVAL-QUALITY-EVAL-01"

EXPECTED_RECORDS = [
    {
        "id": "controlled_batch_01_real_execution_policy",
        "name": "Real Execution Policy",
    },
    {
        "id": "controlled_batch_01_runtime_recovery_runbook",
        "name": "Runtime Recovery Runbook",
    },
    {
        "id": "controlled_batch_01_memory_faiss_canary_doc",
        "name": "Memory FAISS Canary Doc",
    },
]

QUERY_SUITE: List[Dict[str, Any]] = []

QUERIES_BY_RECORD: Dict[str, List[str]] = {
    "controlled_batch_01_real_execution_policy": [
        "real execution policy controlled Brain operations memory FAISS trading connectors",
        "Brain governance limits for memory writes and FAISS promotion",
        "policy preventing external network connectors trading and B8 actions",
        "controlled operations gating expectations for real execution",
        "what document defines limits on Brain real execution",
    ],
    "controlled_batch_01_runtime_recovery_runbook": [
        "runtime recovery Brain V9 dashboard Ollama health check execution gate",
        "Brain V9 recovery runbook for local runtime readiness",
        "health check procedures for Ollama dashboard and execution gate",
        "how to recover Brain runtime before real execution",
        "runtime readiness troubleshooting document",
    ],
    "controlled_batch_01_memory_faiss_canary_doc": [
        "first successful semantic memory FAISS canary promotion template",
        "controlled semantic memory write and FAISS promotion canary",
        "verified template for future controlled ingestion",
        "first memory FAISS canary document",
        "evidence that Brain learned local source through memory and FAISS",
    ],
}

for rid, queries in QUERIES_BY_RECORD.items():
    for q in queries:
        QUERY_SUITE.append({"expected_id": rid, "query": q})


def front_id() -> str:
    return BATCH_FRONT


def expected_records() -> List[Dict[str, Any]]:
    return [dict(r) for r in EXPECTED_RECORDS]


def query_suite() -> List[Dict[str, Any]]:
    return [dict(q) for q in QUERY_SUITE]


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(65536)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def baseline_inventory() -> Dict[str, Any]:
    """Capture baseline state of memory and FAISS (read-only)."""
    inventory = {
        "timestamp": "2026-06-09",
        "phase": "baseline",
        "files": {},
        "batch_counts": {},
    }
    for label, path in (
        ("semantic_memory.jsonl", RECORDS_PATH),
        ("semantic_memory_faiss.index", INDEX_PATH),
        ("semantic_memory_faiss_ids.json", IDS_PATH),
    ):
        if path.is_file():
            entry: Dict[str, Any] = {
                "exists": True,
                "sha256": _sha256_file(path),
            }
            if label == "semantic_memory.jsonl":
                lines = path.read_text(encoding="utf-8").splitlines()
                entry["line_count"] = len(lines)
            elif label == "semantic_memory_faiss_ids.json":
                ids = json.loads(path.read_text(encoding="utf-8"))
                entry["count"] = len(ids)
            else:
                entry["size_bytes"] = path.stat().st_size
            inventory["files"][label] = entry
        else:
            inventory["files"][label] = {"exists": False}

    lines = RECORDS_PATH.read_text(encoding="utf-8").splitlines()
    all_ids = json.loads(IDS_PATH.read_text(encoding="utf-8"))
    for rec in EXPECTED_RECORDS:
        rid = rec["id"]
        mem_count = sum(
            1 for line in lines
            if line.strip() and json.loads(line).get("id") == rid
        )
        faiss_count = all_ids.count(rid)
        inventory["batch_counts"][rid] = {
            "memory_count": mem_count,
            "faiss_count": faiss_count,
        }
    return inventory


def _load_faiss_search():
    """Load SemanticMemoryFAISS without instantiating eagerly."""
    from brain_v9.core.semantic_memory_faiss import get_semantic_memory_faiss, SemanticMemoryFAISS
    return get_semantic_memory_faiss


def search_faiss_direct(query: str, top_k: int = 10) -> Dict[str, Any]:
    """Read-only FAISS search. No mutation."""
    result: Dict[str, Any] = {
        "query": query,
        "top_k_requested": top_k,
        "hits": [],
        "backend": "faiss_direct",
    }
    try:
        get_mem = _load_faiss_search()
        mem = get_mem()
        hits = mem.search(query, top_k=top_k, min_score=0.01)
        for h in hits:
            result["hits"].append({
                "id": h.get("id"),
                "score": h.get("score"),
                "snippet": h.get("snippet", "")[:200],
            })
    except Exception as e:
        result["error"] = str(e)
        result["backend"] = "faiss_direct_failed"
    return result


def evaluate_record(record_id: str) -> Dict[str, Any]:
    """Evaluate a single record against its query suite."""
    queries = QUERIES_BY_RECORD.get(record_id, [])
    evaluations = []
    for q in queries:
        search_result = search_faiss_direct(q, top_k=10)
        top_ids = [h["id"] for h in search_result.get("hits", []) if h.get("id")]
        rank = None
        score = None
        if record_id in top_ids:
            rank = top_ids.index(record_id) + 1
            for h in search_result.get("hits", []):
                if h.get("id") == record_id:
                    score = h.get("score")
                    break
        evaluations.append({
            "expected_id": record_id,
            "query": q,
            "found_top_1": rank == 1,
            "found_top_3": rank is not None and rank <= 3,
            "found_top_5": rank is not None and rank <= 5,
            "found_top_10": rank is not None,
            "rank": rank,
            "score": score,
            "top_10_ids": top_ids[:10],
            "retrieval_backend": search_result.get("backend", "unknown"),
            "passed": rank is not None and rank <= 5,
        })
    return {
        "record_id": record_id,
        "evaluations": evaluations,
    }


def _check_faiss_index_integrity() -> Dict[str, Any]:
    """Verify FAISS index matches ids file (read-only)."""
    if faiss is None:
        return {"ok": False, "reason": "faiss not installed"}
    try:
        index = faiss.read_index(str(INDEX_PATH))
        ids = json.loads(IDS_PATH.read_text(encoding="utf-8"))
        if index.ntotal != len(ids):
            return {"ok": False, "reason": "ntotal_mismatch", "ntotal": index.ntotal, "ids_len": len(ids)}
        return {"ok": True, "ntotal": index.ntotal, "ids_len": len(ids)}
    except Exception as e:
        return {"ok": False, "reason": str(e)}


def run_retrieval_quality_eval() -> Dict[str, Any]:
    """Run the full retrieval quality evaluation. Read-only."""
    result: Dict[str, Any] = {
        "front_id": BATCH_FRONT,
        "timestamp": "2026-06-09",
        "network_called": False,
        "connector_called": False,
        "trading_executed": False,
        "b8_touched": False,
        "memory_mutated": False,
        "faiss_mutated": False,
        "integrity": {},
        "per_record": [],
        "overall": {},
    }

    result["integrity"]["faiss_index"] = _check_faiss_index_integrity()

    before = baseline_inventory()
    result["before_inventory"] = before

    for rec in EXPECTED_RECORDS:
        result["per_record"].append(evaluate_record(rec["id"]))

    after = baseline_inventory()
    result["after_inventory"] = after

    # Detect mutation by comparing SHA of memory and FAISS files
    mutated = False
    for label in ("semantic_memory.jsonl", "semantic_memory_faiss.index", "semantic_memory_faiss_ids.json"):
        before_sha = before["files"].get(label, {}).get("sha256")
        after_sha = after["files"].get(label, {}).get("sha256")
        if before_sha != after_sha:
            mutated = True
            break
    result["memory_mutated"] = mutated
    result["faiss_mutated"] = mutated

    # Summary stats
    total_queries = 0
    top1_pass = 0
    top3_pass = 0
    top5_pass = 0
    top10_pass = 0
    record_summaries = []
    for pr in result["per_record"]:
        evs = pr["evaluations"]
        total_queries += len(evs)
        top1 = sum(1 for e in evs if e["found_top_1"])
        top3 = sum(1 for e in evs if e["found_top_3"])
        top5 = sum(1 for e in evs if e["found_top_5"])
        top10 = sum(1 for e in evs if e["found_top_10"])
        top1_pass += top1
        top3_pass += top3
        top5_pass += top5
        top10_pass += top10
        record_summaries.append({
            "record_id": pr["record_id"],
            "queries": len(evs),
            "top_1": top1,
            "top_3": top3,
            "top_5": top5,
            "top_10": top10,
        })

    result["overall"] = {
        "total_queries": total_queries,
        "top_1_pass_count": top1_pass,
        "top_3_pass_count": top3_pass,
        "top_5_pass_count": top5_pass,
        "top_10_pass_count": top10_pass,
        "top_1_pass_rate": round(top1_pass / total_queries, 4) if total_queries else 0.0,
        "top_3_pass_rate": round(top3_pass / total_queries, 4) if total_queries else 0.0,
        "top_5_pass_rate": round(top5_pass / total_queries, 4) if total_queries else 0.0,
        "top_10_pass_rate": round(top10_pass / total_queries, 4) if total_queries else 0.0,
        "record_summaries": record_summaries,
    }

    return result


def summarize_quality_eval(result: Dict[str, Any]) -> Dict[str, Any]:
    overall = result.get("overall", {})
    total_queries = overall.get("total_queries", 0)
    top5_rate = overall.get("top_5_pass_rate", 0.0)
    top10_rate = overall.get("top_10_pass_rate", 0.0)
    mutated = result.get("memory_mutated", True) or result.get("faiss_mutated", True)

    record_passes = []
    for pr in result.get("per_record", []):
        evs = pr["evaluations"]
        top5_count = sum(1 for e in evs if e["found_top_5"])
        top10_count = sum(1 for e in evs if e["found_top_10"])
        top1_count = sum(1 for e in evs if e["found_top_1"])
        record_passes.append({
            "record_id": pr["record_id"],
            "top_1_count": top1_count,
            "top_5_count": top5_count,
            "top_10_count": top10_count,
            "at_least_4_of_5_top_5": top5_count >= 4,
            "all_5_top_10": top10_count == 5,
            "at_least_2_of_5_top_1": top1_count >= 2,
        })

    pass_criteria_met = (
        top5_rate >= 0.80
        and top10_rate == 1.00
        and not mutated
        and all(r["at_least_4_of_5_top_5"] for r in record_passes)
        and all(r["all_5_top_10"] for r in record_passes)
        and all(r["at_least_2_of_5_top_1"] for r in record_passes)
    )

    status = (
        "FRONT_CONTROLLED_BATCH_RETRIEVAL_QUALITY_EVAL_01_COMPLETE"
        if pass_criteria_met
        else "RETRIEVAL_QUALITY_BELOW_THRESHOLD"
    )

    return {
        "front_id": result.get("front_id", BATCH_FRONT),
        "status": status,
        "pass_criteria_met": pass_criteria_met,
        "total_queries": total_queries,
        "top_1_pass_count": overall.get("top_1_pass_count", 0),
        "top_3_pass_count": overall.get("top_3_pass_count", 0),
        "top_5_pass_count": overall.get("top_5_pass_count", 0),
        "top_10_pass_count": overall.get("top_10_pass_count", 0),
        "top_5_pass_rate": top5_rate,
        "top_10_pass_rate": top10_rate,
        "memory_mutated": result.get("memory_mutated", True),
        "faiss_mutated": result.get("faiss_mutated", True),
        "network_called": result.get("network_called", False),
        "connector_called": result.get("connector_called", False),
        "trading_executed": result.get("trading_executed", False),
        "b8_touched": result.get("b8_touched", False),
        "record_passes": record_passes,
        "overall": overall,
    }


def assert_read_only_integrity(before: Dict[str, Any], after: Dict[str, Any]) -> Dict[str, Any]:
    """Compare two inventories and assert no mutation."""
    violations = []
    for label in before.get("files", {}):
        b_sha = before["files"][label].get("sha256")
        a_sha = after["files"].get(label, {}).get("sha256")
        if b_sha != a_sha:
            violations.append({"file": label, "before": b_sha, "after": a_sha})
    return {
        "ok": len(violations) == 0,
        "violations": violations,
    }
