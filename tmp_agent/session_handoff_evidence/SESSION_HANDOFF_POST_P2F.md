# AI_VAULT Session Handoff — Post P2-F

## Current canonical HEAD
bf02e2a7

## Branch
codex/own-capital-sustainable-return

## Closed work
- TOOL-01A/B: Enable governed real tools permission gate in chat (db21ae89)
- TOOL-01 executor tools: Register governed real tools in executor (bbec35a2)
- DASH-02: Fix stale dashboard routes with read-only aliases (75811d31)
- Ledger checkpoint: Record TOOL-01 and DASH-02 migration checkpoint (b4ac7d8e)
- .gitignore hygiene: Ignore local runtime and protected AI_VAULT artifacts (4f23958d)
- P2-F GitHubSourceConnector: Add read-only dry-run connector (9b2803d7)
- P2-F ledger checkpoint: Record P2-F GitHub Source Connector checkpoint (bf02e2a7)

## Important decisions
- DASH-V2-MOUNT was REJECTED and REVERTED due to startup blocking risk.
- Do NOT recommit old implementation. If retrying, use lazy initialization only.

## Dirty tree policy
Protected files (memory/semantic, tmp_agent/strategies, tmp_agent/reports, nul) remain dirty in working tree but must NEVER be staged or committed.

## Open questions
1. validate_security_3g.py, validate_security_4d_canary.py, validate_security_4d_evidence.py — commit as security audit artifacts, archive, ignore, or discard?
2. tmp_agent/bor3_llm_audit.py — commit as audit tool or archive?
3. DASH-V2-MOUNT evidence in tmp_agent/dashboard_v2_mount_evidence/ — keep as rejected evidence or archive?
4. Next roadmap item after P2-F?

## Recommended next prompt
Start with validate_security_*.py audit before any new feature work.

## Tests status at handoff
- endpoints_auth: 8 passed / 0 failed
- chat_routing: 33 passed / 0 failed
- dashboard_stale_routes: 7 passed / 0 failed
- Total: 48 passed / 0 failed

## Created
Generated: 2026-05-27T06:02:58.655175+00:00
