# FRONT-CHAT-UI-DOCKER-NETWORKING-FIX-01

## Objective
Restore the minimal Chat/UI layer by making Open WebUI reachable on local port 3000 without touching canonical memory, FAISS, trading, B8, legacy cleanup, or QC processes.

## Previous Diagnostic Summary
- Previous front: `FRONT-CHAT-UI-E2E-FAILURE-DIAGNOSTIC-01`
- Primary failure: `UI_NOT_REACHABLE`
- Backend 8090 reachable: `true`
- Ollama 11434 reachable: `true`
- Open WebUI 3000 reachable before this front: `False`

## Docker / Open WebUI Inventory
- Docker daemon available: `True`
- Open WebUI candidates detected: `1`
- Port 3000 before fix: `None`
- Docker Desktop was started safely because the Docker daemon was initially unavailable.

## Backend Connectivity Baseline
- `http://127.0.0.1:11434/api/tags`: status=200 ok=True ms=90.2 error=
- `http://host.docker.internal:11434/api/tags`: status=None ok=False ms=5009.0 error=URLError
- `http://127.0.0.1:8090/health`: status=200 ok=True ms=18.8 error=
- `http://127.0.0.1:8090/openapi.json`: status=200 ok=True ms=15.2 error=
- `http://127.0.0.1:3000/`: status=None ok=False ms=2041.6 error=URLError

## Start / Recreate Plan
- decision: `START_EXISTING_OPEN_WEBUI`
- reason: `Open WebUI candidate exists but is not running`
- no repository bind mount was used
- no secrets were passed

## Actions Applied
- action_taken: `docker_start_existing`
- container_id: `61edccb48634`
- image: `ghcr.io/open-webui/open-webui:main`
- env OLLAMA_BASE_URL observed: `OLLAMA_BASE_URL=/ollama`
- errors: `[]`

## Post-Fix UI Probes
- Open WebUI reachable after fix: `True`
- attempts: `11`
- final 127.0.0.1 status: `200`
- final localhost status: `200`

## Ollama Container Networking
- reachable from Open WebUI container: `True`
- method: `curl`

## Minimal Chat Compatibility
- UI_LAYER_RESTORED: `True`
- OLLAMA_PROVIDER_READY: `True`
- BRAIN_PROVIDER_READY: `False`
- NEEDS_OPENAI_COMPAT_ADAPTER: `True`
- local Ollama models detected: `nomic-embed-text:latest, deepseek-v4-pro:cloud, kimi-k2.5:cloud, gpt-oss:120b-cloud, qwen3-coder:480b-cloud, qwen2.5-coder:14b, gpt-oss:20b-cloud, deepseek-r1:14b, deepseek-v3.1:671b-cloud, qwen3-vl:235b-cloud`

## Fix Classification
- primary_result: `UI_RESTORED_BUT_BRAIN_OPENAI_COMPAT_MISSING`
- confidence: `HIGH`
- next recommended front: `FRONT-CHAT-OPENAI-COMPATIBILITY-ADAPTER-01`

## Remaining Gaps
- Open WebUI is reachable, but Brain does not expose OpenAI-compatible `/v1/chat/completions`.
- Full Brain chat integration through Open WebUI remains blocked until an OpenAI-compatible adapter or provider bridge is implemented.

## No Memory / FAISS Mutation Proof
- canonical_memory_mutated: `false`
- canonical_faiss_mutated: `false`
- semantic_memory_lines: `1715`
- faiss_ids: `1616`
- faiss_ntotal: `1616`
- no trading, B8, `tmp_agent/strategies`, broker/API, or legacy cleanup actions were used.

## Tests
- smoke test: `tests/smoke/smoke_front_chat_ui_docker_networking_fix_01.py`
- expected count: `20 passed`

## Next Locked Front
`FRONT-CHAT-OPENAI-COMPATIBILITY-ADAPTER-01`
