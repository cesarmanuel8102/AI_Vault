"""
Semantic Memory V2 - FAISS backend con embeddings reales de Ollama.

Migración del sistema de memoria semántica:
- Backend: FAISS (CPU) en lugar de numpy hashing
- Embeddings: Ollama API (llama3.1:8b) - 4096 dims, embeddings neuronales reales
- Compatibilidad: Misma API pública que SemanticMemory original

Uso:
    from brain_v9.core.semantic_memory_faiss import get_semantic_memory_faiss
    mem = get_semantic_memory_faiss()
    mem.search("concepto trading")
"""
from __future__ import annotations

import hashlib
import json
import logging
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional
import urllib.request
import urllib.error

import numpy as np

try:
    import faiss
    FAISS_AVAILABLE = True
except ImportError:
    FAISS_AVAILABLE = False

from brain_v9.config import BASE_PATH, STATE_PATH

log = logging.getLogger("semantic_memory_faiss")

# Configuración
SEMANTIC_ROOT = BASE_PATH / "memory" / "semantic"
RECORDS_PATH = SEMANTIC_ROOT / "semantic_memory.jsonl"
FAISS_INDEX_PATH = SEMANTIC_ROOT / "semantic_memory_faiss.index"
FAISS_IDS_PATH = SEMANTIC_ROOT / "semantic_memory_faiss_ids.json"
STATUS_PATH = STATE_PATH / "semantic_memory_status.json"

OLLAMA_URL = "http://localhost:11434"
EMBEDDING_MODEL = "nomic-embed-text"  # Modelo rápido de embeddings
EMBEDDING_DIMS = 768  # nomic-embed-text genera 768 dims

# Throttle global para Ollama embeddings: limita concurrencia para evitar
# saturar el servidor (causaba ConnectionResetError bajo carga).
_OLLAMA_MAX_CONCURRENT = 2
_OLLAMA_SEMAPHORE = threading.BoundedSemaphore(_OLLAMA_MAX_CONCURRENT)
# Cache LRU simple por hash de texto para evitar recomputar embeddings.
_EMBED_CACHE: Dict[str, np.ndarray] = {}
_EMBED_CACHE_MAX = 512
_EMBED_CACHE_LOCK = threading.Lock()


@dataclass
class SemanticRecord:
    id: str
    created_utc: str
    source: str
    session_id: str
    kind: str
    text: str
    metadata: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "created_utc": self.created_utc,
            "source": self.source,
            "session_id": self.session_id,
            "kind": self.kind,
            "text": self.text,
            "metadata": self.metadata,
        }


