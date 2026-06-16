# Brain Agent Kernel V2

Agent V2 is canonical for new agentic operations. It stores each run under `tmp_agent/agent_kernel_v2/runs/{run_id}/` with `run.json`, `checkpoint.json`, and `trace.jsonl`. Backend is LangGraph when available, with native graph-compatible fallback.
