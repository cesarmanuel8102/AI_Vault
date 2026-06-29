# Dashboard Proxy Contract Results

**Front:** FRONT-BRAIN-AGENT-V2-BACKEND-FLAG-CONTRACT-TESTS-08D  
**Test File:** `tests/smoke/test_brain_dashboard_chat_contracts_08d.py`  
**Backend:** `native_runtime` (upstream 8091 mocked)  
**Result:** **9 passed, 0 failed**

## Summary

The 8092 dashboard chat and trace proxy contracts are pinned against mocked upstream responses. The tests verify that `dashboard_routes.py` correctly forwards requests to `127.0.0.1:8091/v2/chat/agent` and `127.0.0.1:8091/v2/agent/runs/{run_id}/trace`, and that the response mapping preserves every field consumed by `dashboard/static/app.js`.

## Verified Contracts

1. **Dashboard chat proxy** maps all required response fields:
   - `content`, `canonical_agent_v2`, `run_id`, `trace_url`
   - `classification`, `status`
   - `model_used`, `provider_used`, `provider_degraded`, `fallback_reason`, `raw_cot_exposed`
   - `mode_requested`, `mode_effective`, `auto_decision`
   - `mode_escalation_required`, `mode_escalation_reason`, `required_permission`, `expected_write_scope`, `confirmation_id`
   - `blocked_tools`
2. **Dashboard chat error shape** returns `{ok: false, error, content}` when upstream is unreachable.
3. **Dashboard trace proxy** returns `{ok, run_id, trace, event_count}` and includes `plan_created` and `run_completed` events.
4. **Dashboard agent-v2/status** returns `ok: true` with `agent_v2.backend` and `chat_agent_route: /v2/chat/agent`.
5. **Main dashboard status** includes the `agent_v2` panel with backend/runs/trace availability.
6. **Build mode escalation** is correctly mapped: `mode_escalation_required=true`, `required_permission='build'`, `confirmation_id` present, `expected_write_scope` populated.
7. **Auto mode** maps `auto_decision`.
8. **Validation** rejects empty messages with HTTP 400.
9. **Scope guard** confirms no dashboard or source files were modified.

## Notes for Future LangGraph Wiring

- The proxy itself does not need changes if `/v2/chat/agent` response is normalized.
- 8091 and 8090 must use identical backend selection logic when `AGENT_V2_BACKEND` is active, otherwise the dashboard will see a different backend than the main UI.
