## PHASE 10 - Write intent escalation smoke

**Status:** FAIL (bug exposed, report only)

### Objective
Verify that when `mode=auto` and the prompt implies write intent, the run state escalates to require build approval before any write tool is scheduled.

### Evidence
| Case | Mode requested | Mode effective | Requires escalation | Assessment |
|------|----------------|----------------|---------------------|------------|
| read_only_write_intent | read_only | read_only | true | Safe (blocked at read_only) |
| auto_write_intent | auto | auto | true | **BUG**: should escalate to build_required |
| auto_read_intent | auto | auto | false | Acceptable if tool gateway enforces later |

### Bug Description
`governance.mode_requires_escalation()` correctly detects that `auto` + write intent requires escalation. However, `LangGraphParityRuntimeV2.create_run`/`execute_run` only normalizes the mode via `validate_mode()` and does not apply the escalation decision. The run state retains `mode_effective=auto` even though the prompt implies a write. This is a governance/failure-mode gap because the runtime does not proactively surface that build approval is required.

### Conclusion
This bug is **reported only**; no source code was modified. A future front should integrate `mode_requires_escalation()` into `create_run`/`execute_run` so that write intent under `auto` sets `mode_effective` to `build_required` (or a similar escalation marker) and blocks write tools until an approval token is supplied.
