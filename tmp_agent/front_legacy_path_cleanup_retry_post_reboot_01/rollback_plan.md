# Rollback Plan (Retry)

**Front**: FRONT-LEGACY-PATH-CLEANUP-RETRY-POST-REBOOT-01

## Current Status

**No rollback needed** — the quarantine rename never succeeded (second attempt blocked by WinError 32). `C:\AI_VAULT` remains in its original location.

## Future Rollback (If Rename Succeeds)

If a future attempt successfully renames `C:\AI_VAULT` to a quarantine target, rollback is possible by reversing the rename.

### Rollback Action

```python
from pathlib import Path
Path("C:/AI_VAULT_LEGACY_QUARANTINE_YYYYMMDD_HHMMSS").rename(Path("C:/AI_VAULT"))
```

### Preconditions

- Quarantine target must exist
- `C:\AI_VAULT` must NOT exist (to avoid collision)
- Canonical runtime must be stopped or not dependent on legacy path

### Verification After Rollback

- `C:\AI_VAULT` exists
- Quarantine target no longer exists
- Canonical runtime still works

## When Rollback Is Needed

- If quarantine rename breaks any runtime dependency
- If user decides to restore legacy path
- If canonical system fails after rename and legacy is needed for recovery

## Note

Since the rename failed in this front (second attempt), no rollback is currently needed. The legacy path remains intact.
