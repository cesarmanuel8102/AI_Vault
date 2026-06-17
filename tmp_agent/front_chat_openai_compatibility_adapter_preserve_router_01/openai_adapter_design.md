# OpenAI-Compatible Adapter Design

Generated: 2026-06-12T06:47:01.437493+00:00

- endpoints: ['GET /v1/models', 'POST /v1/chat/completions']
- model_ids: ['brain-v9-local', 'brain', 'ai-vault-brain']
- non_stream_response: OpenAI-style chat.completion with brain diagnostic metadata
- stream_behavior: stream=true returns 501 unsupported_feature; no fake streaming
- error_behavior: 400 for missing/empty messages; safe error object without stack traces
- request_model: Pydantic model tolerating unknown OpenAI fields
- response_model: dict OpenAI-compatible envelope plus safe brain metadata
- future_openwebui_base_url: http://host.docker.internal:8090/v1
- direct_codex_to_brain: tmp_agent/brain_v9/evolution/direct_brain_client.py
- no_cot_protection: adapter trusts handle_user_message no_cot_leak and strips forbidden metadata fields
- router_preservation_invariant: POST /v1/chat/completions calls handle_user_message and never calls LLMManager.query, llm.query, FAISS, Ollama, or BrainSession.chat directly
