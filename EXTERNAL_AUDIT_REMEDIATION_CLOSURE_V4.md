# CODEX IBKR AUTONOMOUS — EXTERNAL AUDIT REMEDIATION CLOSURE V4

Date: 2026-09-21

Canonical branch:
`codex/ibkr-paper-auditor-gate-v2`

Canonical merged HEAD at closure:
`1d537a795fef5d7918f8bcf5184a90c49e69bd60`

V3 remediation code parent:
`e2ae2383b62012a0feff37b75a70c9d8c4857f8e`

This document is an engineering closure index, not proof of correctness. The
external re-auditor must independently inspect code, tests, runtime paths, CI,
Git history, and operational controls.

## Audit lineage

Original external audit:
- `EXTERNAL_AUDIT_CODEX_IBKR_AUTONOMOUS_V1.md`
- audited SHA: `c4a0abdd081724e6073d0a4c394feb9749e4c985`

First remediation:
- `EXTERNAL_AUDIT_REMEDIATION_V1.md`

Second external re-audit remediation:
- `EXTERNAL_REAUDIT_V2_REMEDIATION.md`

Third audit remediation:
- `EXTERNAL_AUDIT_V3_REMEDIATION.md`

Final canonical merge:
- commit `1d537a795fef5d7918f8bcf5184a90c49e69bd60`
- subject: `Merge V3 external audit remediation`

## Current validated behavior

The implementation now contains explicit fail-closed controls for:

- persisted immutable 30-day experiment clock;
- restart recovery without resetting the experiment horizon;
- broker-server-time experiment clock snapshots;
- runtime MARKET_DATA_POLICY evaluation;
- fresh market-data gate immediately before execution;
- fresh Auditor V2 receipt validation every cycle and before execution;
- kill-switch write path and immediate pre-send recheck;
- owner authorization bound to the persisted experiment clock;
- owner authorization rechecked immediately before broker transmission;
- IBKR what-if None/error/missing-margin/missing-commission fail-closed;
- broker-warning fail-closed handling;
- position-action margin/equity parity with new proposals;
- late position size/direction inversion rechecks;
- same-connection what-if and paper send path;
- bounded Level-4 liability;
- no model-authored capital fallback for multi-leg market BUY structures;
- experiment-only order registry;
- orderRef + broker identity fill attribution;
- immediate-fill identity inheritance;
- post-submit broker permId persistence;
- synthetic-to-real execId reconciliation;
- late commission adjustment recovery;
- hash-chained isolated experiment ledger;
- fatal handling of ledger corruption;
- explicit PAUSE_FOR_REVIEW side effects;
- recoverable continuous-service loop errors;
- observation-only immediate post-fill reevaluation;
- GPT-5.6 Sol / max reasoning floor;
- strict fail-closed actual-model attestation;
- malformed/duplicate-key/missing-model JSONL rejection;
- model-facing redaction of global broker balances;
- per-trade realtime contract data validation;
- combo-leg realtime fallback validation;
- Auditor loopback broker-socket denial;
- exact Auditor endpoint map validation for IPv4/IPv6 and ports 4001/4002;
- Auditor restricted-account deny logon rights;
- fail-closed opaque path handling;
- immutable Git trust anchor for Auditor deployment;
- bounded auditor account enablement and password lifecycle;
- standardized market evidence windows;
- broker-timestamp evidence span;
- corrected ETF primary-exchange mapping;
- corrected latest broker timestamp semantics;
- restricted local sync receipt ACL.

## Autonomous mandate preserved

The remediation does NOT reintroduce:

- fixed trading-symbol universe;
- frozen candidate allowlist;
- mandatory predefined strategies;
- 5% per-trade risk cap;
- 15% open-risk cap;
- 20% drawdown cap;
- 40% position cap;
- fixed maximum number of positions;
- mandatory stops;
- mandatory diversification.

The autonomous route remains capital-adaptive and Codex-directed.

The deterministic capital boundary remains:

`maximum experiment liability <= current isolated experiment equity`

and actual broker feasibility remains enforced with IBKR what-if plus
deterministic payoff analysis.

## Final CI evidence

### V3 remediation code SHA

`e2ae2383b62012a0feff37b75a70c9d8c4857f8e`

Linux / Python 3.11:
- 447 passed
- 0 failed
- 99 skipped

Windows / Python 3.11:
- 544 passed
- 0 failed
- 7 skipped

PowerShell parser checks: PASS.
Critical Python compilation: PASS.
Phase 0 security tests: PASS.
Phase 1 baseline tests: PASS.
Import smoke: PASS.

### Canonical merge HEAD

`1d537a795fef5d7918f8bcf5184a90c49e69bd60`

Windows full IBKR suite:
- 544 passed
- 0 failed
- 7 skipped

The merge commit has two parents, one of which is the validated V3 remediation
SHA above. No claim should be accepted without independently confirming that
the canonical HEAD contains the expected remediation tree.

## Operational state

This closure does NOT mean the 30-day experiment has started.

At closure:
- paper execution is not automatically armed;
- no live-money path is enabled;
- the operational Windows host must still complete the actual local
  prerequisite/runtime evidence sequence;
- the independent external re-audit must still confirm zero open CRITICAL and
  zero open HIGH findings before Day 1 authorization.

## Re-audit requirement

A new external auditor must:
1. clone the canonical branch fresh;
2. resolve and record the actual HEAD;
3. ignore this document as proof;
4. independently reproduce the runtime call graph;
5. re-test all original V1 findings;
6. re-test all V2/V3 findings and bypass families;
7. add new adversarial tests rather than only running repository tests;
8. explicitly search for regressions introduced by remediation;
9. verify both application-level and Windows-host-level assumptions;
10. report any remaining blocker before operational Day 1.

The canonical external re-audit prompt is stored in:
`EXTERNAL_REAUDIT_PROMPT_V4.md`.
