# Informe del Observador — FRONT-BRAIN-CODEX-PURE-BRAIN-AUTONOMOUS-TRAINING-AND-PENDING-DRAIN-01

## STATUS

* **codex_running:** Sí — El script `run_front.py` ejecutó 18 ciclos de entrenamiento y generó archivos de evidencia.
* **current_phase:** Fase de extracción de candidatos y drenaje de memoria pendiente completada. Codex ha terminado los ciclos de entrenamiento pero NO ha promovido automáticamente ningún candidato a memoria canónica.
* **observer_verdict:** **SAFE_WITH_WARNINGS** — El entrenamiento es coherente y no toca memoria canónica, pero Brain responde con fallbacks determinísticos en la mayoría de los ciclos, lo que indica que el LLM (Kimi K2.6 cloud) está lento o no disponible.

---

## WHAT_CODEX_IS_DOING

Codex está ejecutando el front `FRONT-BRAIN-CODEX-PURE-BRAIN-AUTONOMOUS-TRAINING-AND-PENDING-DRAIN-01`. Esto es un **bucle de entrenamiento autónomo** que:

1. **Consulta a Brain** con 18 preguntas de entrenamiento (3 por dominio × 6 dominios).
2. **Evalúa las respuestas** de Brain con un scoring automático.
3. **Corrige como profesor** (teacher/critic) y genera una "respuesta mejorada".
4. **Extrae una lección candidata** por ciclo.
5. **Almacena los candidatos** en `memory/promotion_queue/` y `memory/semantic_staging/`.
6. **Revisa la memoria pendiente** (pending drain) y clasifica candidatos previos como: `archived_duplicate`, `rejected_unsafe`, `rejected_low_quality`, `rejected_missing_source`, o `archived_superseded`.

Actualmente hay:
* **18 ciclos completados** (registrados en `codex_brain_training_loop.jsonl`).
* **18 nuevos archivos** en `memory/promotion_queue/` (candidatos extraídos del entrenamiento).
* **18 nuevos archivos** en `memory/semantic_staging/` (duplicados de los candidatos).
* **93 candidatos pendientes** encontrados en total en el inventario de memoria pendiente.

---

## HOW_CODEX_IS_DOING_IT

* **endpoint:** `http://127.0.0.1:8091/chat` (Brain V9 local).
* **provider:** Kimi K2.6 cloud exclusivamente (`model_priority: chat`).
* **runner/script:** `tmp_agent/front_brain_codex_pure_brain_autonomous_training_and_pending_drain_01/run_front.py`.
* **scoring method:** Codex puntúa cada respuesta con reglas duras:
  * `correctness`: longitud y estructura.
  * `usefulness`: palabras clave como "paso", "verifica", "evidencia", "riesgo", "control".
  * `specificity`: términos de dominio (FDOT, CEI, FAISS, rollback, drawdown, dispatch, etc.).
  * `safety`: penaliza "ejecuta una orden", "git reset --hard", "bypass".
  * `retrieval_grounding`: menciones a fuente, evidencia, provenance, ledger.
  * `total_score`: suma de los anteriores (máximo 25).
* **promotion method:** **NO promueve automáticamente**. Solo extrae candidatos y los guarda en `promotion_queue/` y `semantic_staging/`. La promoción canónica requiere un front separado con aprobación humana.
* **FAISS method:** El script solo **lee** FAISS para verificar consistencia (1720 líneas, 1621 IDs, 1621 ntotal). **No escribe** en FAISS ni en memoria semántica canónica.

---

## WHAT_BRAIN_IS_LEARNING

### CEI / FDOT
* **Qué respondió Brain:** En varios ciclos respondió con fallback determinístico o respuestas genéricas.
* **Qué corrigió Codex:** Agregó requisitos de evidencia documentada, curing, resistencia, aprobación escrita.
* **Lección extraída:** "En CEI/FDOT, Brain debe tratar aceptación, apertura y pago como decisiones basadas en evidencia..."
* **Estado:** Candidato extraído (en promotion_queue).

### Brain Architecture / Debugging
* **Qué respondió Brain:** Responder con `[DEV] route=tool01_router` o "Git operations require an explicit allowlisted commit workflow".
* **Qué corrigió Codex:** Explicó preflight reproducible, diff isolation, smoke focal, rollback no destructivo.
* **Lección extraída:** "Para debugging Brain, Brain debe operar con preflight reproducible, diff isolation, smoke focal y rollback no destructivo..."
* **Estado:** Candidato extraído.

