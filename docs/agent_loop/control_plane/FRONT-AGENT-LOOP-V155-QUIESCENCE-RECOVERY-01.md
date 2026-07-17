# FRONT-AGENT-LOOP-V155-QUIESCENCE-RECOVERY-01

## Status

IMPLEMENTED IN DRAFT PR #9

## Trigger

During the approved v1.5.4 deployment and trusted resume for Issue #5 / PR #6:

- trusted base advance completed successfully;
- v1.5.4 installed successfully;
- trusted v1.5.4 resume completed successfully;
- resume was required to leave `cycles=2`;
- local state was subsequently observed at `cycles=3` with `repair_local_gate_failed`;
- PR #6 HEAD remained `c94fa5c995684a8db2ecbec09ceef1cfb30c55c5`;
- a third legacy `TOKEN_EXHAUSTED` comment appeared;
- the scheduled task remained Disabled.

The merged worker runs trusted maintenance commands before entering `SingleInstanceLock`, while normal `--once`/polling work acquires that lock. A stale or concurrent worker can therefore race trusted state mutation.

## Objective

Release v1.5.5 to enforce process quiescence and transactional one-time recovery of the preserved second pilot, without creating a third pilot or touching canonical.

## Hard constraints

- Do not touch `C:\AI_VAULT_CANONICAL`.
- Do not create a new pilot Issue or pilot PR.
- Do not run Kimi until the v1.5.5 recovery has passed all invariants.
- Keep `AI_Vault_Kimi_GitHub_Worker` Disabled during deployment and recovery.
- Do not merge PR #6 before deterministic CI and Codex supervision pass.
- No trading scope.
- No credentials in logs or prompts.

## Required implementation

1. Acquire the same `state/worker.lock` for every state-mutating maintenance command, including base advance, trusted resume and recovery.
2. Stop and disable the scheduled task, then prove quiescence before any worker/state replacement or remote mutation.
3. If the lock is busy, collect bounded PID/command-line evidence for exact `agent_worker.py` processes and abort before mutation. Do not kill unrelated processes.
4. Add a one-time command restricted to Issue #5 / PR #6, such as `--trusted-v155-recover-existing-pr`.
5. Recovery preconditions must include:
   - base branch HEAD `220fa3b043d2cae8f8b084c0617027d754963335`;
   - PR #6 open, Draft, exact branch and HEAD `c94fa5c995684a8db2ecbec09ceef1cfb30c55c5`;
   - exact two pilot files;
   - installed task Disabled;
   - `trusted_v154_resume_done=true`;
   - local `cycles=3`, `status=WAITING_GITHUB`;
   - no cycle-3 commit/push;
   - cycle-3 failure evidence is `MODEL_CONTENT_FAILURE` after the trusted resume.
6. Recovery must transactionally preserve and restore exact state bytes, Issue/PR bodies, complete labels and notification ledger.
7. On success recovery must set:
   - `cycles=2`;
   - `status=WAITING_GITHUB`;
   - `last_head_sha=c94fa5c995684a8db2ecbec09ceef1cfb30c55c5`;
   - `local_retry_count=0`;
   - `terminal_notified=false`;
   - `trusted_v155_recovery_done=true`;
   - Issue #5 and PR #6 exactly `loop:repairing`.
8. Seed stable notification dedupe from all existing matching legacy terminal comments so no fourth duplicate is posted. Do not delete historical comments automatically.
9. Record bounded events for quiescence, recovery, rollback and exact process identity.
10. Update deployment script to leave the task Disabled and never run `--once` implicitly.

## Behavioral tests

- A process holding `worker.lock` causes trusted resume/recovery to fail before any local or remote mutation.
- Windows test with a real second process holding the lock.
- Linux equivalent lock contention test.
- Recovery success from the exact Issue #5 / PR #6 fixture.
- Failure at each local/remote mutation point restores byte-identical state and original bodies/labels.
- Three existing legacy `TOKEN_EXHAUSTED` comments do not produce a fourth.
- Deployment and recovery never invoke Kimi.
- Exactly one later explicit `--once` consumes cycle 3.

## Exit criteria

- Windows and Ubuntu contracts green.
- Independent audit finds no P0/P1.
- v1.5.5 deployed with task Disabled.
- one-time recovery returns `RECOVERED_EXISTING_PR_V155`.
- state is exactly cycle 2 before the explicit one-shot.
- canonical untouched.


## Implementation summary

Implemented in `control-plane/v155-quiescence-recovery`:

- `WORKER_VERSION = 1.5.5`.
- Trusted maintenance commands now acquire `state/worker.lock` before state-mutating work:
  - `--trusted-resume-existing-pr`;
  - `--trusted-base-advance-existing-pr`;
  - `--trusted-v154-resume-existing-pr`;
  - `--trusted-v155-recover-existing-pr`.
- Lock contention now fails closed and includes bounded sanitized process evidence for exact worker/config command lines.
- `--trusted-v155-recover-existing-pr 5` is permanently restricted to Issue #5 / PR #6.
- Recovery validates the exact preserved pilot state and resets it to `cycles=2`, `WAITING_GITHUB`, `loop:repairing` without running Kimi or pushing.
- Recovery seeds `notification_keys` from markerless legacy `TOKEN_EXHAUSTED` comments to prevent a fourth duplicate notification.
- `Repair-AgentLoop-v1.5.5.ps1` and `Repair-AgentLoop-v1.5.5.Core.psm1` install v1.5.5, run contracts, execute only the one-time recovery command, and leave the scheduled task Disabled.

## Local validation

Windows local validation executed:

- `python -m py_compile scripts/agent_loop/local_worker/agent_worker.py` — PASS
- `python tests/contract/test_agent_loop_worker_v153_base_advance.py` — PASS
- `python tests/contract/test_agent_loop_worker_v153_regression.py` — PASS
- `python tests/contract/test_agent_loop_worker_v154_repair.py` — PASS
- `python tests/contract/test_agent_loop_worker_v154_transaction_notifications.py` — PASS
- `powershell -NoProfile -ExecutionPolicy Bypass -File tests/contract/test_agent_loop_worker_v154_deploy_rollback.ps1` — PASS
- `python tests/contract/test_agent_loop_worker_v155_quiescence_recovery.py` — PASS
- `powershell -NoProfile -ExecutionPolicy Bypass -File tests/contract/test_agent_loop_worker_v155_deploy_recovery.ps1` — PASS
- `git diff --check` — PASS

## Current live pilot note

During this hotfix work, PR #6 was observed externally returning to `loop:token-exhausted` with a third legacy `TOKEN_EXHAUSTED` comment. This PR does not modify PR #6; the v1.5.5 recovery command is designed to transactionally repair that preserved second-pilot state after PR #9 is reviewed and deployed.
