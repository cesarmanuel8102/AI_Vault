# IBKR Capability Matrix V1

| Capability | Status | Evidence |
|---|---|---|
| Local deterministic infrastructure | AVAILABLE | Scoped test suite |
| Fake broker lifecycle | AVAILABLE | Fake and fault suites |
| Real IBKR read-only identity | AVAILABLE | PASS |
| Real IBKR paper order write path | IMPLEMENTED_UNARMED | Paper-only executor exists; transmission requires explicit service execution plus IBKR_AUTONOMOUS_PAPER_ARMED=true |
| Test order lifecycle | UNAVAILABLE | No order lifecycle has been authorized or started |
| Real Codex synthetic invocation | AVAILABLE | Synthetic non-trading provider receipt |
| Autonomous Codex research trader | AVAILABLE_UNARMED | GPT-5.6 Sol/max default, live web search, IBKR primitive research tools, dynamic isolated equity |
| Capital-adaptive Level 4 feasibility | AVAILABLE_UNARMED | IBKR what-if + deterministic bounded-loss analysis; no fixed strategy/symbol universe |
| Auditor OS isolation | UNAVAILABLE | RESTRICTED_WINDOWS_TOKEN_NOT_PROVEN, SECRET_READ_CAPABILITY_PRESENT, BROKER_IMPORT_CAPABILITY_PRESENT, EXECUTION_LOCK_CAPABILITY_PRESENT, LIVE_DATABASE_WRITE_CAPABILITY_PRESENT |
| 30-day experiment start | UNAVAILABLE | Owner authorization required |

`AUTONOMOUS_TRADING_STATUS=BLOCKED`

No broker order submission, cancellation, or modification is currently authorized or armed. The paper execution path is implemented but remains operationally disabled until the lifecycle gates are satisfied and the paper experiment is explicitly started.
