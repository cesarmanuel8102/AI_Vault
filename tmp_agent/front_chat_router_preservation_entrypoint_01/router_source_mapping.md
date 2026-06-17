# Router Source Mapping

Generated: 2026-06-12T06:28:43.329299+00:00

- IntentDetector exists: tmp_agent/brain_v9/core/intent.py
- IntentDetector runtime call: tmp_agent/brain_v9/core/session.py:900 via BrainSession.chat fallback path
- BrainSession.chat call: tmp_agent/brain_v9/main.py /chat normal ORAV path
- V9.1 bypass risk: main.py owns multiple /chat fastpaths and native route calls session.chat directly; future OpenAI adapter could bypass session if implemented naively
- direct LLM risk: main.py has non-/chat introspective/direct LLM call sites; future chat adapter must not call LLMManager.query directly

## Current chat routes
- POST /chat
- POST /chat/introspectivo
