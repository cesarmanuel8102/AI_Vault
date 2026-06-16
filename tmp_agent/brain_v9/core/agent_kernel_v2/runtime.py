from __future__ import annotations
try:
    from .langgraph_runtime import LangGraphAgentRuntimeV2
    _runtime = LangGraphAgentRuntimeV2()
    if not getattr(_runtime, "graph_available", False):
        raise RuntimeError(getattr(_runtime, "graph_error", "langgraph_unavailable"))
    LANGGRAPH_USED = True
    LANGGRAPH_BLOCKER = None
except Exception as exc:
    from .native_runtime import NativeAgentRuntimeV2
    _runtime = NativeAgentRuntimeV2()
    LANGGRAPH_USED = False
    LANGGRAPH_BLOCKER = str(exc)


def get_agent_runtime_v2():
    return _runtime
