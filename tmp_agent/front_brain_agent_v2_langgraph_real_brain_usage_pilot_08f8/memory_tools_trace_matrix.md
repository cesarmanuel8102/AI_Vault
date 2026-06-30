# Memory/Tools/Trace Matrix — 08F8

| Item | Expected | Observed | Result |
|---|---|---|---|
| repo read tool | Available | Listed in native helpers | PARTIAL |
| file read tool | Available | Listed in native helpers | PARTIAL |
| safe smoke test execution | Available | 113 tools loaded | PARTIAL |
| retrieve trace | Available | /v2/agent/runs/{run_id}/trace works | PASS |
| read memory/retrieval state | Read-only safe | retrieval_skipped=true; no mutation | PASS |
| no memory mutation | True | True | PASS |
| no FAISS mutation | True | True | PASS |
| trace created for chat prompt | True | True | PASS |
| trace links usable | True | True | PASS |
| dashboard displays run | True | UI served; run metadata available via API | PARTIAL |

No memory/FAISS/trading/env mutation: True