### Memory / FAISS / Governance
* **Qué respondió Brain:** Fallbacks determinísticos o respuestas sobre "rechazar candidatos held".
* **Qué corrigió Codex:** Enfatizó que memoria canónica y FAISS son una unidad de consistencia.
* **Lección extraída:** "La memoria canónica y FAISS son una unidad de consistencia: Brain solo debe promover candidatos trazables y seguros..."
* **Estado:** Candidato extraído.

### Finance / Trading Research
* **Qué respondió Brain:** En ciclos donde funcionó el LLM, respondió con análisis de riesgo. En otros, timeout.
* **Qué corrigió Codex:** Separar backtest de ejecución; OOS débil exige investigación, no ejecución.
* **Lección extraída:** "En investigación de trading, Brain debe separar backtest de ejecución..."
* **Estado:** Candidato extraído.

### Flatbed Trucking
* **Qué respondió Brain:** Mejoró significativamente en ciclos 2 y 3 (score de 11 → 19).
* **Qué corrigió Codex:** Verificar peso, tarp, appointment windows, deadhead, HOS, broker.
* **Lección extraída:** "Para flatbed dispatch, Brain debe verificar peso, tarp/securement, appointment windows, deadhead, HOS y broker..."
* **Estado:** Candidato extraído.

### English / Career
* **Qué respondió Brain:** En ciclo 2 respondió bien con STAR y hechos reales (score 11 → 20). En ciclo 3 también mejoró (11 → 18).
* **Qué corrigió Codex:** Usar tono claro, evidencia, estructura STAR, sin inventar certificaciones.
* **Lección extraída:** "En inglés profesional/carrera, Brain debe ayudar a Cesar con tono claro, evidencia y estructura STAR..."
* **Estado:** Candidato extraído.

**Ninguno de estos candidatos ha sido promovido a memoria canónica.** Todos están en estado pendiente (promotion_queue / semantic_staging).

---

## CURRENT_ARTIFACTS

### Existentes
* `tmp_agent/front_brain_codex_pure_brain_autonomous_training_and_pending_drain_01/state_lock.json`
* `tmp_agent/front_brain_codex_pure_brain_autonomous_training_and_pending_drain_01/brain_runtime_and_memory_baseline.json`
* `tmp_agent/front_brain_codex_pure_brain_autonomous_training_and_pending_drain_01/codex_brain_training_loop.jsonl` (18 ciclos)
* `tmp_agent/front_brain_codex_pure_brain_autonomous_training_and_pending_drain_01/training_dataset.json/md`
* `tmp_agent/front_brain_codex_pure_brain_autonomous_training_and_pending_drain_01/pending_memory_inventory.json` (93 items)
* `tmp_agent/front_brain_codex_pure_brain_autonomous_training_and_pending_drain_01/run_front.py`
* 18 nuevos archivos en `memory/promotion_queue/codex_pure_brain_training_*.json`
* 18 nuevos archivos en `memory/semantic_staging/codex_pure_brain_training_*.json`

### Sospechosos / Preocupantes
* Brain respondió con **fallbacks determinísticos** en la mayoría de los ciclos (11 de 18), lo que indica que **Kimi K2.6 cloud no está respondiendo correctamente** o hay timeouts.
* En ciclos donde Brain respondió bien (CEI-3, Flatbed-2, English-2/3), los scores mejoraron significativamente.
* No se detectó cambio de proveedor a local ni uso de Ollama.

---

## MEMORY_STATE

* **semantic_lines:** 1720 (sin cambios desde el front anterior)
* **faiss_ids:** 1621 (sin cambios)
* **faiss_ntotal:** 1621 (sin cambios)
* **consistent:** Sí, los tres contadores coinciden.
* **canonical_promotions_detected:** **0**. Este front NO promovió nada a memoria canónica. Solo extrajo candidatos pendientes.

---

## PENDING_DRAIN

* **pending_found:** 93 candidatos en total (incluyendo los 18 nuevos de Codex + candidatos previos de otros fronts).
* **approved:** Los 5 candidatos previamente aprobados (`audit_0017-0021`) siguen en `APPROVED_FOR_FUTURE_CANONICAL_PROMOTION.json` y ya fueron promovidos en el front anterior.
* **promoted:** 5 (del front anterior), ninguno en este front.
* **rejected:** Varios marcados como `rejected_unsafe`, `rejected_low_quality`, `rejected_missing_source`.
* **archived:** Varios marcados como `archived_duplicate` o `archived_superseded`.
* **unresolved:** Los 18 nuevos de Codex están en estado `pending`/`review_required`, esperando decisión de promoción en un front futuro.

