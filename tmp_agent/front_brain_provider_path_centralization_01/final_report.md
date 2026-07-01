# FRONT-BRAIN-PROVIDER-PATH-CENTRALIZATION-01

Status: IMPLEMENTED_VALIDATED

Implemented:
- Centralized PRIMARY_KIMI_MODEL in 	mp_agent/brain_v9/config.py.
- Moved Agent V2 finalizer Ollama endpoint use to API_ENDPOINTS["ollama"].
- Moved codegen Ollama endpoint use to API_ENDPOINTS["ollama"].
- Moved semantic FAISS embedding base URL to OLLAMA_BASE_URL / config-derived endpoint.
- Added smoke coverage in 	ests/smoke/test_front_brain_provider_centralization_01.py.

Validation:
- python -m py_compile passed for modified Python files.
- pytest tests/smoke/test_front_brain_provider_centralization_01.py -q: 3 passed.
- pytest tests/smoke/smoke_front_brain_agent_v2_total_operational_excellence_closeout_01.py::test_04_finalizer_imports_and_metadata_available -q: 1 passed.
- GET /v2/agent/status with local operator token succeeded.

Safety:
- No broker or real money.
- No memory/semantic mutation.
- No FAISS mutation.
- No trading mutation.
- No .env mutation.

Next recommended front: FRONT-BRAIN-HARDCODED-PATHS-ACTIVE-MODULES-02.
