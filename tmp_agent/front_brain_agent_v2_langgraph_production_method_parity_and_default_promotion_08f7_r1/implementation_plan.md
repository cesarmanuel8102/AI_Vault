# Implementation plan

- Implement guarded plan_run/pause_run/resume_run/cancel_run parity
- Keep create_run/execute_run/list_runs/get_run/get_trace intact
- Promote LangGraph as default when AGENT_V2_BACKEND is unset
- Preserve AGENT_V2_BACKEND=native rollback
- Fallback to Native with metadata on LangGraph init/contract failure
- Expose backend_default/runtime_type/fallback metadata in Agent V2 responses
- Run focused/regression/hygiene validations before explicit staging
