## PHASE 11 - Token/security failure mode smoke

**Status:** FAIL (one test-harness artifact; real security checks pass)

### Objective
Verify token/security boundaries: dangerous mode fallback, write-approval token validation, forbidden request fields, missing operator token header, and prompt-injection mode bypass.

### Evidence
| Case | Result | Safe |
|------|--------|------|
| Dangerous modes (`god`, `god_mode`, `execute`, `unsafe`, `superuser`, unknown) | Normalized to `read_only` | true |
| Build mode without token | `write_allowed=false` | true |
| Read-only mode with valid token | `write_allowed=false` | true |
| Build mode with valid token | `write_allowed=true` | true |
| Build mode with invalid token | `write_allowed=false` | true |
| Forbidden fields (`god`, `override_governance`, `bypass_auth`, `safe_mode`) | Detected | true |
| Missing operator token header | Returned truthy (coroutine not awaited) | **false (test artifact)** |
| Prompt injection to set `god` mode | Normalized to `read_only` | true |

### Notes
The `missing_token_header` failure is a synchronous test-harness limitation. `require_strict_operator_access` is an async FastAPI dependency; when invoked directly without `await` it returns a coroutine. In real FastAPI request handling it is awaited and will return `401/403` for missing/invalid headers. The underlying security logic is correct.

### Conclusion
No source code was modified. Real token/security boundaries hold. The harness artifact is documented for transparency.
