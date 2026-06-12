# Kimi K2.6 Cloud Provider Setup Runbook

## Purpose

Configure Brain to prefer Kimi cloud through Ollama Cloud without storing API keys in the repository, without writing `.env`, and without exposing secrets in logs or reports.

Strategic provider priority:

1. Kimi K2.6 cloud through Ollama Cloud
2. Codex
3. Local Ollama fallback models

Brain currently reads the primary Kimi cloud tag from `KIMI_OLLAMA_MODEL`, defaulting to:

```powershell
kimi-k2.6:cloud
```

If that tag is not available in local Ollama, Brain falls through the provider chain to Codex and then local models. Do not hardcode credentials or model secrets in repo files.

## Required Runtime Prerequisite

Ollama must be installed, running, and authenticated for Ollama Cloud if cloud models require account access on the machine.

Check local Ollama availability:

```powershell
Invoke-RestMethod http://127.0.0.1:11434/api/tags | Select-Object -ExpandProperty models
```

The desired tag is:

```text
kimi-k2.6:cloud
```

The currently observed Kimi cloud tag may be:

```text
kimi-k2.5:cloud
```

Use K2.5 only as an explicit fallback/test choice, not as the strategic target, because prior autonomy probes returned empty content.

## Configure For Current PowerShell Session Only

```powershell
$env:KIMI_OLLAMA_MODEL = "kimi-k2.6:cloud"
```

This does not persist after the terminal closes.

## Configure Windows User Environment

Use the safe helper:

```powershell
.\tools\setup_kimi_k2_6_provider_user_env.ps1 -Mode User -ModelTag kimi-k2.6:cloud
```

This sets only `KIMI_OLLAMA_MODEL` in the Windows User environment. It does not write `.env` and does not store API keys.

## Status Without Printing Secrets

```powershell
.\tools\setup_kimi_k2_6_provider_user_env.ps1 -Mode Status
```

The script prints only presence, length, and redacted status for relevant variables.

## Verify Provider Config

```powershell
.\tools\verify_kimi_k2_6_provider_config.ps1
```

The verifier checks:

- `KIMI_OLLAMA_MODEL` presence and tag value.
- Ollama `/api/tags` availability.
- Whether the configured Kimi cloud tag is present.
- Brain `http://127.0.0.1:8091/v1/models` availability when runtime is up.
- Optional tiny model probe only when the tag is present and `-LiveProbe` is provided.

No headers, account data, API keys, or secrets are printed.

## Remove User Environment Variable

```powershell
.\tools\setup_kimi_k2_6_provider_user_env.ps1 -Mode RemoveUser
```

Open a new terminal after setting or removing a User environment variable.

## Run Brain After Configuration

Restart only the classified Brain V9 runtime after changing persistent environment variables. Do not touch unrelated ports.

```powershell
python -m uvicorn tmp_agent.brain_v9.main:app --host 127.0.0.1 --port 8091
```

## Test Through Brain OpenAI-Compatible Endpoint

```powershell
$body = @{
  model = "brain-v9-local"
  messages = @(@{ role = "user"; content = "Say OK." })
  stream = $false
  dry_run = $true
  metadata = @{ dry_run = $true; read_only = $true; evaluation = $true }
} | ConvertTo-Json -Depth 6

Invoke-RestMethod http://127.0.0.1:8091/v1/chat/completions -Method Post -ContentType "application/json" -Body $body
```

## Rollback

```powershell
.\tools\setup_kimi_k2_6_provider_user_env.ps1 -Mode RemoveUser
```

Then restart Brain 8091. Brain will fall back to the default model tag and provider chain.

## Hard Warnings

- Never paste secrets into ChatGPT/Codex output.
- Never commit API keys.
- Never write `.env` from these scripts.
- Never print request headers that could include authentication data.
- Never store Ollama account tokens in repo files.
