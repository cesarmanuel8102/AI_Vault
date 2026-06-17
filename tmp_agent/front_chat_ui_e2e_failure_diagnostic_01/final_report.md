# FRONT-CHAT-UI-E2E-FAILURE-DIAGNOSTIC-01 Final Report

- status: `CHAT_UI_E2E_FAILURE_DIAGNOSTIC_COMPLETED`
- functional_commit: `d1332e2`
- ledger_commit: `bde9eea`
- head_after: `bde9eea`
- remote_branch_head: `bde9eea`
- local_equals_remote_branch: `True`

## Diagnosis
- primary_failure: `UI_NOT_REACHABLE`
- secondary_failures: `OPENAI_COMPATIBILITY_MISSING, TIMEOUT, STREAMING_SSE_MISMATCH, RETRIEVAL_INJECTION_FAILURE, CANONICAL_PATH_OK_BUT_UI_NOT_CONNECTED`
- confidence: `HIGH`
- recommended_fix_front: `FRONT-CHAT-UI-DOCKER-NETWORKING-FIX-01`

## Runtime Observations
- open_webui_reachable: `False`
- backend_reachable: `True`
- ollama_reachable: `True`
- direct_backend_chat_passed: `False`
- open_webui_chat_passed: `False`
- retrieval_injection_passed: `False`
- streaming_compatible: `False`

## Safety
- canonical_memory_mutated: `false`
- canonical_faiss_mutated: `false`
- semantic_memory_lines: `1715`
- faiss_ids: `1616`
- faiss_ntotal: `1616`
- process_killed: `false`
- force_action_used: `false`

## Final
- staged_empty_after: `True`
- unstaged_tracked_empty_after: `True`
- roadmap_valid: `true`
- tests_passed: `true`

## Next
`FRONT-CHAT-UI-DOCKER-NETWORKING-FIX-01` remains locked.
