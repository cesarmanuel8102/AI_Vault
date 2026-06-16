from __future__ import annotations
from typing import Any, Dict
from .native_runtime import NativeAgentRuntimeV2


class LangGraphAgentRuntimeV2(NativeAgentRuntimeV2):
    backend = "langgraph"

    def __init__(self):
        super().__init__()
        self.graph_available = False
        try:
            from langgraph.graph import END, START, StateGraph
            graph = StateGraph(dict)
            graph.add_node("plan", lambda s: {**s, "planned": True})
            graph.add_node("retrieve", lambda s: {**s, "retrieved": True})
            graph.add_node("tools", lambda s: {**s, "tools_checked": True})
            graph.add_node("final", lambda s: {**s, "finalized": True})
            graph.add_edge(START, "plan")
            graph.add_edge("plan", "retrieve")
            graph.add_edge("retrieve", "tools")
            graph.add_edge("tools", "final")
            graph.add_edge("final", END)
            self.graph = graph.compile()
            self.graph_available = True
        except Exception as exc:
            self.graph_error = str(exc)

    def graph_probe(self) -> Dict[str, Any]:
        if not self.graph_available:
            return {"ok": False, "backend": self.backend, "error": getattr(self, "graph_error", "unknown")}
        out = self.graph.invoke({"probe": True})
        return {"ok": True, "backend": self.backend, "out": out}
