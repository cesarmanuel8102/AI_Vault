# Container-to-Brain Probe

- container_to_brain_passed: `True`
- openwebui_provider_base_url: `http://host.docker.internal:8091/v1`
- models_returncode: `0`
- chat_returncode: `0`
- models_include_brain_v9_local: `True`
- chat_completion_ok: `True`

## Models excerpt
```
{"object":"list","data":[{"id":"brain-v9-local","object":"model","created":0,"owned_by":"local"},{"id":"brain","object":"model","created":0,"owned_by":"local"},{"id":"ai-vault-brain","object":"model","created":0,"owned_by":"local"}]}
```

## Chat excerpt
```
{"id":"chatcmpl-e893e68542af4e19abe5ca94","object":"chat.completion","created":1781248853,"model":"brain-v9-local","choices":[{"index":0,"message":{"role":"assistant","content":"No pude ejecutar herramientas reales en este turno (agent_status=timeout). Respondo con el modelo LLM disponible.\nVerificaciÃ³n recibida. Brain V9 operativo en modo respuesta directa; no ejecutÃ© herramientas reales en este ciclo."},"finish_reason":"stop"}],"usage":{"prompt_tokens":0,"completion_tokens":0,"total_tokens":0},"brain":{"intent":"TRADING","route":"agent","governance_applied":true,"no_cot_leak":true,"canonical_path":"C:\\AI_VAULT_CANONICAL","latency_ms":48828.0,"errors":[],"adapter":"openai_compat","adapter_latency_ms":48828.0}}
```
