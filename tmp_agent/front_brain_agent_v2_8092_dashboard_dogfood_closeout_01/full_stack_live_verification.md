# Full Stack Live Verification

## 8091 Endpoints
- **GET /health:** 200 - healthy, sessions=3, version=9.0.0
- **GET /v2/agent/status:** 200 - canonical_for_new_agent_runs=true, backend=langgraph, runs=59, primary_finalizer_model=kimi-k2.6:cloud, provider_degraded=false
- **GET /v2/agent/capabilities:** 200 - 12 planner classes, 10 capabilities, version=agent_kernel_v2.0-langgraph-compatible
- **GET /brain-dashboard/agent-v2/status:** 200 - ok=true, canonical_for_new_agent_runs=true, backend=langgraph, runs=59
- **POST /v2/chat/agent:** 200 - run_id=agv2_437724e3f34dc5b8, model_used=kimi-k2.6:cloud, provider_degraded=false

## 8092 Endpoints
- **GET /:** 200 - Brain Operator Dashboard HTML loads
- **GET /brain-dashboard/status:** 200 - dashboard=online, brain=healthy, scheduler=cached_ready, autonomy=idle
- **GET /brain-dashboard/agent-v2/status:** ❌ 404 Not Found - BLOCKED by Windows TCP socket zombie

## Blocker Status
- **Blocker closed:** false
- **Blocker type:** windows_tcp_socket_zombie
- **PID:** 183024 (nonexistent but socket remains LISTENING)
- **Root cause:** Process died but Windows TCP socket not released
- **Code status:** CORRECT - route exists in dashboard_routes.py:347
- **Workaround:** Use 8091 as canonical for Agent V2 until OS restart

## Memory/FAISS
- **semantic_memory.jsonl:** 1732 lines (unchanged)
- **faiss_ids:** 1633 (unchanged)
- **faiss_ntotal:** 1633 (unchanged)
- **Hashes:** unchanged from baseline
