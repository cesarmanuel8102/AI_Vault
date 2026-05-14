"""
INFORMATION_CURATOR.PY — Pipeline de ingesta curada general

Extiende la ingesta existente (solo GitHub repos) a un pipeline general que:
1. Acepta texto, archivos, y URLs como fuentes
2. Limpia y normaliza contenido
3. Deduplica por SHA-256
4. Clasifica por topic (7 categorías)
5. Calcula calidad del contenido
6. Detecta contradicciones con conocimiento existente
7. Deprecación automática >30 días sin validación

Reemplaza el grep de archivos locales como "investigación" con un pipeline
estructurado de curación.
"""

import hashlib
import json
import logging
import os
import re
import time
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Any, Tuple
from enum import Enum
from pathlib import Path

log = logging.getLogger("information_curator")


class ContentTopic(str, Enum):
    FINANCE = "finance"
    TRADING = "trading"
    TECHNOLOGY = "technology"
    AI_ML = "ai_ml"
    RISK_MANAGEMENT = "risk_management"
    ARCHITECTURE = "architecture"
    GENERAL = "general"


class QualityLevel(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    UNRELIABLE = "unreliable"


@dataclass
class CuratedRecord:
    """Registro de información curada."""
    record_id: str
    content: str
    topic: ContentTopic
    quality: QualityLevel
    quality_score: float  # 0.0 - 1.0
    source: str
    content_hash: str
    ingested_at: float = field(default_factory=time.time)
    validated_at: Optional[float] = None
    deprecated: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)


DEPRECATION_DAYS = 30

# Negation pairs for contradiction detection
NEGATION_PAIRS = [
    ("debe", "no debe"),
    ("puede", "no puede"),
    ("es necesario", "no es necesario"),
    ("es posible", "no es posible"),
    ("recomiendo", "no recomiendo"),
    ("correcto", "incorrecto"),
    ("seguro", "inseguro"),
    ("válido", "inválido"),
    ("should", "should not"),
    ("can", "cannot"),
    ("is", "is not"),
    ("true", "false"),
]


