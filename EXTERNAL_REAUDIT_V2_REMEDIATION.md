# EXTERNAL_REAUDIT_V2_REMEDIATION

Date: 2026-09-21
Source re-audit: EXTERNAL_REAUDIT_CODEX_IBKR_AUTONOMOUS_V2.md
Audited source SHA: 271653a67fb1eb8eeebe637890b3aeb480dce8fa
Remediation branch: codex/ibkr-reaudit-v2-remediation

## Blocking HIGH findings

### REAUDIT-5-NLV-1 — raw global broker capital exposed to Codex

Status: FIXED

Remediation:
- `IBKRResearchToolbox._account_state()` no longer returns raw
  `NetLiquidation`, cash, buying power, available funds, excess liquidity,
  or account margin values.
- The tool returns only paper/session context, declared options level,
  broker server time, and an explicit redaction marker.
- The ACCOUNT_STATE manifest no longer advertises NLV/cash/global buying power.
- Actual broker affordability remains authoritative through per-order IBKR
  what-if validation immediately before execution.

Regression test:
- `tests/ibkr_paper_30d/test_reaudit_v2_remediation.py::test_account_state_research_never_exposes_global_broker_balances`

### REAUDIT-6-M-3-ACTUAL_MODEL_GAP — actual_model substitution not detected

Status: FIXED

Remediation:
- `CodexAutonomousCLIProvider._assert_effective_model()` now treats
  `actual_model` as an authoritative model-identifier surface in addition to
  `model`, `model_name`, `model_id`, and `effective_model`.
- Any observed non-requested model identifier fails closed.

Regression tests:
- `test_actual_model_substitution_is_detected`
- `test_actual_model_equal_to_requested_model_passes`

### TOCTOU-1 — final position direction inversion not rechecked

Status: FIXED

Remediation:
- The final pre-send position snapshot now derives the required reducing action
  from the actual signed position.
- SELL is allowed only for a current long position; BUY only for a current
  short position.
- If the sign changes after what-if, execution returns
  `POSITION_ACTION_WOULD_INCREASE_EXPOSURE_BEFORE_SEND`.
- `placeOrder` is not reached.

Regression test:
- `test_late_position_direction_inversion_blocks_before_send`

## Additional residual hardening completed

- Logical/hash-chain ledger corruption is now treated as fatal rather than a
  recoverable retry loop.
- Fill attribution now requires all broker identifiers supplied by the fill to
  match the same experiment-order registry row; a correct permId cannot mask a
  wrong orderId and vice versa.
- MARKET_DATA_POLICY artifact loading now requires
  `schema == policy_version == MARKET_DATA_POLICY_V1`.
- Runtime market-gate output exposes both oldest and latest quote timestamps.
- Implementation status now reflects mandatory Auditor broker-socket denial.
- The legacy V2 receipt consolidator now requires all broker loopback endpoint
  observations to be DENIED and emits the current network-isolation facts.

## Residual LOW risks intentionally not reclassified as fixed

The following are not Day-1 HIGH blockers, but should remain visible:

1. Owner-authorization events are append-only against UPDATE/DELETE, but a
   principal with arbitrary raw SQLite write authority is outside the current
   application trust boundary.
2. An irreducible check-to-network-send interval remains between the last
   operator-control DB read and IBKR API transmission. The runtime minimizes it
   with repeated fresh checks. Eliminating it fully would require a stronger
   broker-side or transactionally coupled authorization primitive.
3. Runtime Auditor verification validates installed hashes against the accepted
   receipt every cycle; the Git trust anchor is validated during install/finalize
   rather than invoking Git on every decision cycle.
4. Broker-side buying power remains larger than isolated experimental equity
   unless the paper account itself is separately constrained. Application-layer
   what-if and loss-bound controls remain mandatory.
5. Host-level Windows firewall behavior still requires operational verification
   on the actual Windows machine; Linux CI can only test the gate evaluator and
   PowerShell structure.

## Readiness rule

Do not classify the system READY_FOR_OPERATIONAL_PREFLIGHT unless:
- the full Linux IBKR suite passes;
- the full Windows IBKR suite passes;
- no CRITICAL finding is open;
- no HIGH finding is open;
- a fresh independent re-audit reproduces closure of all three V2 HIGH findings.

This remediation does not arm paper execution and does not authorize live money.
