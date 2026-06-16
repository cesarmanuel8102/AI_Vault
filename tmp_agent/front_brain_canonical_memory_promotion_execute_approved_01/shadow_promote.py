"""
Shadow canonical promotion script.
Appends approved records to shadow semantic_memory.jsonl and updates shadow FAISS.
"""
import json, hashlib, os, sys, time
from pathlib import Path
import numpy as np

# Add tmp_agent to path for semantic_memory_faiss
_tmp_agent_root = str(Path(__file__).resolve().parent.parent.parent / "tmp_agent")
if _tmp_agent_root not in sys.path:
    sys.path.insert(0, _tmp_agent_root)

from brain_v9.core.semantic_memory_faiss import get_semantic_memory_faiss, SemanticMemoryFAISS

SHADOW_ROOT = Path("tmp_agent/front_brain_canonical_memory_promotion_execute_approved_01/shadow")
RECORDS_PATH = SHADOW_ROOT / "semantic_memory.jsonl"
INDEX_PATH = SHADOW_ROOT / "semantic_memory_faiss.index"
IDS_PATH = SHADOW_ROOT / "semantic_memory_faiss_ids.json"

mem = SemanticMemoryFAISS(
    root=SHADOW_ROOT,
    dims=768,
    ollama_url="http://localhost:11434",
    model="nomic-embed-text"
)

records = []
with open("tmp_agent/front_brain_canonical_memory_promotion_execute_approved_01/dry_run_promotion_records.jsonl","r",encoding="utf-8") as f:
    for line in f:
        line=line.strip()
        if not line:
            continue
        records.append(json.loads(line))

print(f"Records to promote: {len(records)}")

for rec in records:
    print(f"Promoting: {rec['id']}")
    result = mem.ingest_text(
        text=rec["summary"],
        source="canonical_memory_promotion",
        session_id="FRONT-BRAIN-CANONICAL-MEMORY-PROMOTION-EXECUTE-APPROVED-01",
        kind="canonical_promoted",
        metadata=rec,
    )
    print(f"  result: {result}")
    if not result.get("ok"):
        print(f"FAILED: {result}")
        sys.exit(1)
    # Small delay to not overwhelm Ollama
    time.sleep(0.2)

print("All records promoted to shadow.")
print(f"Final records: {len(mem._read_records())}")
print(f"Final ntotal: {mem._index.ntotal}")
print(f"Final ids count: {len(mem._ids)}")

# Sanity checks
assert len(mem._read_records()) == 1720, f"Expected 1720, got {len(mem._read_records())}"
assert mem._index.ntotal == 1621, f"Expected 1621, got {mem._index.ntotal}"
assert len(mem._ids) == 1621, f"Expected 1621, got {len(mem._ids)}"

# Search sanity check for newly promoted records
for rec in records:
    hits = mem.search(rec["summary"], top_k=5)
    ids_hit = [h.get("id") for h in hits]
    if rec["id"] not in ids_hit:
        print(f"WARNING: {rec['id']} not found in search hits")
    else:
        print(f"OK: {rec['id']} retrievable")

print("SHADOW_VALIDATION_OK")
