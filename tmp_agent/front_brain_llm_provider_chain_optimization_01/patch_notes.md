# Patch Notes

- Added `kimi_k2_6_cloud` provider slot with env-safe KIMI/MOONSHOT config detection.
- Provider chains now express Kimi K2.6 cloud -> Codex -> local Ollama fallback.
- Kimi K2.5 Ollama cloud is no longer the strategic primary chain entry.
- Empty provider responses are treated as failures.
- Provider chain continues after empty/timeout/config failures.
- Budget handling now caps effective timeout instead of skipping solely because nominal timeout exceeds remaining time.
- Provider metadata is surfaced to the OpenAI-compatible adapter.
