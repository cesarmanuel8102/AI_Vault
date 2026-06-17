# FAISS Stack Detection

**Front**: FRONT-EXTERNAL-CURATED-LEARNING-CANARY-FAISS-PROMOTION-EXECUTE-SECURITY-GOVERNANCE-01

## Detected Stack

| Component | Value |
|-----------|-------|
| Index path | `memory/semantic/semantic_memory_faiss.index` |
| IDs path | `memory/semantic/semantic_memory_faiss_ids.json` |
| Embedding API | Ollama localhost:11434/api/embeddings |
| Model | nomic-embed-text |
| Vector dimension | 768 |
| FAISS index type | `faiss.IndexFlatIP` (cosine similarity) |
| Current ntotal | 1611 |
| Current ids count | 1611 |

## Promotion Method Selected

Use existing `SemanticMemoryFAISS._add_to_index()` from `tmp_agent/brain_v9/core/semantic_memory_faiss.py`.

This method:
- Loads index if needed
- Generates embedding via Ollama
- Adds vector to FAISS
- Appends ID
- Saves index + ids

## Verdict

FAISS stack detected safely. Proceed with mutation using canonical existing code.
