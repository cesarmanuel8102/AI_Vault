# FRONT-BRAIN-V9-ADAPTER-RUNTIME-LOAD-FIX-01

## Status
`BRAIN_V9_ADAPTER_RUNTIME_LOADED_ON_ALTERNATE_PORT_8091`

## Runtime Selection
- selected_runtime_port: `8091`
- safe_restart_performed: `false`
- alternate_port_used: `true`
- reason: port `8090` owner was `python.exe` PID `193980`, but Windows did not expose command line or executable path with enough confidence to classify it as safe to stop.
- 8090 was not killed or modified.

## OpenAI-Compatible Runtime Probe
- base URL: `http://127.0.0.1:8091/v1`
- `/health`: passed
- `GET /v1/models`: passed
- `POST /v1/chat/completions`: passed
- `stream=true`: safe unsupported response passed
- model available: `brain-v9-local`

## Router Preservation
- live `/v1/chat/completions` is served by `tmp_agent/brain_v9/api/openai_compat.py`.
- adapter calls `tmp_agent.brain_v9.core.router_entrypoint.handle_user_message(...)`.
- adapter does not call `LLMManager.query()`, `.llm.query`, FAISS writes, semantic memory writes, broker, or trading code.

## Codex-to-Brain Direct Dialogue
- probe: `tmp_agent/brain_v9/evolution/codex_brain_dialogue_probe.py`
- output: `tmp_agent/evolution_runs/codex_brain_direct_dialogue_001`
- prompt_count: `5`
- successful_responses: `5`
- intent metadata present: `true`
- route metadata present: `true`
- governance/no-CoT metadata present: `true`
- canonical path present: `true`
- preliminary_score: `1.0`

## Container-to-Brain Probe
- Open WebUI container: `open-webui`
- container-to-Brain passed: `true`
- provider base URL for testing: `http://host.docker.internal:8091/v1`

## Canonical Safety
- semantic_memory_lines: `1715`
- faiss_ids: `1616`
- faiss_ntotal: `1616`
- memory_mutated: `false`
- faiss_mutated: `false`
- trading_touched: `false`
- legacy_touched: `false`
- raw_cot_exposed: `false`

## Evidence
- `tmp_agent/front_brain_v9_adapter_runtime_load_fix_01/preflight.json`
- `tmp_agent/front_brain_v9_adapter_runtime_load_fix_01/canonical_safety_baseline.json`
- `tmp_agent/front_brain_v9_adapter_runtime_load_fix_01/source_contract_verify.json`
- `tmp_agent/front_brain_v9_adapter_runtime_load_fix_01/pre_runtime_probe.json`
- `tmp_agent/front_brain_v9_adapter_runtime_load_fix_01/port_owner_classification.json`
- `tmp_agent/front_brain_v9_adapter_runtime_load_fix_01/runtime_openai_probe.json`
- `tmp_agent/front_brain_v9_adapter_runtime_load_fix_01/codex_brain_direct_dialogue_summary.json`
- `tmp_agent/front_brain_v9_adapter_runtime_load_fix_01/container_to_brain_probe.json`
- `tmp_agent/front_brain_v9_adapter_runtime_load_fix_01/post_action_immutability_verify.json`

## Remaining Risks
- Production 8090 still runs the old process and does not expose `/v1`.
- 8091 is a safe alternate runtime, not a switch-over.
- Open WebUI should use `http://host.docker.internal:8091/v1` for testing until a controlled 8091-to-8090 switch-over is approved.

## Next Locked Front
`FRONT-BRAIN-V9-RUNTIME-SWITCHOVER-8091-TO-8090-01`
