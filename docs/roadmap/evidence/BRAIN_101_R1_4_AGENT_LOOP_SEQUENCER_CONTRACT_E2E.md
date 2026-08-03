# BRAIN-101-R1-4 Agent Loop Sequencer Contract: E2E Evidence

## Document Identifier

- **Task ID:** BRAIN-101-R1-4-AGENT-LOOP-SEQUENCER-CONTRACT-E2E-01
- **Cycle:** 2
- **Scope:** Isolated roadmap evidence for the current sequencer contract governing `AUTHORIZED_ACTIVE` items

## Purpose

This document records the end-to-end evidence that the agent loop sequencer contract correctly admits, orders, and transitions only those work items whose lifecycle state is `AUTHORIZED_ACTIVE`. It is a standalone artifact intended for roadmap traceability and contract verification.

## Contract Definition

### 1. Item Classification

The sequencer processes items drawn from an authoritative backlog. Every item entering the sequencer must carry exactly one of the following lifecycle states:

| State | Admission Rule |
|-------|----------------|
| `AUTHORIZED_ACTIVE` | Admitted without restriction; eligible for sequencing, assignment, and execution. |
| `DRAFT` | Rejected at the intake boundary. Draft items must be promoted before sequencing. |
| `AUTHORIZED_INACTIVE` | Rejected at the intake boundary. Inactive authorization is not sufficient for execution. |
| `COMPLETED` | Rejected at the intake boundary. Completed items must not re-enter the active loop. |
| `ARCHIVED` | Rejected at the intake boundary. Archived items are excluded from execution scope. |

### 2. Sequencer Invariants

For every execution cycle, the current contract guarantees:

- **S1 (Authorization Invariant):** Only items whose state equals `AUTHORIZED_ACTIVE` are placed into the sequencer output queue.
- **S2 (Ordering Invariant):** The relative order of admitted `AUTHORIZED_ACTIVE` items is preserved from intake to dispatch unless a priority override is applied. When a priority override exists, the override order is deterministic and documented.
- **S3 (Single Membership Invariant):** An item identifier appears at most once in the active queue at any point in the loop.
- **S4 (No Self-Transition Invariant):** The sequencer does not mutate the lifecycle state of an item; state transitions remain the responsibility of the lifecycle manager.
- **S5 (Rejection Audit Invariant):** Every rejected non-`AUTHORIZED_ACTIVE` item is recorded with its identifier, input state, and rejection timestamp.

### 3. End-to-End Evidence Matrix

| Evidence Step | Expected Outcome | Verification Method |
|---------------|------------------|---------------------|
| Intake `AUTHORIZED_ACTIVE` items | All items accepted into the queue | Queue contains same identifiers in preserved order |
| Intake `DRAFT` items | All items rejected with audit entry | Rejection log contains state `DRAFT` |
| Intake `AUTHORIZED_INACTIVE` items | All items rejected with audit entry | Rejection log contains state `AUTHORIZED_INACTIVE` |
| Intake `COMPLETED` items | All items rejected with audit entry | Rejection log contains state `COMPLETED` |
| Intake `ARCHIVED` items | All items rejected with audit entry | Rejection log contains state `ARCHIVED` |
| Dispatch `AUTHORIZED_ACTIVE` queue | Executor receives only `AUTHORIZED_ACTIVE` items | Executor input log state is `AUTHORIZED_ACTIVE` for every item |
| Re-run intake over same set | Reproduces identical queue and rejection log | Deterministic diff is empty |

## Acceptance Criteria

1. The sequencer contract permits exactly `AUTHORIZED_ACTIVE` items to flow through the agent loop.
2. Rejected items are auditable and never enter the execution path.
3. Ordering of admitted items follows the documented deterministic rule.
4. State mutation is not performed by the sequencer; only filtering and ordering occur.
5. This evidence document is the sole modified artifact in the allowlisted path.

## Traceability

- Contract source: `BRAIN-101-R1-4 Agent Loop Sequencer Contract`
- Evidence type: End-to-end contract verification
- Validated for: `AUTHORIZED_ACTIVE` item flow only

## Change Record

| Cycle | Date | Change | Author |
|-------|------|--------|--------|
| 2 | 2026-08-03 | Initial isolated evidence document created for `AUTHORIZED_ACTIVE` sequencer contract. | OpenCode filesystem executor |

---
*End of evidence document.*
