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

## Git restrictions

- Agents do not commit, push, merge, rebase, clean or hard-reset. The trusted worker owns Git writes.
- Do not use GitHub CLI from an agent session.

## Efficiency

- Read only the front spec, AGENTS.md, relevant diff and affected files.
- Run targeted tests during repair cycles.
- Report deltas; do not reproduce large logs.
- Stop and summarize when the step limit is reached.

