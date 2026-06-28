# Runtime Probe Results

## import_structure

```json

{
  "total_routes": 251,
  "chat_routes": [
    {
      "path": "/v1/chat/completions",
      "methods": [
        "POST"
      ]
    },
    {
      "path": "/v2/chat/agent",
      "methods": [
        "POST"
      ]
    },
    {
      "path": "/chat/introspectivo/debug",
      "methods": [
        "GET"
      ]
    },
    {
      "path": "/chat/introspectivo",
      "methods": [
        "POST"
      ]
    },
    {
      "path": "/chat",
      "methods": [
        "POST"
      ]
    },
    {
      "path": "/brain/chat_excellence/status",
      "methods": [
        "GET"
      ]
    },
    {
      "path": "/brain/chat_excellence/proposals",
      "methods": [
        "GET"
      ]
    },
    {
      "path": "/brain/chat_excellence/proposals/{proposal_id}",
      "methods": [
        "GET"
      ]
    },
    {
      "path": "/brain/chat_excellence/proposals/{proposal_id}/reject",
      "methods": [
        "POST"
      ]
    },
    {
      "path": "/brain/chat_excellence/proposals/{proposal_id}/dry_run",
      "methods": [
        "POST"
      ]
    },
    {
      "path": "/brain/chat_excellence/proposals/{proposal_id}/apply",
      "methods": [
        "POST"
      ]
    },
    {
      "path": "/brain/chat_excellence/proposals/{proposal_id}/rollback",
      "methods": [
        "POST"
      ]
    },
    {
      "path": "/brain/chat_excellence/proposals/{proposal_id}/health_gate_log",
      "methods": [
        "GET"
      ]
    },
    {
      "path": "/brain/chat_excellence/proposals/apply_batch",
      "methods": [
        "POST"
      ]
    },
    {
      "path": "/brain/chat_excellence/proposals/evaluate",
      "methods": [
        "POST"
      ]
    },
    {
      "path": "/brain/chat_excellence/proposals/{proposal_id}/evaluation_status",
      "methods": [
        "GET"
      ]
    },
    {
      "path": "/brain/chat-product/status",
      "methods": [
        "GET"
      ]
    },
    {
      "path": "/brain/chat-product/refresh",
      "methods": [
        "POST"
      ]
    }
  ],
  "agent_routes": [
    {
      "path": "/v2/agent/capabilities",
      "methods": [
        "GET"
      ]
    },
    {
      "path": "/v2/agent/status",
      "methods": [
        "GET"
      ]
    },
    {
      "path": "/v2/agent/runs",
      "methods": [
        "GET"
      ]
    },
    {
      "path": "/v2/agent/runs",
      "methods": [
        "POST"
      ]
    },
    {
      "path": "/v2/agent/runs/{run_id}",
      "methods": [
        "GET"
      ]
    },
    {
      "path": "/v2/agent/runs/{run_id}/plan",
      "methods": [
        "POST"
      ]
    },
    {
      "path": "/v2/agent/runs/{run_id}/execute",
      "methods": [
        "POST"
      ]
    },
    {
      "path": "/v2/agent/runs/{run_id}/pause",
      "methods": [
        "POST"
      ]
    },
    {
      "path": "/v2/agent/runs/{run_id}/resume",
      "methods": [
        "POST"
      ]
    },
    {
      "path": "/v2/agent/runs/{run_id}/cancel",
      "methods": [
        "POST"
      ]
    },
    {
      "path": "/v2/agent/runs/{run_id}/trace",
      "methods": [
        "GET"
      ]
    },
    {
      "path": "/v2/agent/operator-presets",
      "methods": [
        "GET"
      ]
    },
    {
      "path": "/v2/agent/maintenance/modes",
      "methods": [
        "GET"
      ]
    },
    {
      "path": "/v2/chat/agent",
      "methods": [
        "POST"
      ]
    },
    {
      "path": "/v1/agent/healthz",
      "methods": [
        "GET"
      ]
    },
    {
      "path": "/v1/agent/status",
      "methods": [
        "GET"
      ]
    },
    {
      "path": "/brain-dashboard/agent-v2/status",
      "methods": [
        "GET"
      ]
    },
    {
      "path": "/agent",
      "methods": [
        "POST"
      ]
    },
    {
      "path": "/brain/agent-trace/event",
      "methods": [
        "POST"
      ]
    },
    {
      "path": "/brain/agent-trace/latest",
      "methods": [
        "GET"
      ]
    },
    {
      "path": "/brain/agent-trace/stream",
      "methods": [
        "GET"
      ]
    }
  ],
  "gate_routes": [
    {
      "path": "/gate/approve/{pending_id}",
      "methods": [
        "POST"
      ]
    },
    {
      "path": "/gate/reject/{pending_id}",
      "methods": [
        "POST"
      ]
    },
    {
      "path": "/brain/health_gate/status",
      "methods": [
        "GET"
      ]
    },
    {
      "path": "/brain/chat_excellence/proposals/{proposal_id}/health_gate_log",
      "methods": [
        "GET"
      ]
    },
    {
      "path": "/brain/strategy-engine/simulation-gate/{strategy_id}",
      "methods": [
        "POST"
      ]
    }
  ],
  "openai_routes": [
    {
      "path": "/v1/chat/completions",
      "methods": [
        "POST"
      ]
    }
  ]
}

```

## langgraph_detection

```json

{
  "langgraph_runtime_exists": true,
  "LangGraphAgentRuntimeV2_class": true,
  "StateGraph_imported": true
}

```

## runtime_selector

```json

{
  "runtime_importable": true,
  "returned_class": "NativeAgentRuntimeV2",
  "returned_module": "brain_v9.core.agent_kernel_v2.native_runtime",
  "is_native": true,
  "is_langgraph": false
}

```

## legacy_chat_path

```json

{
  "chat_endpoint_exists": true,
  "calls_handle_user_message": true,
  "imports_router_entrypoint": true
}

```

## v2_chat_agent

```json

{
  "chat_agent_endpoint_exists": true,
  "uses_get_agent_runtime_v2": true,
  "calls_execute_run": true,
  "no_langgraph_instantiation": true
}

```

## openai_compat

```json

{
  "endpoint_exists": true,
  "imports_handle_user_message": true,
  "calls_handle_user_message": true,
  "no_v2_runtime_import": true
}

```

## gate_approve

```json

{
  "gate_approve_exists": true,
  "has_approval_token_param": true,
  "calls_gate_approve_with_token": true,
  "fails_closed_on_none": true,
  "checks_signed_approval_validated": true,
  "strips_token_from_response": true
}

```

## memory_gateway_v2

```json

{
  "importable": true,
  "MemoryGatewayV2_class": true,
  "semantic_retrieve_method": true
}

```

## tool_gateway_v2

```json

{
  "importable": true,
  "ToolGatewayV2_class": true,
  "call_method": true
}

```

## signed_approvals

```json

{
  "importable": true,
  "create_approval_token": true,
  "verify_approval_token": true,
  "TEST_SECRET": true
}

```

## visual_trace

```json

{
  "emit_agent_trace_internal": true,
  "append_trace_event": true,
  "trace_store_class_exists": true
}

```

## no_mutations

```json

{
  "no_forbidden_patterns_in_probes": true,
  "forbidden_found_in_probes": [],
  "note": "Test battery data contains these terms as test cases, which is expected"
}

```
