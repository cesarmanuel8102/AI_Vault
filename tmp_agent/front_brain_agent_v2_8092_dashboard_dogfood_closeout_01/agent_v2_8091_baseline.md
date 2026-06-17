# Agent V2 8091 Baseline Verification

## Estado del Servicio 8091
- **Endpoint probado:** http://127.0.0.1:8091
- **Health:** ok=True, version=9.0.0, sessions=3
- **Agent V2 Status:** 
  - canonical_for_new_agent_runs: true
  - backend: langgraph
  - runs: 57
  - primary_finalizer_model: kimi-k2.6:cloud
  - provider_degraded: false
  - checkpointed: true
  - trace_available: true
- **Capabilities:** 12 planner classes disponibles, 10 capabilities con gateway de permisos

## Dogfood Test
- **Endpoint:** POST /v2/chat/agent
- **Run ID:** agv2_4e81f46dc2022b4b
- **Model:** kimi-k2.6:cloud
- **Provider degraded:** false
- **Trace URL:** /v2/agent/runs/agv2_4e81f46dc202b4b/trace
- **Status:** ✅ PASSED

## Veredicto
Agent V2 en 8091 está completamente operacional y listo para uso controlado.
