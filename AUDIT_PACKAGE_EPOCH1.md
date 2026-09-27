# ADVERSARIAL SECURITY AUDIT — AUTONOMY_EPOCH_1 preparation

Auditor: GLM (host assistant, no Codex credits consumed)
Date: 2026-09-27
Scope: worktree `C:\AI_VAULT_IBKR_EPOCH1` at the commit described in the
final report; the entire epoch-1 diff against canonical `fe8c587`.
Method: static inspection + deterministic test suite + targeted escape
probes. No Codex invocation, no broker writes.

## Audit checklist (Parte 15)

| Area | Verdict | Evidence |
|---|---|---|
| Prompt steering / hidden strategy constraints | **INFO** | New charter contains zero strategy prescriptions (test_autonomy_charter.py: 15 tests pin freedom fields, no universe/strategy/indicator strings). Counterfactual ritual, per-cycle active-search duty and conditional NO_TRADE validity were REMOVED. No hidden numeric targets (test_mandate_hardening.py). |
| Self-tooling escape paths | **LOW residual** | `AutonomyWorkspace._resolve` enforces: relative paths only, no `..`, no drive/abs paths, resolution must stay under workspace root; `.py` artifacts only in `tools/`; scripts only run from `tools/` as `python -I` subprocess with env = {SYSTEMROOT, WINDIR, TEMP, TMP} only. PATH removed so scripts cannot spawn codex/lean/git (test_script_cannot_spawn_external_clis). Registry append-only with hashes (test_workspace_registry_is_append_only_and_hashed). |
| Broker-write bypass from model tools | **PASS** | Workspace/toolbox/epoch modules contain zero order-write API references (grep placeOrder/cancelOrder/reqGlobalCancel/whatIfOrder/transmit=True → 0 matches). Research results structurally carry no decision/proposal/order fields (test_custom_tool_failure_yields_no_trading_permission). |
| LIVE route bypass | **PASS** | No LIVE ports (4001/7496/7497) anywhere in new modules; kernel untouched (PAPER_HOSTS/4002 constants intact in ibkr_research_tools/ibkr_readonly_session; test_autonomous_architecture_contract green). |
| Credentials exposure | **PASS** | Script env contains no IBKR/SECRET/TOKEN/PASSWORD vars (test_script_environment_has_no_broker_credentials); no raw account id in epoch manifest (DU-check test); redaction module untouched. |
| Arbitrary mutation of immutable kernel | **PASS** | Workspace writes confined to workspace root (escape tests). Kernel manifest hashes 22 files; `verify_kernel_manifest` detects mutation (test_kernel_manifest_verification_detects_mutation). Kernel files are not in workspace reach. Note: enforcement of kernel integrity at runtime is inherited from existing immutable-hash infrastructure; the epoch manifest adds provenance hashing. |
| QuantConnect / IBKR cross-contamination | **PASS** | QuantConnect path is `lean` CLI read-only whitelist (config/list/report/data/backtest/research/object-store/logs/cloud), live/`lean live` rejected (test_quantconnect_command_whitelist_blocks_live). QC cannot touch IBKR state; IBKR tools unchanged. |
| Workspace persistence | **PASS** | Artifacts persist across AutonomyWorkspace instances and cycles (test_workspace_artifacts_persist_across_workspace_instances; test_workspace_context_flows_into_prompt_across_cycles). |
| Stale state | **INFO** | Workspace summary passes recent artifacts; no freshness prescription (capability only). Epoch manifest is regenerated at each launch (no stale reuse). |
| Execution duplication | **PASS** | Unchanged: single-writer lock, idempotency keys, accepted_cycle_key UNIQUE all intact (test_autonomous_runtime/test_execution_lock green). |
| Scheduled startup | **PASS** | Scheduled task untouched (CodexIBKRMarketDataGate, weekly 09:35 ET + logon trigger, verified read-only). day1_launch now also writes the observational epoch manifest pre-service. |
| Recovery after reboot | **PASS** | Unchanged lock/heartbeat/kill-switch machinery; new modules hold no locks, no OS resources. |
| Epoch reconstruction | **PASS** | epoch manifest records git sha, prompt hash, tool hash, kernel hash, policy hashes, QC status, flags; canonical JSON; hashable (test_epoch_manifest_is_correct_and_hashable). |

## Residual risks (all LOW/INFO — none block Monday)

1. **LOW** — Research scripts execute arbitrary Python in a subprocess with
   stdlib + installed site-packages. Malicious self-harm (e.g. corrupting
   the workspace itself) is possible but self-limiting: the workspace is
   model-owned, and the experiment ledger/kernel/credentials are outside
   its reach. A hostile script cannot escalate: no PATH, no credentials, no
   broker, no kernel imports (probes tested).
2. **LOW** — A research script can open raw TCP sockets (stdlib). It cannot
   authenticate to IBKR (no credentials) and the gateway binds 4002 for
   API sessions with client-id arbitration; order submission additionally
   requires executor authority the script never receives. Residual: a
   script could attempt unauthenticated connections; the gateway's own
   API handshake plus absence of any write path makes this inert.
3. **INFO** — QuantConnect capability availability depends on the locally
   configured `lean` CLI credentials; the tool reports availability
   honestly and is optional; failure never blocks trading (tests pin
   `required: False`).
4. **INFO** — The epoch manifest's `effective_prompt_hash` hashes the
   prompt-builder source; a refactor of unrelated lines changes the hash
   (conservative, not a security issue).
5. **INFO** — `test_prerequisite_finalizer` and one finalizer harness test
   require the canonical repo root (`C:\AI_VAULT_IBKR`) and cannot pass
   inside the worktree; they must be re-run after integration (planned).

## CRITICAL/HIGH findings

None. No unresolved CRITICAL or HIGH finding involving execution
authority exists. READY_FOR_MONDAY = YES (subject to final integration
verification in canonical repo, per Parte 16).