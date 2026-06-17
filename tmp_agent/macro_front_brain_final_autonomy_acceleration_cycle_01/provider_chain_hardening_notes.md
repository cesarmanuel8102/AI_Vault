# Provider Chain Hardening Notes

Implemented as a minimal metadata hardening patch.

- `tmp_agent/brain_v9/core/llm.py` continues to route primary to `kimi_k2_6_cloud`, implemented through Ollama Cloud model tag `kimi-k2.6:cloud` or `KIMI_OLLAMA_MODEL` override.
- Empty provider responses are treated as failures and the chain continues.
- Added explicit metadata aliases:
  - `cloud_provider_available`
  - `codex_provider_available`
- `tmp_agent/brain_v9/api/openai_compat.py` now exposes those aliases in safe response metadata.
- No provider secrets were added.
- No `.env` files were written.
- No memory/semantic writes were performed.

Current limitation: Kimi K2.6 tag is missing in Ollama, so Codex/local fallback remains required until operator enables the tag.
