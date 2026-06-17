# Contaminated Commit Inventory — 52e83ec

## Summary

Commit `52e83ec` was intended as a corrective patch for FRONT-BRAIN-AGENT-V2-CHAT-MODE-SWITCH-READ-BUILD-AUTO-01.
It contained **12 intended files**, **827 suspect files**, and **2 protected files**.

## Intended Files (12)

| Status | Path |
|--------|------|
| M | tmp_agent/brain_v9/ui/index.html |
| M | tmp_agent/brain_v9/dashboard/static/index.html |
| M | tmp_agent/brain_v9/dashboard/static/app.js |
| M | tmp_agent/brain_v9/dashboard/dashboard_routes.py |
| M | tmp_agent/brain_v9/core/agent_kernel_v2/tool_gateway.py |
| M | tmp_agent/brain_v9/core/agent_kernel_v2/governance.py |
| M | tmp_agent/brain_v9/core/agent_kernel_v2/api_adapter.py |
| A | tmp_agent/front_brain_agent_v2_chat_mode_switch_read_build_auto_01/corrective_state_lock.json |
| A | tmp_agent/front_brain_agent_v2_chat_mode_switch_read_build_auto_01/corrective_smoke_results.json |
| A | tmp_agent/front_brain_agent_v2_chat_mode_switch_read_build_auto_01/corrective_memory_faiss_final.json |
| A | tmp_agent/front_brain_agent_v2_chat_mode_switch_read_build_auto_01/corrective_visual_surface_audit.md |
| A | tmp_agent/front_brain_agent_v2_chat_mode_switch_read_build_auto_01/post_push_verification.json |

## Suspect Files (827) — Sample

Unrelated front artifacts, runtime files, old evidence, etc. Full list in `contaminated_commit_inventory.json`.
Examples:
- tmp_agent/control/RUN_ONCE
- tmp_agent/front_brain_agent_v2_spanish_parser_preflight_closeout_01/post_push_verification.json
- tmp_agent/front_brain_autonomous_observer_reports_01/final_report.json
- tmp_agent/front_brain_llm_provider_chain_optimization_01/*
- ...and hundreds more

## Protected Files (2) — CRITICAL

| Status | Path | Details |
|--------|------|---------|
| M | memory/autonomous_journal.jsonl | +18 lines from persistent_run_once cycles |
| M | memory/semantic/semantic_memory.jsonl | +1 line (task_result entry) |

## Why Cleanup Was Stopped

Per governance rules, any commit that modifies `memory/autonomous_journal.jsonl` or `memory/semantic/semantic_memory.jsonl` requires explicit operator approval before cleanup can proceed. Automated cleanup is forbidden.
