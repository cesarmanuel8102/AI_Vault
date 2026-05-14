"""
SEMANTIC_MEMORY_BRIDGE.PY — Puente entre memoria semántica (FAISS+Ollama) y el chat

Conecta el sistema de memoria semántica existente (brain_v9/core/semantic_memory_faiss.py)
con el flujo principal del chat, para que:

1. Cada system prompt se enriquezca con resultados de búsqueda semántica relevantes
2. Intercambios importantes se auto-ingieran sin intervención
3. Correcciones del usuario se persistan como conocimiento

Sin este bridge, el agente "olvida" entre sesiones lo que aprendió.
Con el bridge, cada chat es una oportunidad de aprendizaje automático.
"""

import hashlib
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any

log = logging.getLogger("semantic_memory_bridge")


@dataclass
class MemoryContext:
    """Contexto de memoria semántica para inyección en system prompt."""
    relevant_memories: List[Dict[str, Any]] = field(default_factory=list)
    auto_ingested: bool = False
    query_used: str = ""
    token_count: int = 0


class SemanticMemoryBridge:
    """
    Puente entre la memoria semántica FAISS y el chat.

    Degradación graceful: si FAISS no está disponible, continúa sin memoria.
    """

    MAX_CONTEXT_TOKENS = 300  # Límite de tokens para contexto semántico
    MAX_RESULTS = 5           # Máximo de resultados de búsqueda

    # Patrones que trigger auto-ingesta
    AUTO_INGEST_PATTERNS = [
        "corrección:", "corrijo:", "en realidad",
        "no, es", "equivocado", "incorrecto",
        "la respuesta correcta es", "should be",
        "that's wrong", "actually",
    ]

    def __init__(self, semantic_memory=None):
        self._semantic_memory = semantic_memory
        self._ingest_count = 0
        self._search_count = 0

    def set_semantic_memory(self, memory):
        """Inyecta el sistema de memoria semántica."""
        self._semantic_memory = memory

    def enrich_prompt(self, user_message: str, system_prompt: str) -> str:
        """
        Enriquece el system prompt con contexto de memoria semántica.

        Busca memorias relevantes al mensaje del usuario y las añade
        como contexto al inicio del prompt.
        """
        context = self._search_context(user_message)

        if not context.relevant_memories:
            return system_prompt

        # Formatear memorias como contexto compacto
        memory_text = self._format_memories(context.relevant_memories)

        # Insertar después del system prompt base
        enriched = f"{system_prompt}\n\n### CONTEXTO DE MEMORIA SEMÁNTICA\n{memory_text}"
        return enriched

    def auto_ingest_if_relevant(self, user_message: str, assistant_response: str,
                                 session_id: str = "default") -> bool:
        """
        Auto-ingesta intercambios que parecen importantes.

        Criterios de auto-ingesta:
        - Correcciones del usuario
        - Decisiones significativas
        - Conocimiento factual nuevo
        - Claims que el asistente hizo

        Returns True si se ingirió algo.
        """
        if not self._semantic_memory:
            return False

        should_ingest = False
        ingest_reason = ""

        # 1. Correcciones del usuario
        msg_lower = user_message.lower()
        for pattern in self.AUTO_INGEST_PATTERNS:
            if pattern in msg_lower:
                should_ingest = True
                ingest_reason = "user_correction"
                break

        # 2. Decisiones (verbos de acción)
        action_verbs = ["decido", "decidimos", "vamos a", "elegimos",
                        "decide", "let's", "we will", "chose"]
        for verb in action_verbs:
            if verb in msg_lower:
                should_ingest = True
                ingest_reason = "decision"
                break

        # 3. Claims factuales del asistente
        factual_indicators = ["es ", "son ", "el valor es", "la tasa es",
                              "is ", "are ", "the value is"]
        for indicator in factual_indicators:
            if indicator in assistant_response.lower()[:200]:
                # Solo si parece un claim factual (no una opinión)
                if any(char.isdigit() for char in assistant_response[:200]):
                    should_ingest = True
                    ingest_reason = "factual_claim"
                    break

        if should_ingest:
            content = f"Usuario: {user_message}\nAsistente: {assistant_response}"
            self._do_ingest(content, ingest_reason, session_id)
            return True

        return False

    def manual_ingest(self, content: str, source: str = "manual",
                       session_id: str = "default") -> bool:
        """Ingesta manual de contenido."""
        return self._do_ingest(content, source, session_id)

    def search(self, query: str, top_k: int = None) -> List[Dict[str, Any]]:
        """Búsqueda directa en memoria semántica."""
        if not self._semantic_memory:
            return []

        top_k = top_k or self.MAX_RESULTS
        self._search_count += 1

        try:
            if hasattr(self._semantic_memory, 'search'):
                results = self._semantic_memory.search(query, top_k=top_k)
                return results if isinstance(results, list) else []
            return []
        except Exception as e:
            log.warning(f"Error en búsqueda semántica: {e}")
            return []

    def get_stats(self) -> Dict[str, Any]:
        """Estadísticas del bridge."""
        stats = {
            "ingest_count": self._ingest_count,
            "search_count": self._search_count,
            "memory_available": self._semantic_memory is not None,
        }
        if self._semantic_memory and hasattr(self._semantic_memory, 'status'):
            try:
                stats["memory_status"] = self._semantic_memory.status()
            except Exception:
                pass
        return stats

    def _search_context(self, query: str) -> MemoryContext:
        """Busca contexto relevante en memoria semántica."""
        results = self.search(query)
        return MemoryContext(
            relevant_memories=results,
            auto_ingested=False,
            query_used=query,
            token_count=sum(len(str(r).split()) for r in results),
        )

    def _format_memories(self, memories: List[Dict[str, Any]]) -> str:
        """Formatea memorias para inyección compacta en prompt."""
        parts = []
        total_tokens = 0

        for mem in memories[:self.MAX_RESULTS]:
            text = mem.get("text", mem.get("content", str(mem)))[:200]
            score = mem.get("score", mem.get("relevance", 0.0))
            source = mem.get("source", "unknown")

            entry = f"- [{source}] (relevancia={score:.2f}) {text}"
            entry_tokens = len(entry.split())

            if total_tokens + entry_tokens > self.MAX_CONTEXT_TOKENS:
                break

            parts.append(entry)
            total_tokens += entry_tokens

        return "\n".join(parts) if parts else ""

    def _do_ingest(self, content: str, source: str, session_id: str) -> bool:
        """Ejecuta la ingesta en el sistema de memoria semántica."""
        if not self._semantic_memory:
            return False

        try:
            if hasattr(self._semantic_memory, 'ingest'):
                self._semantic_memory.ingest(content, metadata={
                    "source": source,
                    "session_id": session_id,
                    "timestamp": time.time(),
                })
            elif hasattr(self._semantic_memory, 'add_document'):
                self._semantic_memory.add_document(content, metadata={
                    "source": source,
                    "session_id": session_id,
                })
            else:
                return False

            self._ingest_count += 1
            log.info(f"[SemanticBridge] Ingesta: source={source}, session={session_id}")
            return True
        except Exception as e:
            log.warning(f"Error en ingesta semántica: {e}")
            return False


# ─── Singleton ─────────────────────────────────────────────────────────────────

_bridge: Optional[SemanticMemoryBridge] = None

def get_semantic_memory_bridge(semantic_memory=None) -> SemanticMemoryBridge:
    global _bridge
    if _bridge is None:
        _bridge = SemanticMemoryBridge(semantic_memory)
    return _bridge
