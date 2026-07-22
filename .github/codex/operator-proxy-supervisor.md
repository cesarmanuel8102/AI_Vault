Review the complete pull-request diff as an independent, read-only security and correctness supervisor for FRONT-OPERATOR-PROXY-CODEX-BRIDGE-01.

Compare the checked-out HEAD with its first parent. Verify fail-closed policy behavior, exact repository and SHA binding, LOW/MEDIUM-only delegated merge, HIGH/CRITICAL escalation, complete check gating, builder/reviewer session separation, append-only decisions, idempotency, pause controls, merge-commit-only execution, transactional installation and rollback, secret redaction, and absence of trading, canonical sync, credential, force-push, squash, rebase, auto-merge, or deployment authority.

Return PASS only when there are no P0/P1 findings and the reviewed head is exactly the current git HEAD. Do not modify files. Output only the required JSON schema.
