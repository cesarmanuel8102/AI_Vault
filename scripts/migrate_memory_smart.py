#!/usr/bin/env python
"""
Migración inteligente a FAISS - solo records importantes.
Reduce 1500 records a ~300 más valiosos.
"""
import json
import sys
import time
import hashlib
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

OLLAMA_URL = "http://localhost:11434"
MODEL = "nomic-embed-text"
DIMS = 768


def embed_text(text: str, retries: int = 3) -> np.ndarray:
    text = (text or "").strip()[:1500]  # Shorter = faster
    if not text:
        return np.zeros(DIMS, dtype=np.float32)
    
    for attempt in range(retries):
        try:
            payload = json.dumps({"model": MODEL, "prompt": text}).encode("utf-8")
            req = urllib.request.Request(
                f"{OLLAMA_URL}/api/embeddings",
                data=payload,
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                vec = np.array(data.get("embedding", []), dtype=np.float32)
                if len(vec) != DIMS:
                    return np.zeros(DIMS, dtype=np.float32)
                norm = np.linalg.norm(vec)
                if norm > 0:
                    vec /= norm
                return vec
        except Exception as e:
            if attempt < retries - 1:
                time.sleep(2 ** attempt)  # Backoff
                continue
            print(f"  [WARN] Embedding failed after {retries} attempts: {e}")
            return np.zeros(DIMS, dtype=np.float32)


def load_records():
    records = []
    for line in RECORDS_PATH.read_text(encoding="utf-8", errors="ignore").splitlines():
        if line.strip():
            try:
                records.append(json.loads(line))
            except:
                pass
    return records


def select_important_records(records, max_count=300):
    """Selecciona los records más importantes."""
    priority = {
        'task_result': 1,
        'error': 2,
        'project_context': 3,
        'implementation_note': 4,
        'session_fragment': 5,
    }
    
    # Sort by priority
    sorted_recs = sorted(records, key=lambda r: priority.get(r.get('kind', 'session_fragment'), 5))
    
    # Take high priority records
    selected = []
    seen_hashes = set()
    
    for rec in sorted_recs:
        text = str(rec.get('text', ''))[:500]
        text_hash = hashlib.md5(text.encode()).hexdigest()[:8]
        
        # Skip near-duplicates
        if text_hash in seen_hashes:
            continue
        seen_hashes.add(text_hash)
        
        selected.append(rec)
        if len(selected) >= max_count:
            break
    
    return selected


PROGRESS_PATH = SEMANTIC_ROOT / "smart_migration_progress.json"

def load_progress():
    if PROGRESS_PATH.exists():
        return json.loads(PROGRESS_PATH.read_text())
    return {"processed": 0}

def save_progress(processed):
    PROGRESS_PATH.write_text(json.dumps({"processed": processed, "updated": time.strftime("%Y-%m-%d %H:%M:%S")}))

def migrate():
    print("=== Smart Migration to FAISS ===")
    
    all_records = load_records()
    print(f"Total records: {len(all_records)}")
    
    records = select_important_records(all_records, max_count=300)
    print(f"Selected important: {len(records)}")
    
    # Load existing progress
    progress = load_progress()
    start_idx = progress["processed"]
    
    # Load or create index
    if INDEX_PATH.exists() and start_idx > 0:
        index = faiss.read_index(str(INDEX_PATH))
        all_ids = json.loads(IDS_PATH.read_text()) if IDS_PATH.exists() else []
        print(f"Resuming from {start_idx}, index has {index.ntotal} vectors")
    else:
        index = faiss.IndexFlatIP(DIMS)
        all_ids = []
        start_idx = 0
    
    for i in range(start_idx, len(records)):
        rec = records[i]
        text = str(rec.get("text", ""))
        rec_id = str(rec.get("id", f"rec_{i}"))
        
        vec = embed_text(text)
        index.add(vec.reshape(1, -1))
        all_ids.append(rec_id)
        
        # Save every 10 records
        if (i + 1) % 10 == 0 or i == len(records) - 1:
            faiss.write_index(index, str(INDEX_PATH))
            IDS_PATH.write_text(json.dumps(all_ids))
            save_progress(i + 1)
            print(f"Progress: {i + 1}/{len(records)} ({100*(i+1)//len(records)}%)")
    
    print(f"\n=== Done! ===")
    print(f"Indexed: {index.ntotal} vectors")
    print(f"Index: {INDEX_PATH}")


if __name__ == "__main__":
    migrate()
