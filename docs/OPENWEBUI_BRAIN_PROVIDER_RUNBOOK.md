# Open WebUI Brain Provider Runbook

## Current Recommended Provider
- Base URL: `http://host.docker.internal:8091/v1`
- Model: `brain-v9-local`
- API key: use a dummy/local placeholder if Open WebUI requires one.

## Validate From Host
```powershell
Invoke-WebRequest http://127.0.0.1:8091/v1/models -UseBasicParsing
```

## Validate From Open WebUI Container
```bash
curl http://host.docker.internal:8091/v1/models
```

## Chat Completion Probe
```bash
curl -s http://host.docker.internal:8091/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"model":"brain-v9-local","messages":[{"role":"user","content":"Respond briefly as Brain."}],"stream":false}'
```

## How To Confirm It Is Brain, Not Direct Ollama
- Response object should be `chat.completion`.
- Model should resolve to `brain-v9-local`.
- Response should include Brain governance metadata under the adapter response when available.
- Answers should preserve Brain router/governance behavior rather than direct model behavior.

## Rollback
Remove or disable the Open WebUI provider entry and return to the previous provider. Do not delete Brain runtime files or modify memory/semantic artifacts.

## 8090 Note
Port `8090` remains pending until its owner can be classified safely. Do not kill unknown 8090 processes. Use `8091` until switchover is explicitly safe.

## Final Autonomy Provider Note

Updated: 2026-06-12T19:10:30.941341+00:00

- Primary intended cloud provider: `kimi_k2_6_cloud` via Ollama Cloud tag `kimi-k2.6:cloud`.
- Current blocking condition: `KIMI_K2_6_OLLAMA_TAG_MISSING`.
- Temporary K2.5 tag exists but returned empty content in diagnostic probing; do not treat it as autonomy-ready.
- Provider metadata should be inspected for `cloud_provider_available`, `codex_provider_available`, and `local_fallback_used`.
- No `.env` writes or secrets printing are required by the committed runbook.

