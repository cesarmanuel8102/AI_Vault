# IBKR Capability Matrix V1

| Capability | Status | Evidence |
|---|---|---|
| Local deterministic infrastructure | AVAILABLE | Scoped test suite |
| Fake broker lifecycle | AVAILABLE | Fake and fault suites |
| Real IBKR read-only identity | AVAILABLE | PASS |
| Real IBKR order writes | UNAVAILABLE | Hard-disabled by authorization |
| Test order lifecycle | UNAVAILABLE | Not authorized |
| Real Codex Trader invocation | AVAILABLE | Synthetic non-trading provider receipt |
| Auditor OS isolation | UNAVAILABLE | RESTRICTED_WINDOWS_TOKEN_NOT_PROVEN, SECRET_READ_CAPABILITY_PRESENT, BROKER_IMPORT_CAPABILITY_PRESENT, EXECUTION_LOCK_CAPABILITY_PRESENT, LIVE_DATABASE_WRITE_CAPABILITY_PRESENT |
| 30-day experiment start | UNAVAILABLE | Owner authorization required |

`AUTONOMOUS_TRADING_STATUS=BLOCKED`

No real broker order submission, cancellation, or modification is authorized.
