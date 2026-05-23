# P2-E SemanticMemory Read-Only Probe

## 1. Objetivo

Implementar un **probe read-only/dry-run** para inspeccionar la infraestructura de SemanticMemory/FAISS sin escribir, sin borrar y sin modificar índices. Este módulo descubre:
- Qué módulos/clases existen
- Qué métodos públicos exponen
- Qué archivos existen en memory/semantic
- Qué riesgos hay antes de integrar promote_real
- Qué contrato mínimo debe cumplir el adapter futuro

## 2. ¿Por Qué el Probe Read-Only va Antes de promote_real?

**Problema:** Integrar escritura real sin conocer la infraestructura:
- Riesgo de incompatibilidades de interfaces
- Posible corrupción de índices existentes
- Falta de rollback capability
- No hay trazabilidad de operaciones

**Solución:** Probe read-only que:
- Descubre módulos y clases sin importar/ ejecutar
- Verifica existencia de paths sin modificar
- Identifica riesgos antes de integración
- Propone contrato mínimo para adapter futuro

## 3. Qué Inspecciona

### 3.1 Módulos Candidatos
Busca archivos Python relacionados con semantic, faiss, memory:
```python
tmp_agent/brain_v9/core/semantic_memory_faiss.py
brain/semantic_memory_bridge.py
```

### 3.2 Clases Candidatas
Analiza AST para encontrar clases públicas:
```python
SemanticMemoryFAISS
SemanticMemoryBridge
```

### 3.3 Métodos Públicos
Extrae métodos públicos de clases candidatas:
```python
search, add_memory, enrich_prompt, auto_ingest_if_relevant
```

### 3.4 Path memory/semantic
Verifica existencia y contenido:
```
memory/semantic/semantic_memory.jsonl
memory/semantic/semantic_memory_faiss.index
memory/semantic/semantic_memory_faiss_ids.json
```

## 4. Qué NO Hace

- **NO** escribe en memory/semantic
- **NO** modifica índices FAISS
- **NO** importa faiss
- **NO** importa requests/httpx
- **NO** construye índices
- **NO** llama endpoints
- **NO** ejecuta métodos de SemanticMemory
- **NO** borra archivos

## 5. Resultados Esperados

### 5.1 Módulos Descubiertos
- `tmp_agent.brain_v9.core.semantic_memory_faiss`
- `brain.semantic_memory_bridge`

### 5.2 Clases Descubiertas
- `SemanticMemoryFAISS`
- `SemanticMemoryBridge`

### 5.3 Métodos Públicos
- `search()` - Para búsqueda semántica
- `add_memory()` - Para escritura futura
- `enrich_prompt()` - Para enriquecimiento de prompts

### 5.4 Archivos en memory/semantic
- `semantic_memory.jsonl` - Registro de memorias
- `semantic_memory_faiss.index` - Índice FAISS
- `semantic_memory_faiss_ids.json` - Mapeo de IDs

## 6. Riesgos Detectables

| ID | Riesgo | Severidad |
|----|--------|-----------|
| R1 | No existe memory/semantic | Crítico |
| R2 | No hay módulos candidatos | Crítico |
| R3 | FAISS no disponible | Crítico |
| R4 | Múltiples implementaciones | Medio |

## 7. Contrato Mínimo Futuro para SemanticMemory Adapter

### 7.1 Métodos Requeridos
- `add_memory(text, metadata, source)` → memory_id
- `search(query, top_k=5)` → List[MemoryResult]
- `get_by_id(memory_id)` → MemoryResult | None

### 7.2 Contrato de Entrada
```python
{
    "text": str,              # Texto a almacenar
    "metadata": Dict[str, Any], # Metadatos adicionales
    "source": str,            # Fuente del contenido
}
```

### 7.3 Contrato de Salida
```python
{
    "memory_id": str,
    "embedding": List[float],
    "similarity_score": float,
}
```

### 7.4 Manejo de Errores
- `FAISS_UNAVAILABLE` - FAISS no está instalado/disponible
- `EMBEDDING_FAILED` - Fallo al generar embedding
- `IO_ERROR` - Error de lectura/escritura

## 8. Requisitos Antes de Escritura Real

1. ✅ Probe read-only completado (P2-E Commit 3F)
2. ⏸️ Validar contrato de SemanticMemory
3. ⏸️ Crear adapter dry-run
4. ⏸️ Implementar rollback capability
5. ⏸️ Agregar observability de operaciones
6. ⏸️ Pruebas de integración controladas
7. ⏸️ Solo entonces: permitir escritura real

## 9. Próximo Paso Recomendado

**P2-E Commit 4 (cuando estén listos los requisitos):**

1. Validar contrato con implementación real
2. Crear adapter que valide payloads antes de FAISS
3. Implementar rollback real sobre índices
4. Pruebas end-to-end con dataset pequeño
5. Integrar con CuratedMemoryDryRunFlow
6. Permitir allow_real_write=True con governance completo

**Alternativa:** Saltar a P2-F GitHubSourceConnector.

---

**Estado:** P2-E Commit 3F completado  
**Scope:** Probe read-only de SemanticMemory  
**Escritura real:** BLOQUEADA hasta validación de contrato  
**Branch:** codex/own-capital-sustainable-return
