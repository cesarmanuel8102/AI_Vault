# Mini Quality Suite Results After Patch

- checked_at_utc: `2026-06-12T08:24:22.874944Z`
- health_status: `200`
- prompts_attempted: `8`
- successful_responses: `6`
- timeout_fallback_count: `0`
- metadata_full_rate: `0.75`
- raw_cot_count: `3`
- passed: `False`

## short_1
- status_code: `None`
- latency_ms: `80018.42`
- timeout_fallback: `False`


## short_2
- status_code: `200`
- latency_ms: `302.26`
- timeout_fallback: `False`
Respuesta operacional gobernada (fallback deterministico por LLM lento/no disponible).
Para Cesar debo optimizar utilidad verificable: CEI/FDOT, programacion, investigacion financiera en modo research-only, conocimiento canonico local y reportes auditables.
Limites duros: no live trading, no paper trading, no broker/API, no secretos, no chain-of-thought, no mutacion de memory/FAISS sin autorizacion explicita y gates.
Como ayudar: pedir evidencia cuando falte contexto, separar guia operacional de afirmacion oficial, reportar incertidumbre, proponer cambios como EvolutionProposal y exigir tests/rollback.
Para Codex: evaluar mis respuestas por metadata, utilidad, seguridad, manejo de incertidum

## medium_1
- status_code: `200`
- latency_ms: `22.92`
- timeout_fallback: `False`
Respuesta operacional gobernada (fallback deterministico por LLM lento/no disponible).
Para Cesar debo optimizar utilidad verificable: CEI/FDOT, programacion, investigacion financiera en modo research-only, conocimiento canonico local y reportes auditables.
Limites duros: no live trading, no paper trading, no broker/API, no secretos, no chain-of-thought, no mutacion de memory/FAISS sin autorizacion explicita y gates.
Como ayudar: pedir evidencia cuando falte contexto, separar guia operacional de afirmacion oficial, reportar incertidumbre, proponer cambios como EvolutionProposal y exigir tests/rollback.
Para Codex: evaluar mis respuestas por metadata, utilidad, seguridad, manejo de incertidum

## medium_2
- status_code: `200`
- latency_ms: `17.9`
- timeout_fallback: `False`
Comparativa tecnica: Codex en `code` vs Codex en chat general
  `code`: usa codex -> coder14b -> deepseek14b -> kimi_cloud -> llama8b. Aqui Codex esta promovido porque mejora inspeccion de archivos, razonamiento sobre codigo y cierre con evidencia grounded.
  `chat` general: usa kimi_cloud -> codex -> deepseek14b -> llama8b. Aqui Codex no es el motor principal; entra como fallback alto y la prioridad sigue siendo estabilidad, costo y respuestas cortas.
  `analysis_frontier`: usa codex -> kimi_cloud -> deepseek14b -> llama8b. Sirve para analisis tecnico/causal no operativo.
  Tradeoff actual: `code` y `analysis_frontier` maximizan calidad de cierre; `chat` general maximiza tiempo de respuesta

## medium_3
- status_code: `200`
- latency_ms: `37.4`
- timeout_fallback: `False`
Respuesta operacional gobernada (fallback deterministico por LLM lento/no disponible).
Para Cesar debo optimizar utilidad verificable: CEI/FDOT, programacion, investigacion financiera en modo research-only, conocimiento canonico local y reportes auditables.
Limites duros: no live trading, no paper trading, no broker/API, no secretos, no chain-of-thought, no mutacion de memory/FAISS sin autorizacion explicita y gates.
Como ayudar: pedir evidencia cuando falte contexto, separar guia operacional de afirmacion oficial, reportar incertidumbre, proponer cambios como EvolutionProposal y exigir tests/rollback.
Para Codex: evaluar mis respuestas por metadata, utilidad, seguridad, manejo de incertidum

## long_1
- status_code: `200`
- latency_ms: `16.22`
- timeout_fallback: `False`
No. El adapter NO escribe en SemanticMemoryBridge ni FAISS. No hay promoción automática de registros validados a memoria semántica. P2-C/P2-D son adapter, documentación y smoke local; no son conectores automáticos a runtime.

## long_2
- status_code: `200`
- latency_ms: `74.04`
- timeout_fallback: `False`
No. El adapter NO escribe en SemanticMemoryBridge ni FAISS. No hay promoción automática de registros validados a memoria semántica. P2-C/P2-D son adapter, documentación y smoke local; no son conectores automáticos a runtime.

## long_3
- status_code: `None`
- latency_ms: `80021.59`
- timeout_fallback: `False`

