# Mini Quality Suite Results

- checked_at_utc: `2026-06-12T08:18:35.360770Z`
- health_status: `200`
- prompts_attempted: `8`
- successful_responses: `6`
- timeout_fallback_count: `0`
- metadata_full_rate: `0.75`
- raw_cot_count: `0`
- passed: `False`

## short_1
- status_code: `None`
- latency_ms: `130014.69`
- timeout_fallback: `False`


## short_2
- status_code: `200`
- latency_ms: `61153.78`
- timeout_fallback: `False`
LLM pool no disponible.
Modelos consultados: kimi_cloud, codex, deepseek14b, llama8b.
Motivo: llama8b: timeout (60s).
Ollama: posiblemente caído — verificar con: ollama serve.
Proxima accion: verificar que Ollama este corriendo en 127.0.0.1:11434, o reformular la consulta usando rutas deterministas (ej: 'git status', 'health', 'estado del sistema').

## medium_1
- status_code: `200`
- latency_ms: `60979.75`
- timeout_fallback: `False`
LLM pool no disponible.
Modelos consultados: kimi_cloud, codex, deepseek14b, llama8b.
Motivo: llama8b: timeout (60s).
Ollama: posiblemente caído — verificar con: ollama serve.
Proxima accion: verificar que Ollama este corriendo en 127.0.0.1:11434, o reformular la consulta usando rutas deterministas (ej: 'git status', 'health', 'estado del sistema').

## medium_2
- status_code: `200`
- latency_ms: `13.78`
- timeout_fallback: `False`
Comparativa tecnica: Codex en `code` vs Codex en chat general
  `code`: usa codex -> coder14b -> deepseek14b -> kimi_cloud -> llama8b. Aqui Codex esta promovido porque mejora inspeccion de archivos, razonamiento sobre codigo y cierre con evidencia grounded.
  `chat` general: usa kimi_cloud -> codex -> deepseek14b -> llama8b. Aqui Codex no es el motor principal; entra como fallback alto y la prioridad sigue siendo estabilidad, costo y respuestas cortas.
  `analysis_frontier`: usa codex -> kimi_cloud -> deepseek14b -> llama8b. Sirve para analisis tecnico/causal no operativo.
  Tradeoff actual: `code` y `analysis_frontier` maximizan calidad de cierre; `chat` general maximiza tiempo de respuesta

## medium_3
- status_code: `200`
- latency_ms: `281.34`
- timeout_fallback: `False`
LLM pool no disponible.
Modelos consultados: kimi_cloud, codex, deepseek14b, llama8b.
Motivo: llama8b: circuit_open.
Ollama: posiblemente caído — verificar con: ollama serve.
Proxima accion: verificar que Ollama este corriendo en 127.0.0.1:11434, o reformular la consulta usando rutas deterministas (ej: 'git status', 'health', 'estado del sistema').

## long_1
- status_code: `200`
- latency_ms: `12.25`
- timeout_fallback: `False`
No. El adapter NO escribe en SemanticMemoryBridge ni FAISS. No hay promoción automática de registros validados a memoria semántica. P2-C/P2-D son adapter, documentación y smoke local; no son conectores automáticos a runtime.

## long_2
- status_code: `200`
- latency_ms: `24.85`
- timeout_fallback: `False`
No. El adapter NO escribe en SemanticMemoryBridge ni FAISS. No hay promoción automática de registros validados a memoria semántica. P2-C/P2-D son adapter, documentación y smoke local; no son conectores automáticos a runtime.

## long_3
- status_code: `None`
- latency_ms: `130001.66`
- timeout_fallback: `False`

