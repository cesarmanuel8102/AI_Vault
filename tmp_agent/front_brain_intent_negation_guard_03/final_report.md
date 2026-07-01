# FRONT-BRAIN-INTENT-NEGATION-GUARD-03

Status: IMPLEMENTED_VALIDATED

## Problem
The live operational probe showed sin escribir memoria ni usar broker being classified as memory_write because deterministic keywords were matched inside a negated constraint.

## Fix
Added a local negation guard for risky keyword intents only:
- code_change_request
- delete_request
- push_request
- memory_write
- 	rading_broker_live

Positive risky requests still escalate or block normally.

## Validation
- py_compile: PASS
- 	ests/smoke/test_front_brain_intent_negation_guard_03.py: 4 passed
- Focal regression with boundary contracts: 10 passed
- Existing live NL router/governance smoke with correct token: 12 passed

## Safety
- No real money path touched.
- No broker/IBKR path touched.
- No trading code touched.
- No memory/semantic data mutated.
- No FAISS/index mutation.
- No .env or secrets touched.

## Live post-restart verification
- File: tmp_agent/front_brain_intent_negation_guard_03/live_negation_verify_after_restart.json
- Result: PASS
- intent_detected: unknown_or_insufficient_info
- governance_decision: allow
- approval_required: false
- backend/model: langgraph_parity / kimi-k2.6:cloud

