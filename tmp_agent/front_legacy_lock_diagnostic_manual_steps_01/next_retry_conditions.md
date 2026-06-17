# Next Retry Conditions

Before another automated retry:

- User confirms lock source was identified.
- User confirms the locking app/process is closed.
- `C:\AI_VAULT` still exists.
- No process appears to hold `AI_VAULT`.
- Canonical baseline passes.
- Exact approval phrase required again:

```text
APPROVE_LEGACY_PATH_CLEANUP_EXECUTE_AI_VAULT
```

Recommended next front, still locked:

```text
FRONT-LEGACY-PATH-CLEANUP-RETRY-AFTER-LOCK-RELEASE-01
```
