# Kimi K2.6 Live Provider Probe

This note records the safe live chat probe path for Kimi K2.6 through Brain V9.

## Route

`POST /v1/chat/completions`

Required metadata:

```json
{
  "provider_probe": true,
  "read_only": true,
  "evaluation": true
}
```

## Guarantees

- Calls the Brain router entrypoint; the OpenAI adapter does not call `LLMManager` directly.
- Uses a `provider_probe` route separate from `diagnostic_dry_run`.
- Blocks tools, memory writes, FAISS writes, and external side effects by contract.
- Skips `_save_turn` in the probe path.
- Sanitizes visible reasoning blocks such as `Thinking...done thinking` and `<think>...</think>`.
- Closes the LLM aiohttp session after the probe path to avoid unclosed session warnings.

## Verified Result

- provider_selected: `kimi_k2_6_cloud`
- model_selected: `kimi-k2.6:cloud`
- provider_status: `FAST_SUCCESS`
- content: `OK`
- local_fallback_used: `false`
- fallback_used: `false`
- no_cot_leak: `true`
- memory/semantic unchanged: `true`
- FAISS unchanged: `true`

## Limits

This is a live provider probe, not general autonomous operations mode. Normal chat/tool/autonomy escalation still requires the next governed front.
