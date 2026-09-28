# AUTONOMY_EPOCH_1 Security Remediation Implementation Plan

> Execute this plan in `C:\AI_VAULT_IBKR_REMEDIATION` on branch
> `codex/autonomy-epoch1-security-remediation`. Do not run the production
> finalizer, arm PAPER, start Day 1, or submit/cancel/modify broker orders.

**Goal:** Preserve autonomous research and self-tooling while making research
execution unable to reach broker, credentials, host processes, protected files,
or authoritative state, then repair lock, epoch, provenance, and launch defects.

**Architecture:** Model-authored Python runs through a host broker into a WSL2
worker isolated by user/mount/PID/network namespaces, chroot, dropped
capabilities, `no_new_privs`, seccomp, and resource limits. Host-controlled
execution, manifests, epochs, and scheduler validation remain fail closed.

**Tech stack:** Python 3.11, Pydantic, SQLite, pytest, Windows PowerShell 5.1,
WSL2 Ubuntu, Linux namespaces, libseccomp, Git.

---

## File Structure

- `ibkr_paper_30d/research_sandbox.py`: host-side typed request, WSL command
  construction, exchange validation, timeout handling, and artifact hashing.
- `ibkr_paper_30d/research_worker_linux.py`: trusted Linux worker, resource
  limits, seccomp installation, in-process execution, and structured result.
- `scripts/run_research_worker_wsl.sh`: namespace, mount, chroot, identity, and
  lifecycle launcher.
- `ibkr_paper_30d/autonomy_workspace.py`: sandbox delegation and V2 registry
  integrity.
- `ibkr_paper_30d/autonomy_toolbox.py`: typed QuantConnect mediation.
- `ibkr_paper_30d/execution_lock.py`: lock inspection and serialized recovery.
- `ibkr_paper_30d/experiment_epoch.py`: append-only epoch definition and
  bounded continuity state.
- `ibkr_paper_30d/autonomy_bootstrap.py`: deterministic first-process context.
- `ibkr_paper_30d/kernel_manifest.py`: deterministic authority closure.
- `ibkr_paper_30d/epoch_manifest.py`: corrected manifest inputs and hashes.
- `ibkr_paper_30d/runtime_provenance.py`: tracked-source/import verification.
- `ibkr_paper_30d/day1_launch.py`: repaired ordering and gate integration.
- `RUN_IBKR_MARKET_DATA_GATE.ps1`: fresh-session-only market gate behavior.
- `RUN_IBKR_DAY1_SERVICE.ps1`: approved HEAD and dry-run validation.
- `FINALIZE_IBKR_PREREQUISITES.ps1`: explicit dry-run/provision/activation
  boundaries without implicit PAPER activation.
- `tests/ibkr_paper_30d/`: focused adversarial and integration tests.

## Task 1: Pin The Audit Baseline And Safety Invariants

**Files:**
- Create: `tests/ibkr_paper_30d/test_remediation_invariants.py`
- Modify: `ibkr_paper_30d/autonomy_workspace.py`

1. Add failing tests proving current Owner-context scripts can see protected
   paths, broker TCP, and host executables; mark them against the new sandbox
   interface rather than executing broker writes.
2. Add tripwires that fail if remediation tests call `placeOrder`,
   `cancelOrder`, `reqGlobalCancel`, or connect to LIVE ports.
3. Run the focused test and confirm the expected failures.
4. Introduce a sandbox protocol dependency in `AutonomyWorkspace`; remove the
   direct `subprocess.run([sys.executable, ...])` implementation.
5. Re-run and retain failures until Task 2 supplies the implementation.
6. Commit: `test: pin autonomy remediation security invariants`.

## Task 2: Implement The WSL2 Namespace Sandbox

**Files:**
- Create: `ibkr_paper_30d/research_sandbox.py`
- Create: `ibkr_paper_30d/research_worker_linux.py`
- Create: `scripts/run_research_worker_wsl.sh`
- Create: `tests/ibkr_paper_30d/test_research_sandbox.py`
- Modify: `ibkr_paper_30d/autonomy_workspace.py`

1. Add contract tests for request validation, path canonicalization, bounded
   arguments, timeout, output truncation, and fail-closed WSL unavailability.
2. Add actual worker probes for protected Windows paths, `/mnt/c`, environment,
   process spawning, socket/DNS/HTTP, symlink escape, and arbitrary executables.
3. Confirm tests fail before implementation.
4. Implement the host broker and Linux launcher with namespace/chroot setup.
5. Install seccomp in the trusted worker before `runpy.run_path`; deny network,
   exec, fork/clone, ptrace, mount, and namespace syscalls.
6. Apply CPU, address-space, file-size, open-file, and output limits. Kill the
   Linux process group on timeout.
7. Validate generated artifact paths/hashes on the host and return a structured
   run receipt.
8. Run the actual escape matrix and focused unit tests.
9. Commit: `feat: isolate model research code in WSL sandbox`.

## Task 3: Make Workspace Persistence Tamper-Evident

