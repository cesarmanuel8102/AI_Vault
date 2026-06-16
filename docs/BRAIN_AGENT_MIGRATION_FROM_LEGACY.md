# Brain Agent Migration From Legacy

Agent V2 is canonical for new agent runs via `/v2/agent/*`. Legacy `/v1/agent/*`, `/agent`, and `/chat` remain compatible. Chat remains conversational; agentic execution should create Agent V2 runs. 8092 dashboard exposes `/brain-dashboard/agent-v2/status`.
