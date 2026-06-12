# FRONT-LEGACY-LOCK-DIAGNOSTIC-MANUAL-STEPS-01

## Objective
Diagnose safely what may be locking `C:\AI_VAULT` after two failed quarantine rename attempts, and provide precise manual steps for releasing the lock without killing processes automatically, restarting services, deleting, moving, copying, syncing, or mutating memory/FAISS.

## Previous Repeated Lock Failures
- Previous front: `FRONT-LEGACY-PATH-CLEANUP-EXECUTE-01`
- Retry front: `FRONT-LEGACY-PATH-CLEANUP-RETRY-POST-REBOOT-01`
- Failure reason both times: `WinError 32` file lock.
- Original legacy path: `C:\AI_VAULT`
- Attempted quarantine target: `C:\AI_VAULT_LEGACY_QUARANTINE_20260611_223045`
- Rename attempted: `true`
- Rename success: `false`

## Diagnostics Attempted
Read-only diagnostics were run:

- PowerShell process command-line scan for `AI_VAULT`.
- Process path scan for `AI_VAULT`.
- Known port checks: `8090`, `8010`, `3000`, `11434`.
- Named process checks: `python`, `python3`, `uvicorn`, `node`, `ollama`, `docker`.
- Sysinternals `handle.exe` / `handle64.exe` availability check.
- Windows Search/Defender were not modified.

## Detected / Undetected Likely Lock Source
- Exact lock source: `unknown` because `handle.exe` / `handle64.exe` is not installed.
- Likely source: Python process on port `8090`, PID `244420`, may be Brain runtime/server using the legacy path.
- Likely source: Python QC runner PID `265004`, command line references `tmp_agent\strategies\mean_reversion_eq\run_phase311_bull_put_guard_qc_revalidation_2026-06-12.py` under `C:\AI_VAULT`. This was already running before this diagnostic front and was not killed.
- Possible sources: VS Code/Cursor/Codex/Kimi file watcher, Defender, Windows Search indexing.

Confidence: `MEDIUM`.

## Manual Lock Release Plan
Use one of these manual methods. Do not delete or copy anything over canonical.

### Option A - Resource Monitor
1. Open Start Menu.
2. Run `resmon`.
3. Go to CPU tab.
4. In Associated Handles search box, type `AI_VAULT`.
5. Identify process names/PIDs holding handles.
6. If process is safe/non-critical, close it manually.
7. Do NOT close system-critical processes.
8. Retry rename only after handles disappear.

### Option B - Process Explorer
1. Download/run Microsoft Sysinternals Process Explorer.
2. Use Find -> Find Handle or DLL.
3. Search `AI_VAULT`.
4. Identify process.
5. Close application manually if safe.

### Option C - handle.exe
1. Download Microsoft Sysinternals Handle.
2. Run `handle64.exe C:\AI_VAULT`.
3. Identify PID.
4. Do not force-close a handle unless the user explicitly understands the risk.

### Option D - Safe Mode
1. Reboot into Safe Mode.
2. Manually rename `C:\AI_VAULT` to `C:\AI_VAULT_LEGACY_QUARANTINE_MANUAL_YYYYMMDD_HHMMSS`.
3. Reboot normally.
4. Verify `C:\AI_VAULT_CANONICAL` still works.

## Next Retry Conditions
Before another automated retry:

- User confirms lock source was identified.
- User confirms locking app/process is closed.
- `C:\AI_VAULT` still exists.
- No process appears to hold `AI_VAULT`.
- Canonical baseline passes.
- Exact approval phrase required again:

```text
APPROVE_LEGACY_PATH_CLEANUP_EXECUTE_AI_VAULT
```

## No Mutation Proof
- Delete performed: `false`
- Rename performed: `false`
- Copy performed: `false`
- Sync performed: `false`
- Process killed: `false`
- Force action used: `false`
- Canonical memory mutated: `false`
- Canonical FAISS mutated: `false`
- Broker/API used: `false`
- Trading used by this front: `false`

## Tests Result
Smoke test created:

```text
tests/smoke/smoke_front_legacy_lock_diagnostic_manual_steps_01.py
```

Result: `16/16 passed`, `3 warnings`, `0 failed`.

## Next Locked Front
`FRONT-LEGACY-PATH-CLEANUP-RETRY-AFTER-LOCK-RELEASE-01` remains `LOCKED`.
