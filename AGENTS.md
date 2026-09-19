# AI_Vault Agent Loop Rules

These instructions apply to OpenCode/Kimi and any coding agent working in this repository.

## Authority and source of truth

- GitHub remote and the current Draft PR are authoritative.
- Never read, modify, synchronize, or assume the state of `C:\AI_VAULT_CANONICAL`.
- Never merge, force-push, rewrite the base branch, or bypass required checks.
- Kimi is the writer. Codex is a read-only supervisor. Human reauditing is final authority.

## Scope discipline

- Modify only the paths in the machine-issued front specification.
- Do not make opportunistic cleanups.
- Preserve authentication, response shape, side effects, error codes and rollback behavior.
- Never touch memory/semantic, FAISS, runtime state, trading, QC, IBKR or financial autonomy unless a future front explicitly authorizes it.

## Persistent completion rule

Before any claim of COMPLETE, CLOSED, VERIFIED, READY, or CERTIFIED — and before any successor authorization — the worker must:

1. Re-read the parent requirement.
2. Resolve SemanticCompletionGate / `evaluateSemanticCompletion()` through the governed canonical path (never a parallel or duplicated check).
3. Use fresh verification: the decision must come from the gate at completion time, not from a cached, assumed, or asserted result.
4. Invoke verification-before-completion discipline: the claim is made only after the gate returns PASS.
5. Refuse semantic completion whenever the gate returns BLOCK; a BLOCKed requirement can never be reported as complete.

Evidence rules (absolute):

- Agent claim is not evidence.
- Reviewer claim is not evidence.
- Lifecycle status is not semantic evidence.

The gate defined in `scripts/operator_proxy/semantic_completion_gate.ts` (reached through the governed resolver) is the single semantic PASS/BLOCK authority. CI results, review verdicts, and lifecycle states never substitute for it; this rule defers to that authority and does not restate its evaluation logic. Human reauditing remains final authority.

## Git restrictions

- Agents do not commit, push, merge, rebase, clean or hard-reset. The trusted worker owns Git writes.
- Do not use GitHub CLI from an agent session.

## Efficiency

- Read only the front spec, AGENTS.md, relevant diff and affected files.
- Run targeted tests during repair cycles.
- Report deltas; do not reproduce large logs.
- Stop and summarize when the step limit is reached.

