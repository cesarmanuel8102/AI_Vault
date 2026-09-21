# EXTERNAL AUDIT REMEDIATION V1

Branch: `codex/ibkr-external-audit-remediation-v1`

Source audit: `EXTERNAL_AUDIT_CODEX_IBKR_AUTONOMOUS_V1.md` against
`c4a0abdd081724e6073d0a4c394feb9749e4c985`.

This document is a remediation index, not proof. A second external auditor must
reproduce every claim from executable code and tests.

## Blocking findings

| Audit ID | Remediation implemented | Verification target |
|---|---|---|
| C-1 / F4-1 | Persisted immutable experiment clock in `experiment_clock_events`; restart loads original clock; broker server time drives snapshots; changed start/duration/allocation is rejected. | `experiment_control.py`, external-audit regression tests |
| C-2 / F5-1 | Runtime loads verified frozen market policy and evaluates fresh IBKR quotes every cycle and immediately before execution. | `runtime_integrity.py`, `autonomous_state.py`, `autonomous_service.py` |
| C-3 / F3-1 | IBKR what-if is fail-closed on None/exception/missing margin/missing commission. | `ibkr_research_tools.py::_feasibility_common`, broker failure tests |
| C-4 / F4-2 | Production append-only kill-switch write path added; fresh DB state is checked immediately before broker transmission. | `experiment_control.py::KillSwitchStore`, service CLI, executor fresh-safety callback |
| C-5 / F-01 | Auditor gate requires broker socket DENIED on loopback; bounded probe firewall is verified; forbidden privileges checked; restricted account password rotated and account disabled outside the probe window. | Auditor PowerShell runtime + finalizer + V2 evaluator |
| H-1 / F3-2 | Position actions use the same margin-evidence/equity checks as new proposals. | `validate_position_action` |
| H-2 / F3-3 | Shared broker warning block list includes insufficient/incompatible/missing/rejected/not allowed/cannot. | `WARNING_BLOCK_TOKENS` |
| H-3 / F3-4 | Position is re-resolved and quantity/direction rechecked after what-if and immediately before send on the same IBKR connection. | `autonomous_execution.py` |
| H-4 / F4-3 | Continuous loop distinguishes fatal DB faults from recoverable runtime faults, persists alerts, waits and continues. | `autonomous_service.py::run_forever` |
| H-5 / F4-4 | PAUSE_FOR_REVIEW triggers kill switch, alert, stop event. | `autonomous_service.py::_handle_pause` |
| H-6 / F-02 | Restricted account receives explicit deny logon rights and probe proves absence of dangerous token privileges. | provisioning + consolidated probe |
| H-7 / F-03 | Opaque/uninspectable path chain now fails closed. | `AUDITOR_DENIAL_PROBE_V1.ps1` |
| H-8 / F-04 | Auditor receipt freshness/integrity is re-evaluated every autonomous cycle and again immediately before broker transmission. | `RuntimeAuditorGate` + fresh safety |
| H-9 / F-05 | Auditor deployment is bound to a pinned immutable Git trust source/anchor instead of hashing the installed manifest as its own authority. | finalizer + prerequisite tools |
| H-10 / TQ-1 | Fault matrix can no longer report PASS for an unexecuted scenario; PASS is bound to concrete production regression-test nodeids. | reporting/fault tests |
| H-11 / TQ-2 | Explicit regressions cover what-if None/failure and broker warning rejection. | broker feasibility tests |
| H-12 / TQ-5 | Windows and Linux workflows run the full `tests/ibkr_paper_30d` suite. | CI workflows |
| H-13 / F4-5 | Immediate post-fill cycle is observation/reasoning only; execution disabled; position cadence timer reset. | service cadence tests |

## Additional integrity remediations

- Expected PAPER account identity is bound in autonomous IBKR tooling rather
  than accepting any DU account.
- Codex runtime enforces GPT-5.6 Sol + max reasoning and detects a reported
  model substitution in Codex JSONL.
- Autonomous ledger is hash chained.
- Missing broker execIds receive deterministic synthetic execution hashes.
- Experiment fills require both experiment orderRef and a matching issued-order
  registry identity.
- Order identity is persisted before transmission.
- Multi-leg BUY market structures no longer use model-authored
  `capital_required` as a loss-floor fallback.
- Global broker NLV/buying power are redacted from Codex; exposed experiment
  buying power is capped to isolated equity and broker constraints.
- Mark failures block reconciliation rather than silently using an old value.
- Market evidence span is measured from broker timestamps.
- Market evidence windows are standardized at 330 seconds / 5-second cadence /
  31-minute start separation.
- Corrected collector semantics are versioned; stale pre-fix policy artifacts
  are rejected.
- SPY/QQQ/IEF primary exchanges remain SPY=ARCA, QQQ=NASDAQ, IEF=NASDAQ.
- Market-gate result reports oldest and latest quote timestamps explicitly.
- Isolated ledger tracks weighted-average cost while equity remains cash +
  marked market value.
- Deprecated duplicate prerequisite scripts delegate to canonical finalizers.
- Auditor seclogon state is restored after probing and password is rotated.
- Local sync receipt directory receives restricted ACLs.
- PAPER execution requires an immutable owner authorization event bound to the
  persisted experiment clock, in addition to the arming environment variable
  and fresh runtime gates.

## Deliberate terminal policy

At experiment expiry or equity depletion the service does not create new
strategy decisions or blindly transmit liquidation orders outside market
conditions. It records a terminal state event containing final cash, marked
market value, equity, fees and open positions; triggers the kill switch; and
marks open positions as requiring controlled/manual close. This is deliberate:
the 30-day objective stops at the terminal marked state and the runtime must not
create new post-horizon risk merely to flatten mechanically.

## CI closure

Final Windows/Linux counts and final remediation SHA must be inserted only
after both full-suite workflows pass on the same HEAD.

## External re-audit rule

Do not accept this file, commit messages, or existing tests as proof. Re-audit
from a clean clone, inspect the runtime call graph, add independent adversarial
tests, and specifically try to falsify each remediation above.