class InformationCurator:
    """
    Pipeline de ingesta curada de información.

    Diferencia con el sistema anterior:
    - ANTES: solo GitHub repos, sin validación, sin detección de contradicciones
    - AHORA: pipeline completo con limpieza, deduplicación, clasificación,
             calidad, detección de contradicciones, y deprecación automática
    """

    def __init__(self, storage_path: str = None):
        self.storage_path = storage_path
        self._records: Dict[str, CuratedRecord] = {}
        self._hash_index: Dict[str, str] = {}  # hash -> record_id

        # Load existing records if storage path provided
        if storage_path and os.path.exists(storage_path):
            self._load_records()

    def ingest_text(self, text: str, source: str = "manual",
                     topic: ContentTopic = None) -> CuratedRecord:
        """
        Ingesta texto a través del pipeline completo.

        Pipeline: limpiar → deduplicar → clasificar → evaluar calidad
                  → detectar contradicciones → almacenar
        """
        # 1. Limpiar
        cleaned = self._clean_text(text)
        if not cleaned or len(cleaned) < 10:
            return self._error_record("Contenido demasiado corto o vacío", source)

        # 2. Deduplicar
        content_hash = self._compute_hash(cleaned)
        if content_hash in self._hash_index:
            existing_id = self._hash_index[content_hash]
            return self._records[existing_id]

        # 3. Clasificar topic
        if topic is None:
            topic = self._classify_topic(cleaned)

        # 4. Evaluar calidad
        quality_score = self._evaluate_quality(cleaned, source)
        quality = self._quality_from_score(quality_score)

        # 5. Detectar contradicciones
        contradictions = self._detect_contradictions(cleaned, topic)

        # 6. Crear registro
        record_id = f"rec_{int(time.time())}_{hashlib.md5(cleaned[:50].encode()).hexdigest()[:8]}"
        record = CuratedRecord(
            record_id=record_id,
            content=cleaned,
            topic=topic,
            quality=quality,
            quality_score=quality_score,
            source=source,
            content_hash=content_hash,
            metadata={
                "contradictions_with": contradictions,
                "original_length": len(text),
                "cleaned_length": len(cleaned),
            },
        )

        # 7. Almacenar
        self._records[record_id] = record
        self._hash_index[content_hash] = record_id

        # 8. Persistir si hay storage
        if self.storage_path:
            self._save_records()

        return record

    def ingest_file(self, file_path: str, source: str = None) -> List[CuratedRecord]:
        """Ingesta un archivo completo, dividiéndolo en chunks si es necesario."""
        if not os.path.exists(file_path):
            return [self._error_record(f"Archivo no encontrado: {file_path}", source or "file")]

        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
        except Exception as e:
            return [self._error_record(f"Error leyendo archivo: {e}", source or "file")]

        source = source or f"file:{os.path.basename(file_path)}"

        # Dividir en chunks si es largo
        chunks = self._chunk_content(content, max_chars=2000)

        records = []
        for i, chunk in enumerate(chunks):
            if len(chunk.strip()) < 10:
                continue
            record = self.ingest_text(chunk, source=f"{source}:chunk_{i}")
            records.append(record)

        return records

    def search(self, query: str, topic: ContentTopic = None,
               min_quality: QualityLevel = None,
               limit: int = 10) -> List[CuratedRecord]:
        """Busca registros por keyword matching y filtros."""
        results = []
        query_lower = query.lower()
        query_words = set(query_lower.split())

        quality_order = {
            QualityLevel.HIGH: 3,
            QualityLevel.MEDIUM: 2,
            QualityLevel.LOW: 1,
            QualityLevel.UNRELIABLE: 0,
        }

        for record in self._records.values():
            # Skip deprecated
            if record.deprecated:
                continue

            # Filter by topic
            if topic and record.topic != topic:
                continue

            # Filter by quality
            if min_quality:
                if quality_order.get(record.quality, 0) < quality_order.get(min_quality, 0):
                    continue

            # Score by keyword match
            content_lower = record.content.lower()
            match_count = sum(1 for w in query_words if w in content_lower)

            if match_count > 0:
                results.append((match_count, record))

        # Sort by relevance
        results.sort(key=lambda x: x[0], reverse=True)
        return [r for _, r in results[:limit]]

    def deprecate_old(self) -> int:
        """Marca registros como deprecados si no se validaron en DEPRECATION_DAYS."""
        threshold = time.time() - (DEPRECATION_DAYS * 86400)
        deprecated_count = 0

        for record in self._records.values():
            if record.deprecated:
                continue
            if record.validated_at is None and record.ingested_at < threshold:
                record.deprecated = True
                deprecated_count += 1
            elif record.validated_at and record.validated_at < threshold:
                record.deprecated = True
                deprecated_count += 1

        if deprecated_count > 0 and self.storage_path:
            self._save_records()

        return deprecated_count

    def get_contradictions(self) -> List[Tuple[CuratedRecord, CuratedRecord, str]]:
        """Retorna pares de registros contradictorios."""
        contradictions = []
        seen = set()

        for r1 in self._records.values():
            if r1.deprecated:
                continue
            for r2 in self._records.values():
                if r2.deprecated or r1.record_id == r2.record_id:
                    continue
                pair_key = tuple(sorted([r1.record_id, r2.record_id]))
                if pair_key in seen:
                    continue
                seen.add(pair_key)

                # Check for contradictions
                detected = self._detect_contradictions_between(r1.content, r2.content)
                if detected:
                    contradictions.append((r1, r2, detected))

        return contradictions

    def get_stats(self) -> Dict[str, Any]:
        """Estadísticas del curador."""
        topics = {}
        qualities = {}
        for record in self._records.values():
            topics[record.topic.value] = topics.get(record.topic.value, 0) + 1
            qualities[record.quality.value] = qualities.get(record.quality.value, 0) + 1

        return {
            "total_records": len(self._records),
            "deprecated": sum(1 for r in self._records.values() if r.deprecated),
            "by_topic": topics,
            "by_quality": qualities,
            "unique_hashes": len(self._hash_index),
        }

    # ─── Métodos internos ─────────────────────────────────────────────────────

    def _clean_text(self, text: str) -> str:
        """Limpia texto: elimina ruido, normaliza whitespace."""
        # Remove HTML tags
        cleaned = re.sub(r'<[^>]+>', '', text)
        # Normalize whitespace
        cleaned = re.sub(r'\s+', ' ', cleaned).strip()
        # Remove control characters
        cleaned = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', cleaned)
        return cleaned

    def _compute_hash(self, text: str) -> str:
        """Computa hash SHA-256 para deduplicación."""
        # Normalize before hashing: lowercase, remove extra spaces
        normalized = ' '.join(text.lower().split())
        return hashlib.sha256(normalized.encode()).hexdigest()

    def _classify_topic(self, text: str) -> ContentTopic:
        """Clasifica el topic del texto por keyword matching."""
        text_lower = text.lower()

        topic_keywords = {
            ContentTopic.FINANCE: ["financiero", "inversión", "portfolio", "rentabilidad",
                                    "financial", "investment", "return", "asset"],
            ContentTopic.TRADING: ["trading", "estrategia", "backtest", "forex", "señal",
                                    "signal", "order", "position", "entry", "exit"],
            ContentTopic.TECHNOLOGY: ["software", "código", "api", "base de datos", "servidor",
                                       "code", "database", "server", "deploy"],
            ContentTopic.AI_ML: ["modelo", "machine learning", "neural", "embedding",
                                  "model", "training", "inference", "llm", "gpt"],
            ContentTopic.RISK_MANAGEMENT: ["riesgo", "risk", "drawdown", "stop loss",
                                            "volatilidad", "volatility", "exposure"],
            ContentTopic.ARCHITECTURE: ["arquitectura", "architecture", "sistema", "módulo",
                                         "module", "component", "service", "microservice"],
        }

        scores = {}
        for topic, keywords in topic_keywords.items():
            score = sum(1 for kw in keywords if kw in text_lower)
            if score > 0:
                scores[topic] = score

        if scores:
            return max(scores, key=scores.get)
        return ContentTopic.GENERAL

    def _evaluate_quality(self, text: str, source: str) -> float:
        """Evalúa la calidad del contenido (0.0 - 1.0)."""
        score = 0.5  # Base

        # Length bonus (more content = more likely useful)
        if len(text) > 100:
            score += 0.1
        if len(text) > 500:
            score += 0.1

        # Structure indicators
        if any(marker in text for marker in ["1.", "2.", "3.", "- ", "* "]):
            score += 0.05  # Has lists/structure
        if "porque" in text.lower() or "because" in text.lower():
            score += 0.05  # Has reasoning

        # Source quality
        trusted_sources = ["official", "docs", "paper", "research", "github"]
        if any(ts in source.lower() for ts in trusted_sources):
            score += 0.1

        # Penalty: too short
        if len(text) < 30:
            score -= 0.2

        # Penalty: too much repetition
        words = text.lower().split()
        if words:
            unique_ratio = len(set(words)) / len(words)
            if unique_ratio < 0.3:
                score -= 0.1

        return max(0.0, min(1.0, score))

    def _quality_from_score(self, score: float) -> QualityLevel:
        """Convierte score numérico a QualityLevel."""
        if score >= 0.8:
            return QualityLevel.HIGH
        elif score >= 0.6:
            return QualityLevel.MEDIUM
        elif score >= 0.4:
            return QualityLevel.LOW
        return QualityLevel.UNRELIABLE

    def _detect_contradictions(self, text: str, topic: ContentTopic) -> List[str]:
        """Detecta contradicciones con registros existentes del mismo topic."""
        contradictions = []
        for record in self._records.values():
            if record.deprecated or record.topic != topic:
                continue
            detected = self._detect_contradictions_between(text, record.content)
            if detected:
                contradictions.append(f"{record.record_id}: {detected}")
        return contradictions

    def _detect_contradictions_between(self, text1: str, text2: str) -> str:
        """Detecta contradicciones entre dos textos."""
        t1_lower = text1.lower()
        t2_lower = text2.lower()

        for pos, neg in NEGATION_PAIRS:
            # Check both directions
            if pos in t1_lower and neg in t2_lower:
                return f"'{pos}' vs '{neg}'"
            if neg in t1_lower and pos in t2_lower:
                return f"'{neg}' vs '{pos}'"

        return ""

    def _chunk_content(self, content: str, max_chars: int = 2000) -> List[str]:
        """Divide contenido en chunks por párrafos."""
        paragraphs = content.split('\n\n')
        chunks = []
        current_chunk = ""

        for para in paragraphs:
            if len(current_chunk) + len(para) > max_chars and current_chunk:
                chunks.append(current_chunk.strip())
                current_chunk = para
            else:
                current_chunk += "\n\n" + para if current_chunk else para

        if current_chunk.strip():
            chunks.append(current_chunk.strip())

        return chunks

    def _error_record(self, error_msg: str, source: str) -> CuratedRecord:
        """Crea un registro de error."""
        return CuratedRecord(
            record_id=f"err_{int(time.time())}",
            content="",
            topic=ContentTopic.GENERAL,
            quality=QualityLevel.UNRELIABLE,
            quality_score=0.0,
            source=source,
            content_hash="",
            metadata={"error": error_msg},
        )

    def _save_records(self):
        """Persiste registros a disco."""
        if not self.storage_path:
            return
        try:
            data = {rid: asdict(r) for rid, r in self._records.items()}
            os.makedirs(os.path.dirname(self.storage_path), exist_ok=True)
            with open(self.storage_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False, default=str)
        except Exception as e:
            log.warning(f"Error guardando registros: {e}")

    def _load_records(self):
        """Carga registros desde disco."""
        try:
            with open(self.storage_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            for rid, rdata in data.items():
                rdata["topic"] = ContentTopic(rdata.get("topic", "general"))
                rdata["quality"] = QualityLevel(rdata.get("quality", "low"))
                record = CuratedRecord(**rdata)
                self._records[rid] = record
                if record.content_hash:
                    self._hash_index[record.content_hash] = rid
        except Exception as e:
            log.warning(f"Error cargando registros: {e}")


# ─── Singleton ─────────────────────────────────────────────────────────────────

_curator: Optional[InformationCurator] = None

def get_information_curator(storage_path: str = None) -> InformationCurator:
    global _curator
    if _curator is None:
        _curator = InformationCurator(storage_path)
    return _curator
