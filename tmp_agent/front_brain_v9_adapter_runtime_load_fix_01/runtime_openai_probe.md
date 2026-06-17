# Runtime OpenAI Probe

- base_url: `http://127.0.0.1:8091`
- health_200: `True`
- models_200: `True`
- models_include_brain_v9_local: `True`
- chat_200: `True`
- chat_object_is_chat_completion: `True`
- message_content_exists: `True`
- brain_intent_exists: `True`
- brain_route_exists: `True`
- brain_governance_applied_true: `True`
- brain_no_cot_leak_true: `True`
- brain_canonical_path_ok: `True`
- stream_safe_unsupported: `True`

## Chat Response Excerpt
```
{"id":"chatcmpl-4d92b6b1a2874e3385db34a0","object":"chat.completion","created":1781248692,"model":"brain-v9-local","choices":[{"index":0,"message":{"role":"assistant","content":"No pude ejecutar herramientas reales en este turno (agent_status=timeout). Respondo con el modelo LLM disponible.\nVerificación recibida. Brain V9 operativo en modo respuesta directa; no se ejecutaron herramientas ni se consultaron archivos/logs en este ciclo."},"finish_reason":"stop"}],"usage":{"prompt_tokens":0,"completion_tokens":0,"total_tokens":0},"brain":{"intent":"CODE","route":"agent","governance_applied":true,"no_cot_leak":true,"canonical_path":"C:\\AI_VAULT_CANONICAL","latency_ms":45734.0,"errors":[],"adapter":"openai_compat","adapter_latency_ms":45734.0}}
```
