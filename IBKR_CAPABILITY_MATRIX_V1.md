# IBKR Capability Matrix V1

| Capability | Status | Evidence |
|---|---|---|
| Local deterministic infrastructure | AVAILABLE | Scoped test suite |
| Fake broker lifecycle | AVAILABLE | Fake and fault suites |
| Real IBKR read-only identity | UNAVAILABLE | EXPECTED_ACCOUNT_IDENTITY_NOT_CONFIGURED, GATEWAY_UNAVAILABLE |
| Real IBKR order writes | UNAVAILABLE | Hard-disabled by authorization |
| Test order lifecycle | UNAVAILABLE | Not authorized |
| Real Codex Trader invocation | UNKNOWN | Not tested |
| Auditor OS isolation | PARTIAL | Restricted token and ACLs unproven |
| 30-day experiment start | UNAVAILABLE | Owner authorization required |

`AUTONOMOUS_TRADING_STATUS=BLOCKED`

No real broker order submission, cancellation, or modification is authorized.
