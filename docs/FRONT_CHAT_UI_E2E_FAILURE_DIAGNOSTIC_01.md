# FRONT-CHAT-UI-E2E-FAILURE-DIAGNOSTIC-01

## Objective
Diagnose why the chat/UI path is still failing end-to-end without changing runtime, memory, FAISS, trading, B8, or live processes.

## Important Reminder
The chat/UI is still failing. This front is diagnostic only; it does not declare the system complete and does not implement the fix.

## Canonical Safety
- canonical path: `C:\AI_VAULT_CANONICAL`
- branch head at diagnostic start: `278f5fa`
- semantic memory lines: `1715`
- FAISS ids: `1616`
- FAISS ntotal: `1616`
- runtime BASE_PATH: `C:\AI_VAULT_CANONICAL`
- canonical memory mutated: `false`
- canonical FAISS mutated: `false`

## Service / Port Inventory
- `3000`: not listening
- `8090`: pid=244420 name=python.exe
- `8010`: not listening
- `8000`: not listening
- `11434`: pid=23388 name=ollama.exe

Docker status: `DOCKER_UNAVAILABLE_OR_NOT_RUNNING`

## Endpoint Probes
- `http://127.0.0.1:3000/`: status=None ok=False ms=2028.4 error=URLError
- `http://localhost:3000/`: status=None ok=False ms=4041.6 error=URLError
- `http://127.0.0.1:11434/api/tags`: status=200 ok=True ms=34.8 error=
- `http://127.0.0.1:8090/health`: status=200 ok=True ms=12.7 error=
- `http://127.0.0.1:8090/docs`: status=200 ok=True ms=14.0 error=
- `http://127.0.0.1:8090/openapi.json`: status=200 ok=True ms=588.4 error=
- `http://127.0.0.1:8010/health`: status=None ok=False ms=2027.3 error=URLError
- `http://127.0.0.1:8010/docs`: status=None ok=False ms=2040.4 error=URLError
- `http://127.0.0.1:8010/openapi.json`: status=None ok=False ms=2027.2 error=URLError
- `http://127.0.0.1:8000/health`: status=None ok=False ms=2067.8 error=URLError
- `http://127.0.0.1:8000/openapi.json`: status=None ok=False ms=2043.1 error=URLError

## Route Discovery
- OpenAPI available: `True`
- discovered routes: `225`
- OpenAI-compatible `/v1/chat/completions`: `False`
- native chat routes discovered: `/chat`, `/chat/introspectivo`, `/agent` if listed in evidence

## Direct Backend Chat Probes
- direct backend chat passed: `False`
- `/chat` timed out under a short diagnostic probe when present.
- `/chat/introspectivo` returned protected/dev-off behavior when probed.
- details: `tmp_agent/front_chat_ui_e2e_failure_diagnostic_01/direct_backend_chat_probe.json`

## Open WebUI Provider Diagnostic
- Open WebUI reachable at port 3000: `False`
- Docker inspection status: `DOCKER_UNAVAILABLE_OR_NOT_RUNNING`
- provider config status: `OPEN_WEBUI_CONFIG_NOT_AVAILABLE`

## Streaming / SSE Diagnostic
- streaming compatible: `False`
- reason: OpenAI-compatible route was not discovered, so Open WebUI-compatible streaming cannot be validated.

## Session / Retrieval Diagnostic
- retrieval injection passed: `False`
- expected canary IDs: `SEC_GOV_CANARY_001_nist_csf_001, SEC_GOV_CANARY_001_nist_ai_rmf_002, SEC_GOV_CANARY_001_opa_docs_003, SEC_GOV_CANARY_001_mitre_atlas_004, SEC_GOV_CANARY_001_gvisor_docs_005`
- native chat route did not return usable canary evidence within the diagnostic timeout.

## Failure Classification
- primary failure: `UI_NOT_REACHABLE`
- secondary failures: `OPENAI_COMPATIBILITY_MISSING, TIMEOUT, STREAMING_SSE_MISMATCH, RETRIEVAL_INJECTION_FAILURE, CANONICAL_PATH_OK_BUT_UI_NOT_CONNECTED`
- confidence: `HIGH`

## Recommended Fix Plan
- next locked fix front: `FRONT-CHAT-UI-DOCKER-NETWORKING-FIX-01`
- likely files/config to inspect or change: `Open WebUI/container/startup configuration if UI should run on 3000, tmp_agent/brain_v9/main.py only if OpenAI-compatible adapter is chosen after UI is reachable, tests/smoke/smoke_front_chat_ui_docker_networking_fix_01.py`
- success criteria: `direct backend chat passes; Open WebUI chat passes; canonical retrieval evidence appears; no raw CoT leakage; response latency acceptable; tests pass`

## No Mutation Proof
- No tracked runtime diff was produced by this diagnostic.
- No memory/semantic files were staged.
- No FAISS add/reindex was executed.
- No process was killed or restarted.
- No trading, B8, broker/API, or `tmp_agent/strategies` files were touched.

## Tests
The smoke test validates diagnostic artifacts and guardrails:
`tests/smoke/smoke_front_chat_ui_e2e_failure_diagnostic_01.py`

## Next Locked Fix Front
`FRONT-CHAT-UI-DOCKER-NETWORKING-FIX-01`
