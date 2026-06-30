# Rollback validation

- `AGENT_V2_BACKEND=native` selects `NativeAgentRuntimeV2`.
- LangGraph construction failure falls back to Native with fallback metadata.
- Rollback requires no code, git, memory, FAISS, or trading changes.