**Files:**
- Modify: `ibkr_paper_30d/autonomy_workspace.py`
- Modify: `tests/ibkr_paper_30d/test_autonomy_workspace.py`

1. Add failing tests for modified artifacts, malformed/truncated registry tails,
   duplicate active paths, V1 migration, atomic writes, and bounded summaries.
2. Implement V2 records with previous-record hash, record hash, operation,
   artifact hash, and cycle identity.
3. Verify content against the latest active record on every read/list/summary.
4. Keep valid V1 history readable through a migration-anchor event.
5. Commit: `feat: make autonomy workspace registry tamper evident`.

## Task 4: Complete Mediated QuantConnect

**Files:**
- Modify: `ibkr_paper_30d/autonomy_toolbox.py`
- Create: `tests/ibkr_paper_30d/test_quantconnect_mediation.py`

1. Add tests for typed operations and status values, plus rejection of LIVE,
   brokerage, raw commands, arbitrary paths, shell syntax, and credential
   output.
2. Implement operation-specific argument builders and bounded redacted output.
3. Ensure unavailable/failed QuantConnect never blocks core research.
4. Prove the research worker cannot invoke Lean directly.
5. Commit: `feat: mediate optional QuantConnect research`.

## Task 5: Implement Serialized Stale-Lock Recovery

**Files:**
- Modify: `ibkr_paper_30d/execution_lock.py`
- Modify: `ibkr_paper_30d/day1_launch.py`
- Modify: `tests/ibkr_paper_30d/test_execution_lock.py`
- Modify: `tests/ibkr_paper_30d/test_day1_launch.py`

1. Add failing tests for dead PID/stale heartbeat, PID reuse, live owner, held or
   abandoned mutex, stale DB with active mutex, interrupted transaction, two
   contenders, reboot identity, and old-generation exclusion.
2. Add immutable `LockInspection` and a production process-observer interface.
3. Serialize inspection/recovery/acquire under one named-mutex handle.
4. Append recovery evidence and advance generation atomically; ambiguous cases
   return Owner action required.
5. Wire recovery into `run_day1_launch` before normal acquisition.
6. Run a safe proof using a copy of the observed stale DB and unique mutex.
7. Commit: `fix: recover proven stale execution locks safely`.

## Task 6: Add Truthful Epoch State Without Rewriting History

**Files:**
- Create: `ibkr_paper_30d/experiment_epoch.py`
- Create: `tests/ibkr_paper_30d/test_experiment_epoch.py`
- Modify: `ibkr_paper_30d/autonomous_service.py`
- Modify: `ibkr_paper_30d/autonomous_state.py`

1. Add tests proving legacy events remain byte-identical and are classified as
   `PRE_EPOCH_HISTORY`.
2. Add append-only epoch-definition and projection logic using existing state
   tables, with explicit Owner authorization required for activation.
3. Bind clock snapshots, cycle counts, ledger horizon, and service state to the
   epoch ID.
4. Implement a dry-run rebaseline preview; do not activate it in remediation.
5. Commit: `feat: introduce truthful autonomous experiment epochs`.

## Task 7: Build Bounded First-Process Continuity

**Files:**
- Create: `ibkr_paper_30d/autonomy_bootstrap.py`
- Create: `tests/ibkr_paper_30d/test_autonomy_bootstrap.py`
- Modify: `ibkr_paper_30d/autonomous_runtime.py`
- Modify: `ibkr_paper_30d/autonomous_research.py`

1. Add tests for exact bootstrap fields, deterministic ordering, byte/record
   limits, empty first run, malformed records, untrusted labelling, and no audit
   document leakage.
2. Build recent accepted-decision and workspace research summaries with fixed
   relevance/recency limits.
3. Include epoch, remaining horizon, permissions, constraints, PAPER identity
   class, current state, tools, QC status, hypotheses, and unresolved questions.
4. Supply bootstrap only on the first invocation of each service process.
5. Commit: `feat: restore bounded autonomous research continuity`.

## Task 8: Derive And Enforce The Authority Kernel

**Files:**
- Create: `ibkr_paper_30d/kernel_manifest.py`
- Create: `tests/ibkr_paper_30d/test_kernel_manifest_closure.py`
- Modify: `ibkr_paper_30d/epoch_manifest.py`
- Regenerate: `IMMUTABLE_EXECUTION_KERNEL_MANIFEST.json`

1. Add tests that inject an authority import/call edge and require manifest
   generation to include it or fail.
2. Implement deterministic Python AST closure and reviewed PowerShell/dynamic
   roots. Reject untracked, missing, escaping, duplicate, or unhashed files.
3. Classify every entry by authority role and hash canonical bytes.
4. Regenerate the manifest from committed sources and verify all hashes.
5. Commit: `feat: derive immutable execution kernel closure`.

## Task 9: Correct Epoch Manifest Semantics And Ordering

