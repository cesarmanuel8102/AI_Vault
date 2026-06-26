from __future__ import annotations
from .native_runtime import NativeAgentRuntimeV2

_runtime = NativeAgentRuntimeV2()

def get_agent_runtime_v2():
    return _runtime
