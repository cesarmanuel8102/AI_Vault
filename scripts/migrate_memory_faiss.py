#!/usr/bin/env python
"""
Script de migración incremental a FAISS.
Procesa en batches de 100 y guarda progreso.
Puede reiniciarse sin perder trabajo.
"""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, "C:/AI_VAULT/tmp_agent")

import numpy as np
import faiss
import urllib.request

# Config
SEMANTIC_ROOT = Path("C:/AI_VAULT/memory/semantic")
RECORDS_PATH = SEMANTIC_ROOT / "semantic_memory.jsonl"
INDEX_PATH = SEMANTIC_ROOT / "semantic_memory_faiss.index"
IDS_PATH = SEMANTIC_ROOT / "semantic_memory_faiss_ids.json"
PROGRESS_PATH = SEMANTIC_ROOT / "migration_progress.json"

OLLAMA_URL = "http://localhost:11434"
MODEL = "nomic-embed-text"
DIMS = 768
BATCH_SIZE = 100


def embed_text(text: str) -> np.ndarray:
    """Genera embedding usando Ollama."""
    text = (text or "").strip()[:4000]
    if not text:
        return np.zeros(DIMS, dtype=np.float32)
    
    payload = json.dumps({"model": MODEL, "prompt": text}).encode("utf-8")
    req = urllib.request.Request(
        f"{OLLAMA_URL}/api/embeddings",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode("utf-8"))
        vec = np.array(data.get("embedding", []), dtype=np.float32)
        if len(vec) != DIMS:
            vec = np.zeros(DIMS, dtype=np.float32)
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec /= norm
        return vec


def load_records():
    records = []
    for line in RECORDS_PATH.read_text(encoding="utf-8", errors="ignore").splitlines():
        if line.strip():
            try:
                records.append(json.loads(line))
            except:
                pass
    return records


def load_progress():
    if PROGRESS_PATH.exists():
        return json.loads(PROGRESS_PATH.read_text())
    return {"processed": 0, "ids": [], "vectors_file": None}


def save_progress(processed, ids):
    PROGRESS_PATH.write_text(json.dumps({
        "processed": processed,
        "ids": ids,
        "updated": time.strftime("%Y-%m-%d %H:%M:%S"),
    }))


def migrate():
    print("=== Migración a FAISS con nomic-embed-text ===")
    
    records = load_records()
    total = len(records)
    print(f"Total records: {total}")
    
    progress = load_progress()
    start_idx = progress["processed"]
    all_ids = progress.get("ids", [])
    
    if start_idx >= total:
        print("Migration already complete!")
        return
    
    print(f"Resuming from index {start_idx}")
    
    # Cargar vectores existentes o crear nuevo
    if INDEX_PATH.exists() and start_idx > 0:
        index = faiss.read_index(str(INDEX_PATH))
        print(f"Loaded existing index with {index.ntotal} vectors")
    else:
        index = faiss.IndexFlatIP(DIMS)
        all_ids = []
        print("Created new FAISS index")
    
    # Procesar en batches
    batch_vectors = []
    batch_ids = []
    
    for i in range(start_idx, total):
        rec = records[i]
        text = str(rec.get("text", ""))
        rec_id = str(rec.get("id", f"rec_{i}"))
        
        vec = embed_text(text)
        batch_vectors.append(vec)
        batch_ids.append(rec_id)
        
        # Guardar batch
        if len(batch_vectors) >= BATCH_SIZE or i == total - 1:
            vectors = np.vstack(batch_vectors).astype(np.float32)
            index.add(vectors)
            all_ids.extend(batch_ids)
            
            # Persistir
            faiss.write_index(index, str(INDEX_PATH))
            IDS_PATH.write_text(json.dumps(all_ids))
            save_progress(i + 1, all_ids)
            
            print(f"Processed {i + 1}/{total} ({100*(i+1)//total}%)")
            
            batch_vectors = []
            batch_ids = []
    
    print(f"\n=== Migration complete! ===")
    print(f"Index: {INDEX_PATH}")
    print(f"Vectors: {index.ntotal}")
    print(f"Dims: {DIMS}")


if __name__ == "__main__":
    migrate()