**Files:**
- Modify: `ibkr_paper_30d/epoch_manifest.py`
- Modify: `ibkr_paper_30d/day1_launch.py`
- Modify: `tests/ibkr_paper_30d/test_epoch_manifest.py`
- Modify: `tests/ibkr_paper_30d/test_day1_launch.py`

1. Add failing tests for exact effective-payload hash, actual presented tool
   manifest, receipt byte hashes, risk policy hash, complete kernel hash, and
   blocked-launch absence.
2. Separate `EPOCH_MANIFEST_CREATED` from `EPOCH_STARTED` evidence.
3. Construct and hash the finalized bootstrap/prompt/tool payload before
   service startup, but write only after all gates and kernel verification pass.
4. Emit start evidence only after service construction and initial safety gate.
5. Commit: `fix: bind epoch provenance to effective launch state`.

## Task 10: Enforce Runtime Source Provenance

**Files:**
- Create: `ibkr_paper_30d/runtime_provenance.py`
- Create: `tests/ibkr_paper_30d/test_runtime_provenance.py`
- Modify: `ibkr_paper_30d/day1_launch.py`

1. Add tests for untracked package modules, alternate import roots, modified
   tracked modules, symlinks, ignored executable source, and approved deployed
   material.
2. Resolve loaded/importable production modules and require tracked canonical
   files matching the approved commit/tree hashes.
3. Integrate the gate before lock acquisition and service construction.
4. Produce a non-secret classification report for runtime artifacts.
5. Commit: `feat: fail closed on unproven runtime source`.

## Task 11: Remove Stale Market PASS Reuse

**Files:**
- Modify: `RUN_IBKR_MARKET_DATA_GATE.ps1`
- Modify: `tests/ibkr_paper_30d/test_prerequisite_finalizer.py`
- Modify: `tests/ibkr_paper_30d/_market_gate_evidence_harness.ps1`

1. Add tests showing Friday/session-old PASS cannot launch Monday.
2. Remove unconditional existing-PASS short circuit in scheduled mode.
3. Always collect fresh scheduled evidence; preserve the Python runtime gate.
4. Keep non-scheduled status inspection read-only and explicit.
5. Commit: `fix: require fresh scheduled market evidence`.

## Task 12: Add Scheduler And Launch Dry-Run Gates

**Files:**
- Modify: `RUN_IBKR_DAY1_SERVICE.ps1`
- Create: `ibkr_paper_30d/scheduler_validation.py`
- Create: `tests/ibkr_paper_30d/test_scheduler_validation.py`
- Modify: `tests/ibkr_paper_30d/test_day1_launch.py`

1. Add tests for approved HEAD, action, arguments, user context, overlap policy,
   working directory, task disabled/frozen state, Gateway, kernel, provenance,
   and lock diagnostics.
2. Implement `-ValidateOnly` as a complete non-mutating structured dry run.
3. Refuse launch when HEAD differs from the deployed approved SHA.
4. Do not modify or re-enable the production task.
5. Commit: `feat: validate scheduled launch without activation`.

## Task 13: Separate Finalizer Stages

**Files:**
- Modify: `FINALIZE_IBKR_PREREQUISITES.ps1`
- Modify: `tests/ibkr_paper_30d/test_prerequisite_finalizer.py`

1. Add AST/contract tests for `Check`, `Provision`, `Receipts`, and `Activate`
   stages and a zero-mutation dry-run.
2. Require explicit activation for clock/authorization/task changes.
3. Keep provisioning and receipt refresh incapable of arming PAPER.
4. Report planned security, service, firewall, account, and scheduler mutations.
5. Do not execute the finalizer.
6. Commit: `refactor: separate prerequisite finalizer authority stages`.

## Task 14: Full Adversarial Verification And Report

**Files:**
- Create: `AUTONOMY_EPOCH_1_REMEDIATION_REPORT.md`
- Modify only generated manifests/evidence explicitly required by tests.

1. Run focused sandbox, lock, epoch, bootstrap, manifest, provenance, market,
   scheduler, and finalizer suites.
2. Run the complete tracked suite with bytecode/cache writes disabled.
3. Run operational discovery and explain every additional test or skip.
4. Run actual worker filesystem/process/network/credential escape probes.
5. Run safe stale-lock recovery against a copied DB and unique mutex.
6. Perform read-only current PAPER reconciliation; verify zero positions,
   orders, executions, and remediation broker writes.
7. Parse all PowerShell with the AST parser; run `git diff --check` and manifest
   hash verification.
8. Confirm PAPER unarmed, Day 1 not started, finalizer not executed, and the
   production scheduler not enabled by remediation.
9. Write the exact mandated remediation report, including unresolved blockers.
10. Commit: `docs: report autonomy epoch security remediation`.

## Integration Gate

Do not merge or copy changes into `C:\AI_VAULT_IBKR` unless every critical
escape probe is denied, stale-lock recovery is unambiguous, kernel closure is
complete, the full tracked suite passes, and the Owner separately authorizes
canonical integration. The next required action remains an independent
external adversarial re-audit.
