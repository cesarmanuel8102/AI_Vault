"""
Authoritative fail-closed governance gate for Brain V9.

This module is intentionally pure at the decision point: it performs no writes
and does not execute the requested operation. Callers must evaluate here before
touching governance, execution, patch, dev, lifecycle, or approval paths.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Mapping, Optional
from uuid import uuid4

from brain_v9.governance.protected_paths import classify_path_protection, is_protected_path


SCHEMA_VERSION = "unified_governance_gate_v1"
DEFAULT_DECISION_TTL_SECONDS = 300
GOVERNED_OPERATION_CLASSES = frozenset(
    {"governance", "execution", "patch", "dev", "lifecycle", "approval", "read"}
)
KNOWN_RISK_LEVELS = frozenset({"P0", "P1", "P2", "P3"})
FORBIDDEN_TARGET_TOKENS = (
    ".env",
    ".github/",
    "memory/",
    "memory/semantic/",
    "memory/rollback",
    "financial_autonomy/",
    "tmp_agent/state/",
    "scripts/",
    "tmp_agent/brain_v9/trading/",
    "trading/",
    "c:/ai_vault_canonical",
    "/ai_vault_canonical",
)
FORBIDDEN_REQUEST_FIELDS = frozenset(
    {
        "god",
        "god_mode",
        "safe_mode",
        "override_governance",
        "bypass_auth",
        "bypass_rbac",
        "auto_merge",
        "force_merge",
        "live_trading",
        "real_money",
        "canonical_sync",
    }
)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _utc_text(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_utc(value: Any) -> Optional[datetime]:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def normalize_risk_level(value: Any) -> str:
    text = str(value or "P1").strip().upper()
    if text in KNOWN_RISK_LEVELS:
        return text
    if text in {"LOW", "READ", "READ_ONLY"}:
        return "P0"
    if text in {"MEDIUM", "WRITE", "SANDBOX"}:
        return "P1"
    if text in {"HIGH", "SERVICE"}:
        return "P2"
    if text in {"CRITICAL", "DESTRUCTIVE"}:
        return "P3"
    return "P3"


def normalize_mode(value: Any) -> str:
    text = str(value or "read_only").strip().lower()
    if text in {"read_only", "dry_run", "plan"}:
        return "read_only"
    if text in {"build", "write_allowed", "approval_required"}:
        return "build"
    if text == "auto":
        return "auto"
    return "read_only"


def _normalize_path(value: Any) -> str:
    return str(value or "").replace("\\", "/").strip().lower()


def _extract_target(args: Mapping[str, Any], explicit_target: str = "") -> str:
    if explicit_target:
        return str(explicit_target)
    for key in (
        "path",
        "file",
        "filepath",
        "file_path",
        "target",
        "destination",
        "dest",
        "src",
        "source",
        "cmd",
        "command",
    ):
        value = args.get(key)
        if isinstance(value, str) and value:
            return value
    return ""


def _has_forbidden_request_field(args: Mapping[str, Any]) -> Optional[str]:
    for key in args.keys():
        lower = str(key).strip().lower()
        if lower in FORBIDDEN_REQUEST_FIELDS:
            return lower
    return None


def _target_has_forbidden_token(target: str) -> Optional[str]:
    normalized = _normalize_path(target)
    if not normalized:
        return None
    for token in FORBIDDEN_TARGET_TOKENS:
        if token in normalized:
            return token
    return None


def _legacy_approval_valid(token: Optional[str]) -> bool:
    return bool(token and str(token).startswith("AGENTV2_APPROVED_"))


@dataclass(frozen=True)
class UnifiedGateRequest:
    operation_class: str
    operation: str
    mode: str = "read_only"
    risk_level: str = "P1"
    actor: str = "agent"
    role: str = "viewer"
    target: str = ""
    args: Dict[str, Any] = field(default_factory=dict)
    approval_token: Optional[str] = None
    authenticated: bool = False
    context: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class UnifiedGateDecision:
    schema_version: str
    decision_id: str
    generated_utc: str
    expires_utc: str
    operation_class: str
    operation: str
    allowed: bool
    blocked: bool
    approval_required: bool
    risk_level: str
    action: str
    reason: str
    error: Optional[str] = None
    fail_closed: bool = False
    human_final_authority: bool = True
    live_trading_disabled: bool = True
    real_money_disabled: bool = True
    canonical_sync_disabled: bool = True
    auto_merge_disabled: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def fail_closed_decision(
    reason_code: str,
    *,
    operation_class: str = "governance",
    operation: str = "unknown",
    risk_level: str = "P3",
    reason: str = "",
    approval_required: bool = False,
    metadata: Optional[Dict[str, Any]] = None,
) -> UnifiedGateDecision:
    now = utc_now()
    return UnifiedGateDecision(
        schema_version=SCHEMA_VERSION,
        decision_id=f"gate_{uuid4().hex}",
        generated_utc=_utc_text(now),
        expires_utc=_utc_text(now + timedelta(seconds=DEFAULT_DECISION_TTL_SECONDS)),
        operation_class=operation_class if operation_class in GOVERNED_OPERATION_CLASSES else "governance",
        operation=operation or "unknown",
        allowed=False,
        blocked=True,
        approval_required=approval_required,
        risk_level=normalize_risk_level(risk_level),
        action="blocked",
        reason=reason or reason_code,
        error=reason_code,
        fail_closed=True,
        metadata=metadata or {},
    )


def _decision(
    req: UnifiedGateRequest,
    *,
    allowed: bool,
    action: str,
    reason: str,
    error: Optional[str] = None,
    approval_required: bool = False,
    fail_closed: bool = False,
    metadata: Optional[Dict[str, Any]] = None,
) -> UnifiedGateDecision:
    now = utc_now()
    return UnifiedGateDecision(
        schema_version=SCHEMA_VERSION,
        decision_id=f"gate_{uuid4().hex}",
        generated_utc=_utc_text(now),
        expires_utc=_utc_text(now + timedelta(seconds=DEFAULT_DECISION_TTL_SECONDS)),
        operation_class=req.operation_class,
        operation=req.operation,
        allowed=allowed,
        blocked=not allowed,
        approval_required=approval_required,
        risk_level=normalize_risk_level(req.risk_level),
        action=action,
        reason=reason,
        error=error,
        fail_closed=fail_closed,
        metadata=metadata or {},
    )


class UnifiedGovernanceGate:
    """Single policy surface for all governed runtime decisions."""

    def evaluate(self, request: UnifiedGateRequest | Mapping[str, Any]) -> UnifiedGateDecision:
        try:
            req = self._coerce_request(request)
        except Exception as exc:
            return fail_closed_decision(
                "gate_request_malformed",
                reason=f"Gate request malformed: {type(exc).__name__}",
                metadata={"exception": str(exc)[:200]},
            )

        try:
            return self._evaluate(req)
        except Exception as exc:
            return fail_closed_decision(
                "gate_unavailable",
                operation_class=req.operation_class,
                operation=req.operation,
                risk_level=req.risk_level,
                reason=f"Gate evaluation unavailable: {type(exc).__name__}",
                metadata={"exception": str(exc)[:200]},
            )

    def _coerce_request(self, request: UnifiedGateRequest | Mapping[str, Any]) -> UnifiedGateRequest:
        if isinstance(request, UnifiedGateRequest):
            return request
        if not isinstance(request, Mapping):
            raise TypeError("request must be a mapping or UnifiedGateRequest")
        return UnifiedGateRequest(
            operation_class=str(request.get("operation_class", "")),
            operation=str(request.get("operation", "")),
            mode=str(request.get("mode", "read_only")),
            risk_level=str(request.get("risk_level", "P1")),
            actor=str(request.get("actor", "agent")),
            role=str(request.get("role", "viewer")),
            target=str(request.get("target", "")),
            args=dict(request.get("args") or {}),
            approval_token=request.get("approval_token"),
            authenticated=bool(request.get("authenticated", False)),
            context=dict(request.get("context") or {}),
        )

    def _evaluate(self, req: UnifiedGateRequest) -> UnifiedGateDecision:
        operation_class = str(req.operation_class or "").strip().lower()
        operation = str(req.operation or "").strip()
        args = req.args if isinstance(req.args, dict) else {}
        risk = normalize_risk_level(req.risk_level)
        mode = normalize_mode(req.mode)
        target = _extract_target(args, req.target)
        role = str(req.role or "viewer").lower()

        normalized_req = UnifiedGateRequest(
            operation_class=operation_class,
            operation=operation,
            mode=mode,
            risk_level=risk,
            actor=req.actor,
            role=role,
            target=target,
            args=args,
            approval_token=req.approval_token,
            authenticated=req.authenticated,
            context=req.context,
        )

        if operation_class not in GOVERNED_OPERATION_CLASSES or not operation:
            return fail_closed_decision(
                "gate_request_malformed",
                operation_class=operation_class or "governance",
                operation=operation or "unknown",
                risk_level=risk,
                reason="Missing or unknown governed operation.",
            )

        forbidden_field = _has_forbidden_request_field(args)
        if forbidden_field:
            return _decision(
                normalized_req,
                allowed=False,
                action="blocked",
                error="forbidden_request_field",
                fail_closed=True,
                reason=f"Forbidden governance bypass field present: {forbidden_field}.",
                metadata={"field": forbidden_field},
            )

        forbidden_target = _target_has_forbidden_token(target)
        if forbidden_target:
            return _decision(
                normalized_req,
                allowed=False,
                action="blocked",
                error="forbidden_target",
                fail_closed=True,
                reason=f"Target is outside the governed allow surface: {forbidden_target}.",
                metadata={"target": target, "matched": forbidden_target},
            )

        if any(bool(args.get(flag)) for flag in ("live_trading", "real_money", "canonical_sync", "auto_merge")):
            return _decision(
                normalized_req,
                allowed=False,
                action="blocked",
                error="disabled_invariant_requested",
                fail_closed=True,
                reason="Live trading, real money, canonical sync, and auto-merge remain disabled.",
            )

        if risk == "P3":
            return _decision(
                normalized_req,
                allowed=False,
                action="blocked",
                error="p3_denied",
                approval_required=True,
                reason="P3 operations require explicit human approval and are never auto-approved.",
            )

        if target and is_protected_path(target):
            protection = classify_path_protection(target)
            governance_approved = (
                str(args.get("governance_token", "")) == "AGENTV2_APPROVED_GOVERNANCE_CHANGE"
                and str(args.get("confirm_phrase", "")) == "APPROVE_GOVERNANCE_SECURITY_CHANGE"
            )
            if not governance_approved:
                return _decision(
                    normalized_req,
                    allowed=False,
                    action="blocked",
                    error="governance_file_modification_denied_by_default",
                    approval_required=True,
                    fail_closed=True,
                    reason="Protected governance/security target denied by default.",
                    metadata={"target": target, "protection": protection},
                )

        if operation_class == "approval":
            if not _legacy_approval_valid(req.approval_token):
                return _decision(
                    normalized_req,
                    allowed=False,
                    action="blocked",
                    error="approval_required",
                    approval_required=True,
                    reason="Approval operation requires a valid approval token.",
                )
            return _decision(normalized_req, allowed=True, action="allow", reason="Approval token accepted.")

        if operation_class == "patch":
            dry_run = bool(args.get("dry_run", False)) or operation.endswith("_dry_run")
            if dry_run:
                return _decision(normalized_req, allowed=True, action="allow", reason="Patch dry run allowed.")
            if mode != "build":
                return _decision(
                    normalized_req,
                    allowed=False,
                    action="blocked",
                    error="build_mode_required",
                    approval_required=True,
                    reason="Patch apply requires build mode.",
                )
            if req.authenticated and role in {"operator", "admin"}:
                return _decision(normalized_req, allowed=True, action="allow", reason="Authenticated patch operation allowed.")
            if not _legacy_approval_valid(req.approval_token or args.get("approval_token")):
                return _decision(
                    normalized_req,
                    allowed=False,
                    action="blocked",
                    error="approval_required",
                    approval_required=True,
                    reason="Patch apply requires explicit approval.",
                )
            return _decision(normalized_req, allowed=True, action="allow", reason="Approved patch operation.")

        if operation_class == "dev":
            if bool(args.get("enable_dev_endpoint", False)) and not bool(req.context.get("unsafe_dev_endpoints_enabled", False)):
                return _decision(
                    normalized_req,
                    allowed=False,
                    action="blocked",
                    error="dev_endpoint_disabled",
                    fail_closed=True,
                    reason="Unsafe dev endpoints are disabled.",
                )
            if role not in {"operator", "admin"} or not req.authenticated:
                return _decision(
                    normalized_req,
                    allowed=False,
                    action="blocked",
                    error="operator_authentication_required",
                    approval_required=True,
                    reason="Dev operation requires authenticated operator authority.",
                )
            return _decision(normalized_req, allowed=True, action="allow", reason="Authenticated dev operation allowed.")

        if operation_class in {"governance", "lifecycle", "execution"}:
            if risk == "P2" and mode in {"read_only", "auto"} and not req.authenticated:
                return _decision(
                    normalized_req,
                    allowed=False,
                    action="blocked",
                    error="approval_required",
                    approval_required=True,
                    reason="P2 operation requires operator authentication or explicit approval.",
                )
            return _decision(normalized_req, allowed=True, action="allow", reason="Operation allowed by unified gate.")

        return _decision(normalized_req, allowed=True, action="allow", reason="Read operation allowed.")


_gate_instance: Optional[UnifiedGovernanceGate] = None


def get_unified_governance_gate() -> UnifiedGovernanceGate:
    global _gate_instance
    if _gate_instance is None:
        _gate_instance = UnifiedGovernanceGate()
    return _gate_instance


def validate_gate_decision(
    decision: Any,
    *,
    max_age_seconds: int = DEFAULT_DECISION_TTL_SECONDS,
) -> UnifiedGateDecision:
    if decision is None:
        return fail_closed_decision("missing_gate_decision", reason="Gate decision is missing.")
    if isinstance(decision, UnifiedGateDecision):
        data = decision.to_dict()
    elif isinstance(decision, Mapping):
        data = dict(decision)
    else:
        return fail_closed_decision("malformed_gate_decision", reason="Gate decision has invalid type.")

    required = {
        "schema_version",
        "decision_id",
        "generated_utc",
        "expires_utc",
        "operation_class",
        "operation",
        "allowed",
        "blocked",
        "approval_required",
        "risk_level",
        "action",
        "reason",
        "human_final_authority",
    }
    missing = sorted(k for k in required if k not in data)
    if missing:
        return fail_closed_decision(
            "malformed_gate_decision",
            reason=f"Gate decision missing required fields: {', '.join(missing)}.",
            metadata={"missing": missing},
        )

    if data.get("schema_version") != SCHEMA_VERSION:
        return fail_closed_decision("invalid_gate_decision", reason="Gate decision schema is invalid.")
    if not isinstance(data.get("allowed"), bool) or not isinstance(data.get("blocked"), bool):
        return fail_closed_decision("invalid_gate_decision", reason="Gate decision booleans are invalid.")
    if bool(data.get("allowed")) == bool(data.get("blocked")):
        return fail_closed_decision("invalid_gate_decision", reason="Gate decision allow/block state is inconsistent.")
    if data.get("human_final_authority") is not True:
        return fail_closed_decision("invalid_gate_decision", reason="Gate decision does not preserve human final authority.")

    generated = _parse_utc(data.get("generated_utc"))
    expires = _parse_utc(data.get("expires_utc"))
    now = utc_now()
    if not generated or not expires:
        return fail_closed_decision("malformed_gate_decision", reason="Gate decision timestamps are malformed.")
    if generated < now - timedelta(seconds=max_age_seconds) or expires < now:
        return fail_closed_decision("stale_gate_decision", reason="Gate decision is stale or expired.")

    risk = normalize_risk_level(data.get("risk_level"))
    if bool(data.get("allowed")) and risk == "P3":
        return fail_closed_decision("p3_denied", approval_required=True, reason="Invalid allowed P3 decision rejected.")

    try:
        return UnifiedGateDecision(
            schema_version=str(data["schema_version"]),
            decision_id=str(data["decision_id"]),
            generated_utc=str(data["generated_utc"]),
            expires_utc=str(data["expires_utc"]),
            operation_class=str(data["operation_class"]),
            operation=str(data["operation"]),
            allowed=bool(data["allowed"]),
            blocked=bool(data["blocked"]),
            approval_required=bool(data["approval_required"]),
            risk_level=risk,
            action=str(data["action"]),
            reason=str(data["reason"]),
            error=data.get("error"),
            fail_closed=bool(data.get("fail_closed", False)),
            human_final_authority=True,
            live_trading_disabled=bool(data.get("live_trading_disabled", True)),
            real_money_disabled=bool(data.get("real_money_disabled", True)),
            canonical_sync_disabled=bool(data.get("canonical_sync_disabled", True)),
            auto_merge_disabled=bool(data.get("auto_merge_disabled", True)),
            metadata=dict(data.get("metadata") or {}),
        )
    except Exception as exc:
        return fail_closed_decision(
            "malformed_gate_decision",
            reason=f"Gate decision cannot be reconstructed: {type(exc).__name__}.",
            metadata={"exception": str(exc)[:200]},
        )


def evaluate_governed_operation(**kwargs: Any) -> UnifiedGateDecision:
    try:
        request = UnifiedGateRequest(**kwargs)
        decision = get_unified_governance_gate().evaluate(request)
    except Exception as exc:
        return fail_closed_decision(
            "gate_unavailable",
            operation_class=str(kwargs.get("operation_class", "governance")),
            operation=str(kwargs.get("operation", "unknown")),
            risk_level=str(kwargs.get("risk_level", "P3")),
            reason=f"Gate wrapper failed closed: {type(exc).__name__}.",
            metadata={"exception": str(exc)[:200]},
        )
    return validate_gate_decision(decision)