class SemanticMemoryFAISS:
    """
    Memoria semántica con FAISS + embeddings reales de Ollama.
    API compatible con SemanticMemory original.
    """

    def __init__(
        self,
        root: Path | None = None,
        dims: int = EMBEDDING_DIMS,
        ollama_url: str = OLLAMA_URL,
        model: str = EMBEDDING_MODEL,
    ):
        self.root = Path(root or SEMANTIC_ROOT)
        self.records_path = self.root / RECORDS_PATH.name
        self.index_path = self.root / "semantic_memory_faiss.index"
        self.ids_path = self.root / "semantic_memory_faiss_ids.json"
        self.status_path = STATUS_PATH
        self.dims = int(dims)
        self.ollama_url = ollama_url
        self.model = model
        self.root.mkdir(parents=True, exist_ok=True)
        self.status_path.parent.mkdir(parents=True, exist_ok=True)
        
        # FAISS index (lazy load)
        self._index: Optional[faiss.IndexFlatIP] = None
        self._ids: List[str] = []
        
        if not FAISS_AVAILABLE:
            raise RuntimeError("FAISS not installed. Run: pip install faiss-cpu")

    def status(self) -> Dict[str, Any]:
        records = self._read_records()
        ollama_ok = self._check_ollama()
        status = {
            "ok": FAISS_AVAILABLE and ollama_ok,
            "backend": "faiss_ollama_embeddings",
            "backend_class": "SemanticMemoryFAISS",
            "dims": self.dims,
            "records": len(records),
            "root": str(self.root),
            "records_path": str(self.records_path),
            "index_path": str(self.index_path),
            "index_exists": self.index_path.exists(),
            "faiss_available": FAISS_AVAILABLE,
            "ollama_available": ollama_ok,
            "embedding_model": self.model,
            "embedding_dims": self.dims,
            "improvements": [
                "Embeddings neuronales reales via Ollama (no hashing)",
                "FAISS IndexFlatIP para búsqueda por similitud coseno",
                "Mejor recall semántico para conceptos relacionados",
            ],
            "updated_utc": self._utc_now(),
        }
        self._write_status(status)
        return status

    def _check_ollama(self) -> bool:
        """Verifica que Ollama esté disponible."""
        try:
            req = urllib.request.Request(f"{self.ollama_url}/api/tags", method="GET")
            with urllib.request.urlopen(req, timeout=5) as resp:
                return resp.status == 200
        except Exception:
            return False

    def embed_text(self, text: str) -> np.ndarray:
        """Genera embedding real usando Ollama API. Throttled + cached."""
        text = (text or "").strip()[:8000]  # Limitar longitud
        if not text:
            return np.zeros(self.dims, dtype=np.float32)

        # Cache hit por hash exacto del texto
        cache_key = hashlib.sha256(text.encode("utf-8")).hexdigest()
        with _EMBED_CACHE_LOCK:
            cached = _EMBED_CACHE.get(cache_key)
            if cached is not None:
                return cached

        # Throttle: limita concurrencia a Ollama (evita ConnectionResetError bajo carga)
        acquired = _OLLAMA_SEMAPHORE.acquire(timeout=20)
        if not acquired:
            log.warning("Ollama semaphore timeout (>20s), returning zero vector")
            return np.zeros(self.dims, dtype=np.float32)
        try:
            payload = json.dumps({"model": self.model, "prompt": text}).encode("utf-8")
            req = urllib.request.Request(
                f"{self.ollama_url}/api/embeddings",
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                embedding = data.get("embedding", [])
                if len(embedding) != self.dims:
                    log.warning(f"Embedding dims mismatch: got {len(embedding)}, expected {self.dims}")
                    if len(embedding) < self.dims:
                        embedding.extend([0.0] * (self.dims - len(embedding)))
                    else:
                        embedding = embedding[:self.dims]
                vec = np.array(embedding, dtype=np.float32)
                norm = np.linalg.norm(vec)
                if norm > 0:
                    vec /= norm
                # Almacenar en cache (evict simple si lleno)
                with _EMBED_CACHE_LOCK:
                    if len(_EMBED_CACHE) >= _EMBED_CACHE_MAX:
                        # Drop ~10% mas antiguos (FIFO simple)
                        for k in list(_EMBED_CACHE.keys())[: max(1, _EMBED_CACHE_MAX // 10)]:
                            _EMBED_CACHE.pop(k, None)
                    _EMBED_CACHE[cache_key] = vec
                return vec
        except Exception as e:
            log.error(f"Ollama embedding failed: {e}")
            return np.zeros(self.dims, dtype=np.float32)
        finally:
            _OLLAMA_SEMAPHORE.release()

    def embed_batch(self, texts: List[str], show_progress: bool = True) -> np.ndarray:
        """Genera embeddings para múltiples textos."""
        vectors = []
        total = len(texts)
        for i, text in enumerate(texts):
            if show_progress and (i % 50 == 0 or i == total - 1):
                log.info(f"Embedding {i+1}/{total}...")
            vectors.append(self.embed_text(text))
        return np.vstack(vectors).astype(np.float32)

    def ingest_text(
        self,
        text: str,
        source: str = "manual",
        session_id: str = "default",
        kind: str = "note",
        metadata: Optional[Dict[str, Any]] = None,
        rebuild: bool = True,
    ) -> Dict[str, Any]:
        clean = (text or "").strip()
        if not clean:
            return {"ok": False, "error": "empty_text"}

        metadata = dict(metadata or {})
        digest = hashlib.sha256(
            json.dumps({"source": source, "session_id": session_id, "kind": kind, "text": clean}, 
                      ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest()
        record_id = digest[:24]

        if self._record_exists(record_id):
            return {"ok": True, "inserted": False, "id": record_id, "reason": "duplicate"}

        record = SemanticRecord(
            id=record_id,
            created_utc=self._utc_now(),
            source=source,
            session_id=session_id,
            kind=kind,
            text=clean,
            metadata=metadata,
        )
        with self.records_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record.to_dict(), ensure_ascii=False, sort_keys=True) + "\n")

        if rebuild:
            # Añadir solo este vector al índice (incremental)
            self._add_to_index(record_id, clean)
        return {"ok": True, "inserted": True, "id": record_id, "records": len(self._read_records())}

    def _add_to_index(self, record_id: str, text: str) -> None:
        """Añade un vector al índice FAISS (incremental)."""
        self._ensure_index_loaded()
        vec = self.embed_text(text).reshape(1, -1)
        self._index.add(vec)
        self._ids.append(record_id)
        self._save_index()

    def search(
        self,
        query: str,
        top_k: int = 5,
        min_score: float = 0.1,
        max_age_hours: Optional[float] = None,
    ) -> List[Dict[str, Any]]:
        """Búsqueda semántica usando FAISS."""
        if not (query or "").strip():
            return []
        
        self._ensure_index_loaded()
        if self._index is None or self._index.ntotal == 0:
            return []
        
        # Embedding de la query
        qvec = self.embed_text(query).reshape(1, -1)
        
        # Búsqueda FAISS
        k = min(top_k, self._index.ntotal)
        scores, indices = self._index.search(qvec, k)
        
        # Cargar records para metadata
        records = self._read_records()
        id_to_record = {str(r.get("id")): r for r in records}
        
        results: List[Dict[str, Any]] = []
        for score, idx in zip(scores[0], indices[0]):
            if idx < 0 or idx >= len(self._ids):
                continue
            if score < min_score:
                continue
            record_id = self._ids[idx]
            rec = id_to_record.get(record_id)
            if not rec:
                continue
            age_hours = self._record_age_hours(rec)
            if max_age_hours is not None and age_hours is not None and age_hours > max_age_hours:
                continue
            text = str(rec.get("text", ""))
            results.append({
                "id": rec.get("id"),
                "score": round(float(score), 4),
                "source": rec.get("source"),
                "session_id": rec.get("session_id"),
                "kind": rec.get("kind"),
                "created_utc": rec.get("created_utc"),
                "age_hours": round(age_hours, 2) if age_hours is not None else None,
                "snippet": text[:700],
                "metadata": rec.get("metadata", {}),
            })
        return results

    def format_hits_for_prompt(self, hits: List[Dict[str, Any]]) -> str:
        if not hits:
            return ""
        lines = ["MEMORIA SEMANTICA HISTORICA (FAISS, usar solo como contexto y no como estado actual):"]
        for hit in hits:
            snippet = str(hit.get("snippet", "")).replace("\n", " ")[:500]
            age = hit.get("age_hours")
            age_txt = f", age_h={age}" if age is not None else ""
            lines.append(f"- score={hit.get('score')} source={hit.get('source')} kind={hit.get('kind')}{age_txt}: {snippet}")
        return "\n".join(lines)

    def rebuild_index(self, show_progress: bool = True) -> Dict[str, Any]:
        """Reconstruye el índice FAISS completo desde los records."""
        records = self._read_records()
        if not records:
            self._index = faiss.IndexFlatIP(self.dims)
            self._ids = []
            self._save_index()
            return {"ok": True, "records": 0, "index_path": str(self.index_path)}
        
        log.info(f"Rebuilding FAISS index with {len(records)} records...")
        texts = [str(r.get("text", "")) for r in records]
        ids = [str(r.get("id")) for r in records]
        
        # Generar embeddings (esto toma tiempo)
        vectors = self.embed_batch(texts, show_progress=show_progress)
        
        # Crear índice FAISS
        self._index = faiss.IndexFlatIP(self.dims)
        self._index.add(vectors)
        self._ids = ids
        
        self._save_index()
        status = self.status()
        log.info(f"FAISS index rebuilt: {len(records)} vectors")
        return {"ok": True, "records": len(records), "index_path": str(self.index_path), "status": status}

    def compact(
        self,
        *,
        max_age_hours: Optional[float] = 24.0 * 30.0 * 6.0,
        keep_recent: int = 250,
        dry_run: bool = True,
    ) -> Dict[str, Any]:
        records = self._read_records()
        total_before = len(records)
        keep_recent = max(0, int(keep_recent))
        recent_threshold = max(0, total_before - keep_recent)
        removal_reasons: Dict[str, int] = {"duplicate_exact": 0, "stale_age": 0}
        seen_keys = set()
        keep_flags = [True] * total_before

        for idx in range(total_before - 1, -1, -1):
            rec = records[idx]
            key = self._record_dedupe_key(rec)
            if key in seen_keys:
                keep_flags[idx] = False
                removal_reasons["duplicate_exact"] += 1
                continue
            seen_keys.add(key)

            if idx >= recent_threshold:
                continue

            age_hours = self._record_age_hours(rec)
            if max_age_hours is not None and age_hours is not None and age_hours > max_age_hours:
                keep_flags[idx] = False
                removal_reasons["stale_age"] += 1

        compacted = [rec for idx, rec in enumerate(records) if keep_flags[idx]]
        report = {
            "ok": True,
            "dry_run": dry_run,
            "before": self._memory_stats(records),
            "after": self._memory_stats(compacted),
            "removed_total": total_before - len(compacted),
            "removal_reasons": removal_reasons,
            "keep_recent": keep_recent,
            "max_age_hours": max_age_hours,
        }

        if not dry_run:
            self.records_path.parent.mkdir(parents=True, exist_ok=True)
            with self.records_path.open("w", encoding="utf-8") as fh:
                for record in compacted:
                    fh.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
            self.rebuild_index(show_progress=False)
        return report

    def _ensure_index_loaded(self) -> None:
        """Carga el índice FAISS si existe, o lo crea vacío."""
        if self._index is not None:
            return
        
        if self.index_path.exists() and self.ids_path.exists():
            try:
                self._index = faiss.read_index(str(self.index_path))
                self._ids = json.loads(self.ids_path.read_text(encoding="utf-8"))
                log.info(f"Loaded FAISS index: {self._index.ntotal} vectors")
                return
            except Exception as e:
                log.warning(f"Failed to load FAISS index: {e}")
        
        # Crear índice vacío
        self._index = faiss.IndexFlatIP(self.dims)
        self._ids = []

    def _save_index(self) -> None:
        """Guarda el índice FAISS a disco."""
        if self._index is None:
            return
        try:
            faiss.write_index(self._index, str(self.index_path))
            self.ids_path.write_text(json.dumps(self._ids), encoding="utf-8")
        except Exception as e:
            log.error(f"Failed to save FAISS index: {e}")

    def _read_records(self) -> List[Dict[str, Any]]:
        if not self.records_path.exists():
            return []
        records: List[Dict[str, Any]] = []
        for line in self.records_path.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except Exception:
                continue
        return records

    def _record_exists(self, record_id: str) -> bool:
        return any(str(r.get("id")) == record_id for r in self._read_records())

    def _write_status(self, status: Dict[str, Any]) -> None:
        try:
            self.status_path.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass

    @staticmethod
    def _record_age_hours(record: Dict[str, Any]) -> Optional[float]:
        created = record.get("created_utc")
        if not created:
            return None
        try:
            ts = datetime.fromisoformat(str(created).replace("Z", "+00:00")).astimezone(timezone.utc)
            delta = datetime.now(timezone.utc) - ts
            return delta.total_seconds() / 3600.0
        except Exception:
            return None

    @staticmethod
    def _record_dedupe_key(record: Dict[str, Any]) -> tuple[str, str, str]:
        text = " ".join(str(record.get("text", "")).strip().lower().split())
        return (
            str(record.get("source", "")).strip().lower(),
            str(record.get("kind", "")).strip().lower(),
            text,
        )

    def _memory_stats(self, records: List[Dict[str, Any]]) -> Dict[str, Any]:
        duplicate_keys = set()
        seen_keys = set()
        oldest_age: Optional[float] = None
        newest_age: Optional[float] = None
        by_kind: Dict[str, int] = {}
        for rec in records:
            key = self._record_dedupe_key(rec)
            if key in seen_keys:
                duplicate_keys.add(key)
            else:
                seen_keys.add(key)
            kind = str(rec.get("kind", "unknown"))
            by_kind[kind] = by_kind.get(kind, 0) + 1
            age = self._record_age_hours(rec)
            if age is not None:
                oldest_age = age if oldest_age is None or age > oldest_age else oldest_age
                newest_age = age if newest_age is None or age < newest_age else newest_age
        return {
            "records": len(records),
            "duplicate_exact_count": len(duplicate_keys),
            "oldest_age_hours": round(oldest_age, 2) if oldest_age is not None else None,
            "newest_age_hours": round(newest_age, 2) if newest_age is not None else None,
            "by_kind": by_kind,
            "root": str(self.root),
        }

    @staticmethod
    def _utc_now() -> str:
        return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


# Singleton
_MEM_FAISS: Optional[SemanticMemoryFAISS] = None

def get_semantic_memory_faiss() -> SemanticMemoryFAISS:
    global _MEM_FAISS
    if _MEM_FAISS is None:
        _MEM_FAISS = SemanticMemoryFAISS()
    return _MEM_FAISS


def migrate_to_faiss(show_progress: bool = True) -> Dict[str, Any]:
    """
    Migra la memoria semántica existente a FAISS.
    Lee los records existentes y reconstruye el índice con embeddings reales.
    """
    mem = get_semantic_memory_faiss()
    records_count = len(mem._read_records())
    
    if records_count == 0:
        return {"ok": True, "message": "No records to migrate", "records": 0}
    
    log.info(f"Starting migration of {records_count} records to FAISS...")
    result = mem.rebuild_index(show_progress=show_progress)
    
    return {
        "ok": result.get("ok", False),
        "message": f"Migrated {records_count} records to FAISS with Ollama embeddings",
        "records": records_count,
        "index_path": str(mem.index_path),
        "embedding_model": mem.model,
        "embedding_dims": mem.dims,
    }
