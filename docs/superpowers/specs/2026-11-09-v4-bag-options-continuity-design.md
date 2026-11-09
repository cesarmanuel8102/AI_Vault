# V4 BAG Options Continuity Design

## Intent

Allow a broker-qualified multi-leg option proposal to carry complete, host-derived V4 continuity and ownership evidence without weakening any fail-closed control. The immediate regression is the HIMS 23/20 bear-put: IBKR computed what-if economics, but the host withheld the canonical BAG identity and leg-member identities, so the proposal could not be authorized.

## Goals

- Bind the exact BAG parent identity, ordered combo legs, and each qualified option-leg identity.
- Derive the V4 ownership-group hash from the BAG parent plus all legs.
- Recompute and compare that ownership group immediately before authority reservation.
- Preserve paper-only, single-writer, idempotency, sleeve isolation, and continuity requirements.

## Non-goals

- Reuse or revive the expired HIMS proposal.
- Relax option economics, freshness, market-hours, or continuity validation.
- Substitute a stock or single option leg for a requested combo.
- Submit any broker order during development or testing.

## Constraints

- Production checkout and running Day1 remain untouched during implementation.
- Broker-feasibility evidence is authoritative only when derived from qualified contracts.
- A BAG parent with missing, duplicate, mismatched, or non-option members remains blocked.
- No transaction or write authority is created by what-if evidence.

## Approaches considered

1. **Treat the BAG parent alone as the canonical contract.** Smallest change, but unsafe because it does not reserve the option legs and permits cross-sleeve ownership collisions. Rejected.
2. **Re-resolve all legs later from only the model proposal.** Safer than parent-only, but duplicates broker resolution and can bind a different contract snapshot from the successful what-if. Rejected.
3. **Carry broker-qualified parent and member identities from the successful what-if.** The what-if path already qualifies every leg. Preserve those exact identities, validate parent/member closure, derive the ownership group, and compare it again against live broker evidence before reservation. Selected.

## Design

`IBKRResearchToolbox` retains the qualified contracts used to construct a BAG and emits:

- `canonical_contract_identity_v4`: canonical BAG parent including ordered `bag_legs`.
- `ownership_contracts_v4`: canonical parent followed by each broker-qualified option leg.

`build_v4_new_proposal_bindings` validates that the member set is exact: one parent, one identity for every BAG leg `con_id`, no extras, and no duplicates. It then hashes a `ContractOwnershipGroup(parent, parent+legs)`.

At final sleeve authority, the live broker evidence produces the same parent+leg group. The validator must require its hash and parent hash to match the continuity plan before reserving ownership. Any discrepancy fails closed.

## Verification

- Regression reproducing successful HIMS-like BAG what-if and asserting complete V4 evidence.
- Binding test asserting deterministic parent+leg group derivation and rejection of missing/mismatched members.
- Final-authority test asserting the exact V4 group passes and any altered member/group blocks.
- Existing broker-feasibility, continuity, execution-authority, kernel, and full test suites.

