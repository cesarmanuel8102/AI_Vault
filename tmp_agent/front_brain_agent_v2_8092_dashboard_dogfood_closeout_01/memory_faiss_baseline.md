# Memory / FAISS Baseline

## Estado inicial (pre-front)
- **semantic_memory.jsonl:** 1732 líneas, sha256_prefix=5a3180593cb1ddff, size=805963 bytes
- **semantic_memory_faiss.index:** sha256_prefix=3fd44c7f45096fd2, size=5016621 bytes
- **semantic_memory_faiss_ids.json:** sha256_prefix=96c93ae79301f743, ids_count=1633
- **FAISS ntotal:** 1633
- **Estado:** ✅ Aligned (ids_count == ntotal)

## Nota de seguridad
Se detectaron y revirtieron 2 entradas no autorizadas (agent_loop) en semantic_memory.jsonl antes de este front. Estado actual limpio.

## Veredicto
Baseline estable. Sin mutaciones durante este front.
