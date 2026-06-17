# Diagnóstico timeout/generation quality

## Causa raíz primaria
El presupuesto efectivo de chat es `30s`. `LLMManager` recibe `max_time=30` y descarta todos los modelos porque sus timeouts nominales requieren más margen: `llama8b` ~62s, `kimi_cloud` ~77s, `deepseek14b` ~92s y `codex` ~122s.

Resultado: muchas consultas no intentan generación real; caen en fallback casi inmediato.

## Causa secundaria
El probe directo de Ollama con `qwen2.5-coder:14b` para 32 tokens no respondió en `75s`. Subir timeout puede evitar el budget-skip, pero no garantiza buena UX si el modelo local está demasiado lento.

## Evidencia clave
- Logs: `Budget-skip ... remaining=30s < needed=62-122s`.
- Brain medium prompt: fallback en ~84ms, no generación real.
- Ollama directo: timeout a 75s.
- Fastpath `/model`: responde en ~15ms, por lo que runtime y adapter están vivos.

## Recomendación
Siguiente frente: `FRONT-BRAIN-TIMEOUT-GENERATION-QUALITY-FIX-01`.
Debe probar una solución segura: presupuesto por chain + ruta corta de baja latencia, manteniendo fallback como no-éxito.
