# cycle_02

- goal: improve token efficiency
- provider: codex / gpt-5.5
- risk: LOW
- decision: block
- no_cot_leak: True
- memory_faiss_unchanged: True

## Brain proposal

- Mejora: añadir un `provider_probe_compact_mode` que reduzca el contexto enviado a Kimi K2.6 a: estado operativo, objetivo, restricciones activas y última evidencia relevante; excluir memoria, FAISS, historial largo y catálogos no solicitados.
- Riesgo: pérdida de contexto útil en casos donde la decisión depende de trazas previas o datos cruzados.
- Test: comparar 20 probes actuales vs compactos midiendo tokens de entrada, consistencia de respuesta, cumplimiento de LOW/MEDIUM y ausencia de escrituras semánticas.
- Evidencia: el estado actual ya opera en `provider_probe`, sin writes FAISS/semánticos y con autorización LOW/MEDIUM; por tanto, el mayor ahorro viene de recortar contexto redundante antes del proveedor, no de cambiar lógica de autorización.

## Revised

Acción segura compacta: crear un único helper pequeño para recortar contexto repetitivo antes del prompt, limitado a rutas no protegidas y cubierto por tests.
Cambio propuesto: añadir `compact_context(text, max_chars)` en el módulo de construcción de prompts para eliminar bloques duplicados y truncar por límite explícito, sin tocar rutas protegidas ni cambiar lógica de decisión.
Test exacto: ejecutar `pytest tests/test_prompt_compaction.py -q`, verificando que conserva contenido crítico, elimina duplicados y respeta `max_chars`.
Rollback: revertir únicamente el commit/archivo del helper y su llamada en el prompt builder; al no modificar datos, memoria, FAISS ni rutas protegidas, el rollback es directo y sin migraciones.
