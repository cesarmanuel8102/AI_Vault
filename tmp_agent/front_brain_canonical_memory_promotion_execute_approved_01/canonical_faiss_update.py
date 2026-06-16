"""
Update canonical FAISS with the 5 newly appended records.
Assumes semantic_memory.jsonl already has the new records appended.
"""
import json, sys
from pathlib import Path
sys.path.insert(0, "tmp_agent")

import numpy as np
from brain_v9.core.semantic_memory_faiss import get_semantic_memory_faiss, SemanticMemoryFAISS

mem = get_semantic_memory_faiss()
mem._ensure_index_loaded()

assert mem._index is not None, "FAISS index not loaded"
assert mem._index.ntotal == 1616, f"Expected 1616, got {mem._index.ntotal}"
assert len(mem._ids) == 1616, f"Expected 1616 ids, got {len(mem._ids)}"

records = []
with open("tmp_agent/front_brain_canonical_memory_promotion_execute_approved_01/new_records_to_append.jsonl",encoding="utf-8") as f:
    for line in f:
        line=line.strip()
        if not line:
            continue
        records.append(json.loads(line))

print(f"Adding {len(records)} vectors to canonical FAISS")

for rec in records:
    text = rec.get("text","").strip()
    if not text:
        print(f"SKIP: empty text for {rec['id']}")
        continue
    vec = mem.embed_text(text).reshape(1, -1)
    mem._index.add(vec)
    mem._ids.append(rec["id"])
    print(f"ADDED: {rec['id']} ntotal={mem._index.ntotal} ids={len(mem._ids)}")

mem._save_index()

print(f"Final canonical ntotal: {mem._index.ntotal}")
print(f"Final canonical ids count: {len(mem._ids)}")

assert mem._index.ntotal == 1621, f"Expected 1621, got {mem._index.ntotal}"
assert len(mem._ids) == 1621, f"Expected 1621 ids, got {len(mem._ids)}"

print("CANONICAL_FAISS_UPDATE_OK")
