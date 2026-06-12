# FRONT-CHAT-OPENAI-COMPATIBILITY-ADAPTER-PRESERVE-ROUTER-01

## Objective
Create a minimal OpenAI-compatible adapter for Brain V9 so Open WebUI, Codex, Kimi, GLM, or another local agent can talk to Brain through standard `/v1` endpoints while preserving the canonical router entrypoint.

## Previous Router Entrypoint Verification
- `tmp_agent/brain_v9/core/router_entrypoint.py` exists: `True`
- `handle_user_message` exists: `True`
- dry-run ok: `True`
- governance applied: `True`
- no CoT leak: `True`
- canonical path: `C:\AI_VAULT_CANONICAL`

## Why Adapter Must Preserve Router
A naive adapter that calls `LLMManager.query()` directly would bypass `IntentDetector.detect()`, route selection, BrainSession governance, Tool01/GAK gates, curated lookup handling, no-CoT response hygiene, and observability metadata. This front makes the adapter protocol-only.

## Files Changed
- `tmp_agent/brain_v9/api/__init__.py`
- `tmp_agent/brain_v9/api/openai_compat.py`
- `tmp_agent/brain_v9/main.py`
- `tmp_agent/brain_v9/evolution/direct_brain_client.py`
- `tmp_agent/brain_v9/evolution/codex_brain_dialogue_probe.py`
- `tests/smoke/smoke_front_chat_openai_compatibility_adapter_preserve_router_01.py`

## /v1/models Behavior
`GET /v1/models` returns an OpenAI-style list containing:
- `brain-v9-local`
- `brain`
- `ai-vault-brain`

## /v1/chat/completions Behavior
`POST /v1/chat/completions` accepts OpenAI-style messages, extracts the latest user message, calls `handle_user_message(...)`, and maps the governed Brain result to an OpenAI-compatible `chat.completion` object.

## Stream Behavior
`stream=true` returns a safe unsupported-feature error. Streaming is not faked.

## Router Preservation Proof
- Adapter imports `handle_user_message` from `brain_v9.core.router_entrypoint`.
- Adapter does not call `LLMManager.query()`.
- Adapter does not call `.llm.query`.
- Adapter does not call FAISS writes, semantic memory writes, broker, or trading code.

## Direct Codex-to-Brain Client
Created `tmp_agent/brain_v9/evolution/direct_brain_client.py` with:
- `probe_models`
- `chat_completion`
- `chat_batch`
- `redact_sensitive`
- `validate_openai_response`
- `extract_brain_metadata`

## Codex-to-Brain Dialogue Probe Result
- probe file: `tmp_agent/brain_v9/evolution/codex_brain_dialogue_probe.py`
- dialogue ran: `False`
- status: `SERVER_RESTART_REQUIRED_FOR_ADAPTER`
- successful responses: `0`
- preliminary score: `0.0`
- reason if not run: runtime `/v1/chat/completions` is not loaded until a safe Brain restart/load occurs.

## Runtime HTTP Probe Result
- restart status: `RUNTIME_RESTART_SKIPPED_UNSAFE_PORT_OWNER`
- restart performed: `False`
- `/health` ok: `True`
- runtime `/v1/models` passed: `False`
- runtime `/v1/chat/completions` passed: `False`
- Brain metadata ok: `False`

## Container-to-Brain Probe Result
- Open WebUI expected base URL: `http://host.docker.internal:8090/v1`
- container-to-Brain passed: `False`
- result depends on runtime loading the new `/v1` adapter.

## Open WebUI Configuration Guidance
- Base URL from container: `http://host.docker.internal:8090/v1`
- Model: `brain-v9-local`
- API key: dummy/local if UI requires one

## Memory / FAISS Immutability Proof
- semantic memory unchanged: `True`
- FAISS index unchanged: `True`
- FAISS ids unchanged: `True`
- semantic memory lines: `1715`
- FAISS ids: `1616`
- FAISS ntotal: `1616`
- runtime base path: `C:\AI_VAULT_CANONICAL`

## Tests Result
- smoke: `tests/smoke/smoke_front_chat_openai_compatibility_adapter_preserve_router_01.py`
- result: `34 passed`

## Import/TestClient Side Effect Detected
- Unexpected dirty files were detected under `tmp_agent/knowledge/external/github/*.json` after importing/testing `tmp_agent/brain_v9/main.py` with TestClient.
- Evidence was saved under `tmp_agent/front_chat_openai_compatibility_adapter_preserve_router_01/unexpected_github_knowledge_side_effect.diff`.
- The side-effect files were not staged.
- The side-effect files were surgically reverted with the approved path-scoped cleanup.
- The adapter commit excludes those files.
- Recommended future front: `FRONT-BRAIN-V9-IMPORT-SIDE-EFFECTS-HARDENING-01`.

## Remaining Gaps
- Runtime 8090 must safely load/restart to expose `/v1/models` and `/v1/chat/completions` live.
- After runtime adapter loads, Open WebUI provider configuration should point to `http://host.docker.internal:8090/v1`.
- SSE streaming remains intentionally unsupported until a separate safe streaming front.

## Next Locked Front
`FRONT-BRAIN-V9-ADAPTER-RUNTIME-LOAD-FIX-01`
