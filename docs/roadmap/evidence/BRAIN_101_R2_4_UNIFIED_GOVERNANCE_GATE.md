# BRAIN-101-R2-4 Unified Governance Gate Evidence

## Scope

Implemented one authoritative fail-closed gate model for governed runtime
decisions in `tmp_agent/brain_v9/governance/unified_gate.py`.

## Routed Surfaces

- Agent V2 approval/write checks delegate through the unified gate.
- `ToolGatewayV2` preflights read, patch, approval, and execution tool calls.
- Legacy `ExecutionGate.check()` preflights command/tool execution before its
  existing P2/P3 pending-approval behavior.
- `main.py` mutative endpoint preflight helpers preserve existing response
  shape while providing a shared gate decision path.

## Fail-Closed Behavior

The contract covers missing, malformed, stale, unavailable, inconsistent, and
forged gate decisions. Each resolves to `allowed=False`, `blocked=True`, and a
specific gate error.

## Preserved Invariants

- P3 is never auto-approved, including forged decisions and GOD-mode execution.
- Human final authority is a required decision invariant.
- Live trading, real money, canonical local sync, and auto-merge remain disabled.
- `.env`, `.github`, memory/semantic, rollback memory, trading, financial
  autonomy, runtime state, scripts, and canonical-local paths fail closed.

## Verification

Targeted contract:

`python -m pytest tests/contract/test_brain_101_r2_4_unified_governance_gate.py -q`
