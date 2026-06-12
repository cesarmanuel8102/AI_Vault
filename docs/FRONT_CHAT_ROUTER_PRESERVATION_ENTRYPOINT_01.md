# FRONT-CHAT-ROUTER-PRESERVATION-ENTRYPOINT-01

## External Audit Finding
The external audit warned that a naive OpenAI-compatible adapter would likely bypass governance by calling `LLMManager.query()` directly. It also found that `UnifiedChatRouter` exists as an orphan and that the runtime relies on `BrainSession.chat()` as the governed fallback path.

## Why A Naive Adapter Is Unsafe
An adapter that directly maps `/v1/chat/completions` to `LLMManager.query()` would skip intent detection, route selection, Tool01/GAK governance, permission gates, response hygiene, no-CoT filtering, curated lookup handling, and existing session controls.

## Files Inspected
- `tmp_agent/brain_v9/core/intent.py`
- `tmp_agent/brain_v9/core/session.py`
- `tmp_agent/brain_v9/main.py`
- `brain/unified_chat_router.py`
- direct `LLMManager.query` call sites discovered in mapping evidence

## Canonical Entrypoint Design
- entrypoint file: `tmp_agent/brain_v9/core/router_entrypoint.py`
- public function: `handle_user_message(message, room="default", context=None, dry_run=False)`
- output fields: `content, route, intent, evidence_ids, governance_applied, no_cot_leak, canonical_path, errors, latency_ms`
- future adapter policy: `/v1/chat/completions must call handle_user_message and must never call LLMManager.query directly`

## Files Changed
- `tmp_agent/brain_v9/core/router_entrypoint.py`
- `tmp_agent/brain_v9/main.py`
- `tests/smoke/smoke_front_chat_router_preservation_entrypoint_01.py`

## IntentDetector Integration
`handle_user_message()` calls `IntentDetector.detect()` at the boundary before selecting a route. `BrainSession.chat()` may still perform its own internal detection, but the future adapter no longer has a reason to bypass the canonical boundary.

## Governance / No-CoT Filtering
The entrypoint delegates live execution to `BrainSession.chat()` and then applies an entrypoint-level response hygiene pass. It strips `raw_chain_of_thought` / `private_reasoning` fields and rewrites visible output if raw chain-of-thought markers appear.

## Native /chat Wiring
The native `/chat` route now delegates its normal governed path to `handle_user_message()`. Existing early safety/auth fastpaths remain in `main.py`; no `/v1/chat/completions` route was created in this front.

## Future /v1/chat/completions Rule
Any future OpenAI-compatible adapter must call `handle_user_message()`. It must not call `LLMManager.query()` directly.

## Memory / FAISS Immutability Proof
- semantic memory lines: `1715`
- FAISS ids: `1616`
- FAISS ntotal: `1616`
- semantic memory SHA256 captured: `ce81fbe1f97e257e2b124d7a929f0b2af86ce61e9ff1d8d832fdb5da1f69e64e`
- FAISS index SHA256 captured: `adbb6051f79ecbeab0223d631a6013939c00bcc13216fbae437efe83047efa21`
- FAISS ids SHA256 captured: `43736047db548caf9b26dfa61cdffe40e179c738bc8e8c295891f29cedd69102`

## Tests
- smoke test: `tests/smoke/smoke_front_chat_router_preservation_entrypoint_01.py`
- expected test count: `23 passed`

## Runtime Probe
- Brain 8090 health: `200`
- `/chat` runtime probe: timed out under an 8s diagnostic timeout
- runtime loaded new entrypoint: `false`
- server restart required for live route to load this code: `true`
- restart performed: `false`

## Remaining Gaps
- `/v1/chat/completions` is still not implemented.
- Open WebUI can reach its UI layer, but Brain provider integration requires the next adapter front.
- `UnifiedChatRouter` remains documented as legacy/orphan unless a later front deliberately reconciles it with this entrypoint.

## Next Locked Front
`FRONT-CHAT-OPENAI-COMPATIBILITY-ADAPTER-PRESERVE-ROUTER-01`
