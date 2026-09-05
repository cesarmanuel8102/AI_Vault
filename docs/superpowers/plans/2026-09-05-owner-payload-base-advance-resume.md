# Owner Payload Base-Advance Resume V1

Governed SYSTEM_REPAIR: `OWNER_PAYLOAD_BASE_ADVANCE_RESUME_V1` (Issue #282).

## Contract

The Owner grant and its VERIFIED, CONSUMED, and BUILD_DISPATCHED receipts
remain immutable. Recovery retains the existing logical build attempt.
Normal payload repairs stay capped at two; the Owner exception stays capped
at one per front lifetime. No production logic identifies a specimen by its
roadmap item, issue number, PR number, or SHA.

The frozen authorized base and effective execution base have distinct meanings.
Before provider execution, bind the current canonical tip only after proving
frozen-base ancestry, exact installed mirror/source bytes, and Doctor PASS.
Persist the binding in a separate append-only ledger referencing the existing
BUILD_DISPATCHED event. Retries cannot choose another base or attempt.

## Implementation Ownership

- `owner_repair_effective_base.ts`: immutable base binding, chain validation,
  single-front uniqueness, fsync, and crash-recoverable epoch locking.
- `owner_payload_base_sync.ts` and `governed_builder.ts`: deterministic
  two-parent synchronization, exact receipt/provenance, non-force publication,
  and committed-candidate recovery without reinvoking the provider.
- `candidate_execution.ts`: validate published scope before push and keep
  publication separate from adoption.
- `owner_payload_repair_orchestrator.ts`: bind before discovery/dispatch and
  recover existing HEAD_BOUND evidence without another logical build.
- `external_effect_guard.ts`: preserve ordinary guards; require the bound
  effective tip, runtime proof, exact identity, lease, and allowed effect.
- `lineage.ts`, `lifecycle_store.ts`, and `types.ts`: validate actual receipt
  ledgers and four-anchor provenance before persisting effective-base adoption.
- `production_effects.ts` and `autonomous_flow.ts`: resolve frozen authority
  into a verified effective execution spec for later CI/review/policy ticks.
  Never redispatch an already-adopted Owner candidate.
- `Repair-OperatorProxy.psm1`: include both new runtime modules in transactional
  installation and rollback.

## Verification Sequence

1. Add failing focused tests for each boundary before its implementation.
2. Run focused ledger, sync, effect-guard, flow, adoption, and spec contracts.
3. Run `npm run typecheck` and `npm test` from `scripts/operator_proxy`.
4. Run `tests/contract/operator_proxy/install.ps1` in Windows PowerShell 5.1
   and PowerShell 7 against temporary installations only.
5. Run `git diff --check`, scope/secret scans, and whole-path review.
6. Publish the same governed repair front, then require exact-head technical
   CI and a real independent DeepSeek Pro review with zero findings.
7. Materialize the Owner's exact-head critical-merge evidence only after the
   gates pass; execute the installed critical-merge protocol, never bootstrap.
8. Transactionally install the exact merge SHA, verify source/mirror/installed
   identity and Doctor, then resume the existing Owner attempt.

## Negative and Crash Matrix

Test equal/one/many descendant bases, unrelated ancestry, runtime/Doctor drift,
canonical drift after binding, grant/attempt/dispatch tampering, duplicate
consumption, a second grant for one front, malformed or conflicting bindings,
and first binding after HEAD_BOUND. Distinguish inherited canonical changes
from forbidden provider payload. Require both effective-relative and
sync-relative allowlists.

Test process death after durable append, deterministic sync retries, interruption
after sync, local committed-candidate recovery, remote candidate recovery before
HEAD_BOUND, and later-tick execution-spec resolution. Preserve receipt bytes and
the original counters. Reject incomplete adopted anchors, wrong provenance,
non-ancestral candidates, and attempts to resume transport after adoption.

## Integration and Operational Gate

Installation preserves config, lifecycle, decision/receipt ledgers and locks.
Rollback restores the prior runtime byte-for-byte without enabling a task.
Both schedulers remain disabled during repair and installation.

After the repaired existing front closes, perform the convergence audit before
enabling the existing canonical scheduler. Verify a scheduler-originated wake,
single-instance lease and governed tick. Three clean runs certify the enabled
loop; they are not prerequisites to enabling it. Do not claim roadmap completion
before all final roadmap certification requirements pass.

Always preserve `HUMAN_FINAL_AUTHORITY=true`, `AUTO_MERGE=false`,
`CANONICAL_LOCAL_SYNC=false`, `LIVE_TRADING=false`, and `REAL_MONEY=false`.
