# Endpoint Health Matrix — 08F8

| Endpoint | Method | Expected | Actual | Summary | backend_selected | fallback_used | Result |
|---|---|---|---|---|---|---|---|
| /health | GET | 200 | 200 | healthy | langgraph_parity | False | PASS |
| /v2/agent/status | GET | 200 | 200 | langgraph_parity default active | langgraph_parity | False | PASS |
| /v2/chat/agent | POST | 200 | 200 | canonical_agent_v2 response with trace_url | langgraph_parity | False | PASS |
| /v2/agent/capabilities | GET | 200 | 500 | AttributeError: LangGraphParityRuntimeV2 missing list_capabilities | None | None | FAIL |
| /ui/ | GET | 200 | 200 | Brain Chat V9 HTML served | None | None | PASS |
| /v2/agent/runs/{run_id}/trace | GET | 200 | 200 | trace events returned | langgraph_parity | False | PASS |

