# OpenAPI / Route Discovery

Generated: 2026-06-12T04:17:18.576720+00:00

- openapi_available: True
- route_count: 225
- openai_compatible_endpoint_exists: False

## Likely chat routes
- http://127.0.0.1:8090 ['post'] /upgrade/aos/execute
- http://127.0.0.1:8090 ['get'] /v1/agent/healthz
- http://127.0.0.1:8090 ['get'] /v1/agent/status
- http://127.0.0.1:8090 ['get'] /chat/introspectivo/debug
- http://127.0.0.1:8090 ['post'] /chat/introspectivo
- http://127.0.0.1:8090 ['post'] /chat
- http://127.0.0.1:8090 ['post'] /tool01/permission/approve
- http://127.0.0.1:8090 ['get'] /tool01/permission/pending/{session_id}
- http://127.0.0.1:8090 ['get'] /tool01/permission/grants/{session_id}
- http://127.0.0.1:8090 ['get'] /brain/chat_excellence/status
- http://127.0.0.1:8090 ['get'] /brain/chat_excellence/proposals
- http://127.0.0.1:8090 ['get'] /brain/chat_excellence/proposals/{proposal_id}
- http://127.0.0.1:8090 ['post'] /brain/chat_excellence/proposals/{proposal_id}/reject
- http://127.0.0.1:8090 ['post'] /brain/chat_excellence/proposals/{proposal_id}/dry_run
- http://127.0.0.1:8090 ['post'] /brain/chat_excellence/proposals/{proposal_id}/apply
- http://127.0.0.1:8090 ['post'] /brain/chat_excellence/proposals/{proposal_id}/rollback
- http://127.0.0.1:8090 ['get'] /brain/chat_excellence/proposals/{proposal_id}/health_gate_log
- http://127.0.0.1:8090 ['post'] /brain/chat_excellence/proposals/apply_batch
- http://127.0.0.1:8090 ['post'] /brain/chat_excellence/proposals/evaluate
- http://127.0.0.1:8090 ['get'] /brain/chat_excellence/proposals/{proposal_id}/evaluation_status
- http://127.0.0.1:8090 ['post'] /brain/autonomy/execute-top-action
- http://127.0.0.1:8090 ['get'] /brain/chat-product/status
- http://127.0.0.1:8090 ['post'] /brain/chat-product/refresh
- http://127.0.0.1:8090 ['post'] /brain/learning/proposals/{proposal_id}/evaluate
- http://127.0.0.1:8090 ['get'] /brain/strategy-engine/adaptation-state
- http://127.0.0.1:8090 ['post'] /brain/strategy-engine/execute-top-candidate
- http://127.0.0.1:8090 ['post'] /brain/strategy-engine/execute-candidate/{strategy_id}
- http://127.0.0.1:8090 ['post'] /brain/strategy-engine/execute-batch/{strategy_id}
- http://127.0.0.1:8090 ['post'] /brain/strategy-engine/execute-comparison-cycle
- http://127.0.0.1:8090 ['post'] /agent
- http://127.0.0.1:8090 ['post'] /brain/agent-trace/event
- http://127.0.0.1:8090 ['get'] /brain/agent-trace/latest
- http://127.0.0.1:8090 ['get'] /brain/agent-trace/stream
