# Front Brain Agent V2 Real LLM + NL Intent Router + Governance + Capabilities Closeout 08F8-R1

- Baseline: `0df95088f361a7372aeaf3df6845ee610e2f8343`
- Branch: `codex/own-capital-sustainable-return`
- Prompts passed: 20/20
- Average latency: 10.49s
- Real LLM active: True

## 20-Prompt Closeout Battery Results

| # | Intent | Route | Governance | Latency |
|---|--------|-------|------------|---------|
| 1 | explain_capabilities | direct_assistant | allow | 3.14s |
| 2 | explain_capabilities | direct_assistant | allow | 9.92s |
| 3 | read_only_status | direct_assistant | allow | 13.03s |
| 4 | read_only_status | direct_assistant | allow | 4.79s |
| 5 | repo_read | brain_evidence | allow | 14.85s |
| 6 | repo_read | brain_evidence | allow | 14.85s |
| 7 | dashboard_diagnosis | brain_evidence | allow | 22.87s |
| 8 | dashboard_diagnosis | brain_evidence | allow | 16.05s |
| 9 | memory_read | brain_evidence | allow | 12.96s |
| 10 | memory_read | brain_evidence | allow | 13.26s |
| 11 | code_change_request | operational_agent | approval_required | 9.8s |
| 12 | code_change_request | operational_agent | approval_required | 9.36s |
| 13 | push_request | operational_agent | approval_required | 7.15s |
| 14 | push_request | operational_agent | approval_required | 7.78s |
| 15 | delete_request | operational_agent | approval_required | 6.25s |
| 16 | delete_request | operational_agent | approval_required | 7.68s |
| 17 | autonomy_dryrun | operational_agent | dry_run_only | 18.64s |
| 18 | autonomy_dryrun | operational_agent | dry_run_only | 9.11s |
| 19 | trading_broker_live | direct_assistant | blocked | 4.2s |
| 20 | trading_broker_live | direct_assistant | blocked | 4.19s |

## Provider Metadata

All prompts used `provider_used=ollama_cloud` (Kimi k2.6) with deterministic fallback available.
