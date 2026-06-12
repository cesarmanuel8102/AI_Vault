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
