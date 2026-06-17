# Manual Lock Release Plan

## Option A - Resource Monitor
1. Open Start Menu.
2. Run `resmon`.
3. Go to CPU tab.
4. In Associated Handles search box, type `AI_VAULT`.
5. Identify process names/PIDs holding handles.
6. If process is safe/non-critical, close it manually.
7. Do NOT close system-critical processes.
8. Retry rename only after handles disappear.

## Option B - Process Explorer
1. Download/run Microsoft Sysinternals Process Explorer.
2. Use Find -> Find Handle or DLL.
3. Search `AI_VAULT`.
4. Identify process.
5. Close application manually if safe.

## Option C - handle.exe
1. Download Microsoft Sysinternals Handle.
2. Run: `handle64.exe C:\AI_VAULT`.
3. Identify PID.
4. Do not force-close handle unless user explicitly understands risk.

## Option D - Safe Mode
1. Reboot into Safe Mode.
2. Manually rename `C:\AI_VAULT` to `C:\AI_VAULT_LEGACY_QUARANTINE_MANUAL_YYYYMMDD_HHMMSS`.
3. Reboot normally.
4. Verify `C:\AI_VAULT_CANONICAL` still works.

## Hard Rules
- No deletion.
- No copy over canonical.
- Rename only.
- Rollback is renaming the quarantine path back to `C:\AI_VAULT`.
