# Operator Proxy

Governed GitHub bus for BRAIN-101. Builder and reviewer use independent sessions; a deterministic policy decides APPROVE, REPAIR, BLOCK, or ESCALATE_TO_OWNER. Auto-merge, squash, rebase, force-push, canonical sync, trading, credentials, and HIGH/CRITICAL autonomous actions are forbidden. Decisions are immutable and keyed by reviewed HEAD. Local `state/PAUSE` or `operator:pause` stops all work.

Install transactionally with `Install-OperatorProxy.ps1`, keep the task disabled, run `npm run doctor`, `npm run typecheck`, `npm test`, then `Run-OperatorProxy.ps1 -Once -DryRun` before one controlled real poll.
