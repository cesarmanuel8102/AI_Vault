# Contract Test Matrix

This matrix records the contract tests added in **FRONT-BRAIN-AGENT-V2-BACKEND-FLAG-CONTRACT-TESTS-08D**. All tests passed against the baseline `af5636b` with the default `NativeAgentRuntimeV2` backend.

## Summary

- **Total tests:** 30
- **Passed:** 30
- **Failed:** 0
- **Backends exercised:** `native` only (LangGraph not activated)
- **No source files modified**

## Tests by File

### `tests/smoke/test_brain_agent_v2_backend_flag_contracts_08d.py` (14 tests)

| Test | Contract | Result |
|------|----------|--------|
| `test_runtime_selector_default_is_native` | REQ-06 runtime fallback | passed |
| `test_no_backend_flag_wiring_exists_yet` | REQ-06 no premature wiring | passed |
| `test_v2_chat_agent_direct_assistant_contract` | REQ-01 /v2/chat/agent schema | passed |
| `test_v2_chat_agent_brain_evidence_contract` | REQ-01 /v2/chat/agent schema | passed |
| `test_v2_chat_agent_write_intent_read_only_contract` | REQ-04 read_only safe | passed |
| `test_v2_chat_agent_protected_write_contract` | REQ-04 governance metadata | passed |
| `test_v2_chat_agent_auto_mode_contract` | REQ-04 auto mode | passed |
| `test_v2_chat_agent_provider_metadata_contract` | REQ-01 provider_metadata | passed |
| `test_v2_chat_agent_error_shape_contract` | REQ-06 error shape | passed |
| `test_v2_agent_status_contract` | REQ-09 status panel | passed |
| `test_v2_agent_capabilities_contract` | REQ-09 capabilities panel | passed |
| `test_legacy_chat_contract_unchanged` | REQ-08 legacy chat | passed |
| `test_openai_compat_contract_unchanged` | REQ-08 OpenAI-compat | passed |
| `test_no_source_or_frontend_modified` | scope guard | passed |

### `tests/smoke/test_brain_dashboard_chat_contracts_08d.py` (9 tests)

| Test | Contract | Result |
|------|----------|--------|
| `test_dashboard_chat_proxy_contract` | REQ-03 dashboard chat proxy | passed |
| `test_dashboard_chat_proxy_error_shape` | REQ-03 dashboard chat error | passed |
| `test_dashboard_agent_v2_trace_proxy_contract` | REQ-03 dashboard trace proxy | passed |
| `test_dashboard_agent_v2_status_contract` | REQ-09 dashboard agent-v2 status | passed |
| `test_dashboard_status_includes_agent_v2_panel` | REQ-09 main status panel | passed |
| `test_dashboard_chat_build_mode_escalation_contract` | REQ-04 / REQ-05 build mode | passed |
| `test_dashboard_chat_auto_mode_exposes_auto_decision` | REQ-04 auto mode | passed |
| `test_dashboard_chat_message_required_validation` | REQ-03 validation | passed |
| `test_no_dashboard_source_files_modified` | scope guard | passed |

### `tests/smoke/test_brain_agent_v2_trace_contracts_08d.py` (7 tests)

| Test | Contract | Result |
|------|----------|--------|
| `test_v2_chat_agent_trace_url_resolves` | REQ-02 trace resolution | passed |
| `test_v2_agent_trace_event_schema_contract` | REQ-02 trace event schema | passed |
| `test_trace_contract_supports_dashboard_expected_sections` | REQ-02 dashboard trace filters | passed |
| `test_visual_trace_latest_endpoint_contract` | REQ-07 visual trace latest | passed |
| `test_visual_trace_stream_route_exists` | REQ-07 visual trace stream route | passed |
| `test_trace_run_root_current_native_contract` | REQ-02 trace consistency | passed |
| `test_no_source_or_frontend_modified` | scope guard | passed |

## Gaps to Address Before AGENT_V2_BACKEND Wiring

1. LangGraph missing `expected_write_scope` and `auto_decision`.
2. LangGraph trace event types differ from Native dashboard filters.
3. LangGraph default `run_root` differs from Native `RUN_ROOT`.
4. Runtime selector must guard against LangGraph package unavailability.
