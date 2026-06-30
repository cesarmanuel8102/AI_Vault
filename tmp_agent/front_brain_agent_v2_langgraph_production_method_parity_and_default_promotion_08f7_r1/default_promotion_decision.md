# Default promotion decision

Decision: `PROMOTE_LANGGRAPH_TO_AGENT_V2_DEFAULT`.

LangGraph is default for Agent V2 when `AGENT_V2_BACKEND` is unset. Native remains rollback via `AGENT_V2_BACKEND=native`. Trading/broker autonomy remains disconnected.
