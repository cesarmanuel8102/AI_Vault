from __future__ import annotations
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


STATUSES = {"created", "planned", "running", "waiting_approval", "paused", "failed", "completed", "cancelled"}
MODES = {"read_only", "build", "auto"}
LEGACY_MODE_MAP = {"dry_run": "read_only", "approval_required": "build", "write_allowed": "build"}
TRACE_EVENT_TAXONOMY = frozenset(
    {
        "approval_required",
        "capability_metadata_node",
        "context_assembly_node",
        "end_node",
        "evaluator_node",
        "evidence_routing_node",
        "final_answer_created",
        "finalizer_node",
        "governance_gate_node",
        "intent_node",
        "intent_route",
        "invalid_transition",
        "memory_retrieval_completed",
        "memory_retrieval_node",
        "memory_retrieval_started",
        "mode_escalation_detected",
        "native_helper_error",
        "plan_created",
        "planner_node",
        "repair_or_replan_node",
        "result_normalization_node",
        "run_cancelled",
        "run_completed",
        "run_created",
        "run_failed",
        "run_paused",
        "run_resumed",
        "start_node",
        "tool_call_completed",
        "tool_call_started",
        "tool_execution_node",
        "tool_execution_summary",
    }
)


@dataclass
class AgentStep:
    step_id: str
    kind: str
    title: str
    status: str = "created"
    tool_name: Optional[str] = None
    input: Dict[str, Any] = field(default_factory=dict)
    output: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentRun:
    run_id: str
    goal: str
    mode: str = "read_only"
    user_id: str = "local"
    status: str = "created"
    created_utc: str = field(default_factory=utc_now)
    updated_utc: str = field(default_factory=utc_now)
    plan: List[Dict[str, Any]] = field(default_factory=list)
    final_answer: Optional[str] = None
    provider: str = "structured_operational_finalizer"
    safety_flags: List[str] = field(default_factory=list)


@dataclass
class AgentTraceEvent:
    event_type: str
    run_id: str
    timestamp_utc: str = field(default_factory=utc_now)
    event_id: str = field(default_factory=lambda: "trace_" + uuid4().hex)
    correlation_id: Optional[str] = None
    schema_version: int = 1
    step_id: Optional[str] = None
    message: str = ""
    data: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.correlation_id is None:
            self.correlation_id = self.run_id


@dataclass
class ToolCallRequest:
    tool_name: str
    args: Dict[str, Any] = field(default_factory=dict)
    mode: str = "read_only"
    approval_token: Optional[str] = None


@dataclass
class ToolCallResult:
    tool_name: str
    ok: bool
    result: Dict[str, Any] = field(default_factory=dict)
    blocked: bool = False
    approval_required: bool = False
    error: Optional[str] = None


@dataclass
class AgentApprovalRequest:
    run_id: str
    tool_name: str
    reason: str
    required_mode: str = "approval_required"


@dataclass
class AgentFinalResult:
    run_id: str
    status: str
    final_answer: str
    trace_events: int
    safety_flags: List[str] = field(default_factory=list)


@dataclass
class AgentCapability:
    name: str
    description: str
    risk_level: str
    read_only: bool
    requires_approval: bool
    allowed_modes: List[str]


@dataclass
class AgentError:
    code: str
    message: str
    safe_detail: str = ""


@dataclass
class AgentCheckpoint:
    run_id: str
    status: str
    updated_utc: str
    step_index: int = 0
    data: Dict[str, Any] = field(default_factory=dict)


def to_dict(obj: Any) -> Dict[str, Any]:
    if hasattr(obj, "__dataclass_fields__"):
        return asdict(obj)
    if isinstance(obj, dict):
        return obj
    raise TypeError(f"Unsupported schema object: {type(obj)!r}")