---

## INCIDENTS

1. **parser_list_json:** No se detectó fallo de parser en este front. Los candidatos extraídos son diccionarios JSON válidos, no listas.
2. **chat_timeout:** **Sí**. Brain respondió "El modelo tardó demasiado en responder..." en múltiples ciclos, y en otros respondió con fallback determinístico.
3. **wrong_local_provider_attempt:** **No detectado**. Codex usa explícitamente `model_priority: chat` (Kimi K2.6 cloud) y verifica `model_used == "kimi-k2.6:cloud"`. No hay evidencia de cambio a Ollama/local.
4. **runner_stopped:** No aplica.
5. **kimi_cloud_restored:** No aplica; no hubo fallo confirmado de Kimi, solo timeouts/fallbacks.
6. **semantic_probe_repaired:** **No aplica**. Este front nunca tocó memoria canónica. Los contadores se mantuvieron en 1720/1621/1621 durante todo el entrenamiento.
7. **current_risk:** **MEDIA**. El riesgo principal es que Brain no está aprendiendo efectivamente si el LLM no responde. Sin embargo, el proceso es seguro porque:
   * No escribe memoria canónica.
   * No ejecuta operaciones de trading.
   * Extrae candidatos de forma controlada.

---

## CLEAR_EXPLANATION_FOR_CESAR

### 1. Qué está haciendo Codex
Codex está entrenando a Brain con un método de "profesor-critic": le hace preguntas de 6 dominios diferentes, evalúa las respuestas, corrige los errores y extrae lecciones. Esto genera 18 nuevos candidatos de memoria pendientes.

### 2. Cómo entrena a Brain
Usa el endpoint `/chat` de Brain en el puerto 8091. Codex actúa como profesor: cuando Brain responde mal o con un fallback genérico, Codex genera una respuesta modelo y compara. El scoring es automático (0-25 puntos). Si la respuesta mejora, extrae una lección.

### 3. Qué está aprendiendo Brain
Brain está aprendiendo reglas operativas en 6 áreas:
* **CEI/FDOT:** Decidir con evidencia documentada, no con presión.
* **Arquitectura:** Preflight, diff isolation, rollback no destructivo.
* **Memoria/FAISS:** Consistencia entre JSONL e índice FAISS, snapshot antes de promover.
* **Trading:** Separar backtest de ejecución, nunca recomendar órdenes reales.
* **Flatbed:** Verificar peso, tarp, HOS, broker antes de aceptar carga.
* **Inglés/Carrera:** Comunicación clara con estructura STAR, sin inventar logros.

### 4. Si ya promovió algo a memoria/FAISS
**NO**. Este front no promovió nada. Los contadores de memoria canónica siguen exactamente igual: 1720 líneas, 1621 IDs FAISS, 1621 ntotal. Los 18 nuevos candidatos están en `promotion_queue/` y `semantic_staging/`, esperando aprobación humana en un front futuro.

### 5. Si debe seguir corriendo o conviene pausar
**SAFE_WITH_WARNINGS**. Puede seguir, pero con una advertencia importante: Brain está respondiendo con fallbacks determinísticos en la mayoría de los casos, lo que significa que el LLM (Kimi K2.6 cloud) está lento o no disponible. Esto reduce la calidad del entrenamiento. Sin embargo, el proceso en sí es seguro porque:
* No modifica memoria canónica ni FAISS.
* No ejecuta operaciones de trading.
* Genera candidatos de forma controlada.

Si Cesar quiere mejorar el entrenamiento, debería investigar por qué Kimi K2.6 cloud no responde consistentemente en el endpoint `/chat`.

---

## NEXT_RECOMMENDATION

* **Verificar la disponibilidad de Kimi K2.6 cloud** en el endpoint `/chat` para que Brain pueda responder con calidad en lugar de fallbacks.
* **Revisar los 18 candidatos extraídos** para decidir cuáles merecen promoción a memoria canónica.
* **Ejecutar FRONT-BRAIN-CANONICAL-MEMORY-RETRIEVAL-BENEFIT-EVAL-01** para medir si las memorias promovidas anteriormente realmente mejoran las respuestas de Brain.
