## PHASE 8 - Trace failure mode smoke

**Status:** PASS

### Objective
Verify that `get_trace()` behaves safely under missing, malformed, and corrupted trace data.

### Evidence
| Case | Behavior | Assessment |
|------|----------|------------|
| Unknown run_id | Returns empty list | Safe |
| Malformed `trace.jsonl` (non-JSON) | Raises `JSONDecodeError` | Safe, but could be hardened |
| Corrupted existing trace file | Raises `JSONDecodeError` | Safe, but could be hardened |

### Notes
No data leakage or undefined behavior was observed. Raw `JSONDecodeError` propagates from `TraceStore` on malformed lines. A future front could add defensive parsing in `TraceStore.read()` to skip/return a warning trace. No source code was modified.

### Conclusion
Trace failure modes are safe for governance purposes. No patch applied in this front.
