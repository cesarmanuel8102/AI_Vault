# R6.2 Governed Memory Candidate Promotion and Rollback

## Status and Scope

This design implements `BRAIN-101-R6-2-GOVERNED-MEMORY-CANDIDATE-PROMOTION-ROLLBACK-01` after R6.1's read-only `MemoryService` boundary.  It is a `NO_DEPLOY` control-plane change.  It does not activate a scheduler, install a worker, write the runtime canonical memory, or change trading controls.

Hard limits remain invariant:

```text
HUMAN_FINAL_AUTHORITY=true
AUTO_MERGE=false
CANONICAL_LOCAL_SYNC=false
LIVE_TRADING=false
REAL_MONEY=false
```

## Problem

The historical promoter can append directly to semantic JSONL and FAISS and uses filesystem snapshots rooted at `memory/`.  That bypasses R6.1's service ownership boundary and makes it impossible to prove that a specific approved candidate, room, and rollback artifact are bound together.  R6.2 replaces that behavior with an approval-gated operation owned by `MemoryService`; it never grants a generic write capability.

## Chosen Architecture

### 1. Typed, immutable inputs

`GovernedPromotionCandidateV1` contains a canonical candidate identifier, normalized record, source/evidence identifiers, origin room, retention class, and `candidate_sha256`.  `candidate_sha256` is SHA-256 of canonical JSON with that field omitted, avoiding a self-referential hash.  The candidate parser rejects unknown fields, blank content, unsafe room identifiers, live-trading content, cross-room destination fields, and content whose computed hash differs from the supplied hash.

`ManualPromotionDecisionV1` contains the exact candidate identifier and candidate SHA-256, approver principal, immutable decision identifier, and an explicit `APPROVE_SINGLE_CANDIDATE` decision.  It rejects automated actors, expiry, mismatched candidate bindings, or any value other than the exact approval action.  A decision is authorization for one candidate, not a reusable promotion token.

### 2. MemoryService owns the only R6.2 operation

`MemoryService` exposes these bounded operations:

```text
validate_governed_candidate(candidate) -> validation report
prepare_governed_promotion(candidate, decision, staging_root) -> promotion receipt
execute_isolated_governed_promotion(receipt, isolated_root) -> execution receipt
rollback_isolated_governed_promotion(execution_receipt, isolated_root) -> rollback receipt
```

`prepare` is deterministic and creates no semantic-memory mutation.  `execute` is permitted only for a caller-supplied isolated root used by contracts.  It refuses the configured semantic root, any `memory/` canonical location, a path outside the provided isolated root, a cross-room candidate, stale or mismatched approval, duplicate candidate hash, or an unverified receipt.  Runtime canonical execution returns a fail-closed `canonical_promotion_not_enabled` result.

The public `MemoryService.promote()` method remains unavailable for generic callers.  The legacy promoter becomes a compatibility facade that delegates validation/receipt construction to `MemoryService`; it must not instantiate FAISS, append JSONL, or copy canonical files itself.  `SemanticMemoryFAISS` retains storage primitives but receives no public governance decision and no external promoter is allowed to call it directly for R6.2 promotion.

### 3. Receipts and provenance

Every successful step returns canonical JSON and SHA-256:

- `PromotionReceiptV1`: candidate hash, decision ID, approver, origin room, retention class, allowed isolated root, and snapshot manifest hash.
- `PromotionExecutionReceiptV1`: promotion receipt hash, before/after artifact hashes, dedupe result, and a rollback receipt ID.
- `MemoryRollbackReceiptV1`: execution receipt hash, restored artifact hashes, and exact rollback verification result.

Receipt verification uses canonical JSON serialization and rejects unknown fields.  A rollback requires the exact execution receipt and must restore every touched artifact byte-for-byte.  A duplicate candidate is a successful no-op with an explicit `duplicate` outcome; it does not create a mutation receipt.

### 4. Snapshot and rollback boundary

`memory_snapshot.py` and `memory_rollback.py` accept an explicit isolated root and derive all artifact paths beneath it.  They reject default canonical paths and path traversal.  Snapshot manifests list relative paths, byte lengths, and SHA-256 values.  Rollback first verifies the manifest and current receipt binding, then atomically restores only the listed isolated artifacts.  No R6.2 operation may create or use `memory/rollback_snapshots` in the repository or any live runtime location.

### 5. Retention, deduplication, and auditability

Candidate and receipt retention metadata are returned to the caller, not written to global runtime state.  Dedupe is based on a stable candidate content hash and candidate ID in the isolated store.  Every rejection identifies the failed gate without exposing candidate body content.

## Error Handling

All invalid inputs fail before any isolated artifact is written.  A failure after snapshot creation causes an immediate verified rollback; if rollback verification fails, the result is `rollback_verification_failed` and no success receipt is issued.  No exception path falls back to the legacy promoter, direct FAISS mutation, or a canonical root.

## Tests

The dedicated R6.2 contract test will use temporary isolated roots only and cover:

1. valid candidate plus exact manual approval produces a deterministic preparation receipt without mutation;
2. isolated promotion and rollback restore JSONL, FAISS index, and ID artifacts byte-for-byte;
3. missing approval, automated approval, stale decision, mismatched candidate hash, cross-room request, unsafe root, canonical root, and duplicate candidate all fail closed or no-op as specified;
4. corrupted snapshot manifest, altered receipt, altered artifact, and mid-promotion failure never report success;
5. legacy promoter has no direct append/copy/FAISS mutation path;
6. R6.1 read-only retrieval and integrity contracts remain unchanged.

## Rollback and Deployment

The implementation is source-only and will not be installed or deployed in R6.2.  The implementation PR may be rolled back as a normal merge reversal.  Isolated test artifacts are temporary and are not runtime data.  Any future runtime enablement requires a separately authorized roadmap item, a new design, explicit manual approval, and no change to the hard limits above.
