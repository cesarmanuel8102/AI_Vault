# Evaluation Scorecard

- prompts_attempted: `24`
- successful_responses: `24`
- timeout_fallback_count: `20`
- metadata_full_rate: `1.0`
- average_score: `0.583`

## Category Scores
- identity_purpose: `0.553`
- architecture_runtime: `0.621`
- memory_faiss: `0.628`
- cei_fdot: `0.533`
- programming_brain_development: `0.527`
- financial_research: `0.533`
- autonomy_governance: `0.715`
- anti_cot_safety: `0.553`

## Top Gaps
- Content quality is dominated by timeout fallback responses: 20 of 24 prompts.
- Route/metadata layer is strong, but answer generation latency is not reliable enough for broad evaluation.
- Brain self-assessment also timed out on 4 of 5 short prompts.
- Runtime still operates on alternate port 8091, not production 8090.
- Need a recurring evaluation harness with timeout classification and shorter prompt profiles.
- Need CEI/FDOT benchmark pack with source-backed expected answers.
- Need financial research safety pack before trading-adjacent integration.
- Need import/TestClient side-effect hardening from prior front.
- Need Open WebUI provider config/switchover so user can test through UI.
- Need observer report format after autonomous cycles.

## Top Strengths
- 24/24 HTTP calls returned governed chat.completion objects.
- Intent, route, governance, no-CoT, and canonical path metadata were present on all responses.
- No raw CoT markers or secrets were detected.
- Brain endpoint is reachable from Codex via OpenAI-compatible adapter on 8091.
- The loop produced actionable evidence for the next engineering fronts.

## Recommended Improvements
- FRONT-BRAIN-V9-RUNTIME-SWITCHOVER-8091-TO-8090-01
- FRONT-CODEX-TO-BRAIN-EVALUATION-HARNESS-V2-01
- FRONT-BRAIN-V9-LLM-TIMEOUT-QUALITY-STABILIZATION-01
- FRONT-CHAT-UI-BRAIN-PROVIDER-CONFIG-8091-01
- FRONT-BRAIN-V9-IMPORT-SIDE-EFFECTS-HARDENING-01
