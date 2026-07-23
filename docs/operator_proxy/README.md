# Operator Proxy

Governed GitHub bus for BRAIN-101. Builder and reviewer use independent sessions; a deterministic policy decides APPROVE, REPAIR, BLOCK, or ESCALATE_TO_OWNER. Auto-merge, squash, rebase, force-push, canonical sync, trading, credentials, and HIGH/CRITICAL autonomous actions are forbidden. Decisions are immutable and keyed by reviewed HEAD. Local `state/PAUSE` or `operator:pause` stops all work.

Install transactionally with `Install-OperatorProxy.ps1`, keep the task disabled, run `npm run doctor`, `npm run typecheck`, `npm test`, then `Run-OperatorProxy.ps1 -Once -DryRun` before one controlled real poll.

## Autonomous roadmap flow

The proxy reads the manifest and roadmap from the immutable remote integration HEAD. Exactly one `AUTHORIZED_ACTIVE` item with complete automation and closeout metadata is required. The persisted lifecycle advances through discovery, admission, isolated building, CI, independent review, bounded repair, governed merge, optional install/runtime pilot, documentary closeout, and next-item discovery.

External effects are idempotent: an existing Issue, remote branch, Draft PR, decision, or merge is reconciled rather than recreated. Builder and reviewer session IDs must differ. P0/P1 findings block; bounded P2 findings may use at most two fresh builder repair sessions. Installation and runtime pilots use SHA-bound local requests and receipts so UAC pauses resume the same lifecycle.

The sequencer never writes the manifest, roadmap, scorecard, ledger, or status files. Those files may change only through the separately scoped and reviewed closeout PR declared by canonical metadata. Missing metadata, multiple active items, open dependencies, base drift, unsafe test commands, unexpected paths, unavailable actors, or malformed receipts fail closed.
