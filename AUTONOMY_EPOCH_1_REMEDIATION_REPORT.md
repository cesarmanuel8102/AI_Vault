# AUTONOMY_EPOCH_1_REMEDIATION_REPORT

BASE_HEAD: c45421e7539fd63931096904cf4c0051b09c7800

FINAL_HEAD: See the final Owner report emitted after this report commit.

BRANCH: codex/ibkr-paper-auditor-gate-v2

WORKTREE: C:\AI_VAULT_IBKR

PRODUCTION_LAUNCH_FROZEN: true; `CodexIBKRMarketDataGate` is configured and disabled

PAPER_ARMED: false (no arm was performed by remediation; canonical retains pre-remediation authorization history)

DAY1_STARTED: false (AUTONOMY_EPOCH_1 was not activated; prior runs are PRE_EPOCH_HISTORY)

FINALIZER_EXECUTED: false (only Check/DryRun paths were exercised)

BROKER_WRITES_DURING_REMEDIATION: 0

AUTONOMY_PRESERVED: true

PREDEFINED_STRATEGY: false

PREDEFINED_UNIVERSE: false

NO_TRADE_VALID: true

SELF_TOOLING: true, inside the isolated workspace boundary

PERSISTENT_WORKSPACE: true, tamper-evident V2 registry

LONG_RESEARCH_CONTINUITY: true, bounded deterministic bootstrap

QUANTCONNECT_OPTIONAL_LAB: true, mediated and non-authoritative

SANDBOX_ARCHITECTURE: WSL2_NAMESPACE_CHROOT_SECCOMP_V1

SANDBOX_IDENTITY: uid=65534, no inherited Owner identity

SANDBOX_FILESYSTEM_BOUNDARY: PASS; chroot exposes only worker/workspace/scratch and required runtime files; host mounts, profile, Secrets, `.lean`, `.codex`, device/UNC/absolute host escapes denied

SANDBOX_NETWORK_BOUNDARY: PASS; socket creation, PAPER 4002, LIVE 4001, other localhost, external TCP, and DNS denied in the real worker

SANDBOX_PROCESS_BOUNDARY: PASS; cmd, PowerShell, git, codex, lean, absolute executables, and registry discovery denied in the real worker

BROKER_DIRECT_ACCESS_FROM_RESEARCH_WORKER: false

KERNEL_WRITE_ACCESS_FROM_RESEARCH_WORKER: false

DATABASE_WRITE_ACCESS_FROM_RESEARCH_WORKER: false

SECRETS_ACCESS_FROM_RESEARCH_WORKER: false

HOST_SHELL_ACCESS_FROM_RESEARCH_WORKER: false

LOCK_RECOVERY_IMPLEMENTED: true

LOCK_RECOVERY_RUNTIME_PROOF: PASS; consistent copy of canonical DB, unique named mutex, stale generation 11 recovered as generation 12, acquired and released, order_authority=false

EXPERIMENT_EPOCH_STATE: PRE_EPOCH_HISTORY; activation_required=true

PREVIOUS_HISTORY_PRESERVED: true; legacy state rows are committed by SHA-256 without rewriting them

MONDAY_IS_TRUTHFUL_EPOCH_START: IMPLEMENTED_NOT_ACTIVATED; only an Owner-bound epoch activation can establish the new start

FIRST_CODEX_BOOTSTRAP_CONTENT: deterministic 32 KiB-bounded mandate, charter, recent decisions, workspace memory, effective tool list, risk policy, market state, and untrusted-label context

PRIOR_RESEARCH_CONTINUITY: PASS

KERNEL_MANIFEST_FILE_COUNT: 48

KERNEL_MANIFEST_COMPLETENESS: PASS; deterministic authority closure and negative unmanifested-authority tests

KERNEL_HASH_STATUS: PASS; expected=actual=c3b85cb78e53f38495994d696b1aa905bcabd0b2f5e959810c69dcf1e3e0cc60

EPOCH_MANIFEST_ORDERING: PASS; prerequisites, provenance, lock, controls, and kernel precede EPOCH_MANIFEST_CREATED; service construction precedes EPOCH_STARTED

EPOCH_MANIFEST_HASHES_VALID: PASS

