"""
Apply correction to canonical semantic memory:
- Remove last 3 task_result records (lines 1727-1729)
- Keep 6 codex_training_lesson records (lines 1721-1726)
- Rebuild FAISS from corrected semantic memory
"""
import json, sys
from pathlib import Path
sys.path.insert(0, "tmp_agent")

from brain_v9.core.semantic_memory_faiss import get_semantic_memory_faiss, SemanticMemoryFAISS

SEMANTIC_PATH = Path("memory/semantic/semantic_memory.jsonl")

# Step 1: Read current semantic memory
with SEMANTIC_PATH.open("r", encoding="utf-8") as f:
    lines = f.readlines()

print(f"Current lines: {len(lines)}")

# Step 2: Remove last 3 lines (task_result records)
kept_lines = lines[:-3]
removed_count = len(lines) - len(kept_lines)

print(f"Removed {removed_count} task_result records")
print(f"Kept lines: {len(kept_lines)}")

# Step 3: Write corrected semantic memory
with SEMANTIC_PATH.open("w", encoding="utf-8") as f:
    f.writelines(kept_lines)

# Step 4: Verify written file
with SEMANTIC_PATH.open("r", encoding="utf-8") as f:
    verify_lines = f.readlines()

assert len(verify_lines) == 1726, f"Expected 1726, got {len(verify_lines)}"
print(f"Verified: {len(verify_lines)} lines in corrected semantic_memory.jsonl")

# Step 5: Rebuild FAISS from corrected semantic memory
mem = get_semantic_memory_faiss()
print("Rebuilding FAISS index from corrected semantic memory...")
result = mem.rebuild_index(show_progress=True)
print(f"Rebuild result: {result}")

# Step 6: Verify FAISS consistency
assert result["records"] == 1726, f"Expected 1726 records, got {result['records']}"
assert mem._index.ntotal == 1627, f"Expected 1627 vectors, got {mem._index.ntotal}"
assert len(mem._ids) == 1627, f"Expected 1627 IDs, got {len(mem._ids)}"

print("CORRECTION_APPLIED_OK")
print(f"Final semantic_lines: {result['records']}")
print(f"Final faiss_ids: {len(mem._ids)}")
print(f"Final faiss_ntotal: {mem._index.ntotal}")
