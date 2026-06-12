# FRONT-CHAT-UI-BRAIN-PROVIDER-CONFIG-8091-01

## Status
`OPENWEBUI_BRAIN_PROVIDER_8091_RUNBOOK_CREATED`

## Provider Settings
- Base URL: `http://host.docker.internal:8091/v1`
- Model: `brain-v9-local`
- API key: use a local dummy value if Open WebUI requires one.

## Validation
From the `open-webui` container, both `/v1/models` and `/v1/chat/completions` were reachable on port 8091.

## Manual Steps
1. Open Open WebUI admin/provider settings.
2. Add an OpenAI-compatible provider.
3. Set base URL to `http://host.docker.internal:8091/v1`.
4. Set model to `brain-v9-local`.
5. Save and send a short test message.

## Revert
Remove or disable the provider entry, or switch base URL after 8090 switchover succeeds.

## Safety
No Docker destructive action, no credential read/write, no memory/FAISS/trading mutation.