STALE_MARKET_PASS_FIXED: true; scheduled execution always archives and recollects, inspection is explicit/read-only

SCHEDULER_STATUS: PASS_FROZEN; task action, canonical root, working directory, exact ApprovedHead, owner SID, weekday/logon triggers, IgnoreNew policy, retries, Gateway, kernel, provenance, and lock diagnostics pass while the task remains disabled

FINALIZER_STATUS: IMPLEMENTED_AND_TESTED_NOT_EXECUTED; Check/Provision/Receipts/Activate are explicit, non-Check stages require confirmation, four stage dry-runs performed zero mutations

UNTRACKED_RUNTIME_CODE_STATUS: CANONICAL_PASS; prior capability-discovery source, test, runner, and PowerShell launcher were preserved with SHA-256 hashes under `C:\AI_VAULT_IBKR_OWNER_ARTIFACT_ARCHIVE\20260928-pre-external-reaudit` and removed from executable/importable repository paths

FOCUSED_TESTS: PASS; scheduler/launch 140, finalizer/authority 137, epoch/kernel/sandbox 94, real sandbox 12

FULL_TRACKED_TESTS: 1091 passed, 0 failed

FULL_OPERATIONAL_TESTS: PASS_FOR_EXTERNAL_REAUDIT; real WSL escape matrix PASS, copied-lock recovery PASS, scheduler ValidateOnly PASS while frozen, four finalizer dry-runs PASS, real PAPER read-only reconciliation PASS with 0 positions/0 open orders/0 executions

SKIPS: 0

PROTECTED_HASH_STATUS: PASS for the remediation worktree; all authority changes are intentional and represented by the 48-file kernel manifest

POWERSHELL_AST: REMEDIATION_ENTRYPOINTS_PASS; FULL_TRACKED_TREE_BLOCK due to 5 unrelated pre-existing parse failures in `tmp_agent/configurar_inicio_automatico.ps1`, `tmp_agent/emergency_start.ps1`, `tmp_agent/services_manager.ps1`, `tmp_agent/workspace/run_server_safe.ps1`, and `workspace/brain_openai_fastapi/run_dev.ps1`

GIT_DIFF_CHECK: PASS

CRITICAL_FINDINGS_REMAINING: 0

HIGH_FINDINGS_REMAINING: 0; remediated serialized recovery is deployed and the frozen startup diagnostic proves the current lock storage is recoverable without starting PAPER

MEDIUM_FINDINGS_REMAINING: 1 class; five unrelated tracked PowerShell files have pre-existing AST failures and were not remediated outside scope

KNOWN_RESIDUAL_RISKS: canonical retains prior clock/authorization history and an invalid legacy event chain now classified as PRE_EPOCH_HISTORY and safely anchorable without rewrite; five unrelated tracked PowerShell files retain pre-existing AST failures; finalizer, epoch activation, PAPER arming, and external adversarial audit remain outstanding

READY_FOR_EXTERNAL_REAUDIT: true

READY_FOR_PAPER_START: false

NEXT_REQUIRED_ACTION: EXTERNAL_ADVERSARIAL_REAUDIT

## Operational Evidence

- Real PAPER reconciliation: PASS, gateway PAPER, heartbeat true, query completeness true, 0 positions, 0 open orders, 0 executions, outbound read-only allowlist only, 0 broker writes.
- Runtime source provenance on canonical HEAD: PASS, no untracked executable package source.
- Scheduler ValidateOnly: overall PASS while frozen; exact ApprovedHead, owner SID, canonical path/action, Gateway, kernel, provenance, and lock storage PASS; mutations 0 and broker writes 0.
- Canonical epoch projection from a consistent DB copy: PRE_EPOCH_HISTORY, activation required, legacy chain status LEGACY_UNVERIFIED_ANCHORED, legacy state-event commitment `751d5c316dc9626c8ac5796378b47189cd489090589e645341ceead8a472c215`.
- The remediated commit series was fast-forwarded into the canonical tree. The scheduler definition was corrected and left disabled. No finalizer operation, task enablement, PAPER activation, Day 1 start, order submit, cancel, replace, global cancel, or LIVE connection was performed.
