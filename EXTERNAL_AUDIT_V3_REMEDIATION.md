# EXTERNAL_AUDIT_V3_REMEDIATION

Date: 2026-09-21
Source audit: EXTERNAL_AUDIT_CODEX_IBKR_AUTONOMOUS_V3.md
Audited source SHA: 7bb22b2581159b92ee9dac5640692d168588031a
Remediation branch: codex/ibkr-v3-remediation

## Blocking HIGH

### V3-AUDIT-2.A / V3-NF-H1 — missing actual_model fail-open

Status: FIXED IN REMEDIATION BRANCH

Implementation:
- Shared strict Codex JSONL model-attestation routine lives in `ibkr_paper_30d/trader_invocation.py`.
- Autonomous and alternate Codex providers both use the same attestation logic.
- Missing `actual_model`, empty stdout, None/non-string output, malformed JSONL,
  duplicate JSON keys, null/empty/non-string model fields, and model mismatch all fail closed.
- Explicit `actual_model` evidence matching the requested model is required.

Regression coverage:
- `tests/ibkr_paper_30d/test_reaudit_v2_remediation.py`
- `tests/ibkr_paper_30d/test_autonomous_codex_provider.py`
- `tests/ibkr_paper_30d/test_real_codex_provider.py`

## V3 MEDIUM hardening

### V3-AUDIT-1.D — model-facing broker-global feasibility balances

Status: FIXED IN REMEDIATION BRANCH

- Broker what-if remains authoritative internally.
- Model-facing feasibility evidence is allowlisted.
- Global before/after margin and equity-with-loan values are not surfaced.
- Margin changes and commission evidence remain available for capital-boundary checks.

### V3-AUDIT-2.B/C/D/E/F/G/J — model-attestation parser bypass family

Status: FIXED BY SHARED FAIL-CLOSED ATTESTATION

- Malformed JSONL blocks.
- Invalid model-field types block.
- Empty/null model evidence blocks.
- Duplicate JSON keys block.
- Alternate/renamed/nested reporting without authoritative `actual_model` blocks.
- Alternate Codex provider no longer assumes `actual_model=requested_model`.

### V3-AUDIT-5 H-1 — incomplete Auditor endpoint receipt accepted

Status: FIXED IN REMEDIATION BRANCH

The gate now requires the exact endpoint map:
- `127.0.0.1:4001 = DENIED`
- `127.0.0.1:4002 = DENIED`
- `[::1]:4001 = DENIED`
- `[::1]:4002 = DENIED`

Any missing, extra, or non-DENIED endpoint blocks.

### V3-AUDIT-5 Quote-Argument

Status: HARDENED

The prerequisite finalizer rejects PowerShell interpolation/control metacharacters
in scheduled-task argument values in addition to the existing quote/trailing-slash checks.

## V3 LOW / INFO hardening

- Broker exception text no longer echoes raw exception messages into model-facing research results.
- Dormant `summary` consumption was removed from the broker snapshot.
- Legacy Auditor consolidator requires the same exact four-endpoint denial map.
- Committed gate-matrix network facts were aligned with the current mandatory-isolation contract.
- `QuoteSnapshot` rejects naive timestamps at model validation.
- Regression coverage was added for market-policy version/control coherence.
- Runtime gate regression coverage verifies oldest/latest quote timestamps are surfaced.

## Intentionally unchanged accepted residuals

The V3 audit explicitly accepted these as non-blocking architectural residuals:
- Git trust anchor is not re-read on every runtime cycle.
- An irreducible micro-window exists between final broker position read and network send.

No architecture change was made for those accepted residuals.

## Validation requirement

This remediation is not eligible for merge until the same final HEAD passes:
- Linux full `tests/ibkr_paper_30d` suite,
- Windows full `tests/ibkr_paper_30d` suite,
- PowerShell parser checks,
- compilation/security/import-smoke checks.

No trading is armed. No live-money path is enabled by this remediation.
