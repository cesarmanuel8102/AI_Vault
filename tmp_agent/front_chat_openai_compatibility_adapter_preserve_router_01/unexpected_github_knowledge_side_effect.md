# Unexpected GitHub Knowledge Side Effect

- changed_file_count: `55`
- all_under_expected_path: `True`
- all_json: `True`
- staged_empty: `True`
- commit_performed_before_cleanup: `false`

## Hypothesis
Importing/testing tmp_agent/brain_v9/main.py with TestClient caused side-effect writes to curated external GitHub knowledge JSON artifacts.

## Files
- `M tmp_agent/knowledge/external/github/All_Hands_AI_OpenHands/attribution_map.json`
- `M tmp_agent/knowledge/external/github/All_Hands_AI_OpenHands/capability_hypotheses.json`
- `M tmp_agent/knowledge/external/github/All_Hands_AI_OpenHands/curation_report.json`
- `M tmp_agent/knowledge/external/github/All_Hands_AI_OpenHands/pattern_report.json`
- `M tmp_agent/knowledge/external/github/All_Hands_AI_OpenHands/risk_report.json`
- `M tmp_agent/knowledge/external/github/BerriAI_litellm/attribution_map.json`
- `M tmp_agent/knowledge/external/github/BerriAI_litellm/capability_hypotheses.json`
- `M tmp_agent/knowledge/external/github/BerriAI_litellm/curation_report.json`
- `M tmp_agent/knowledge/external/github/BerriAI_litellm/pattern_report.json`
- `M tmp_agent/knowledge/external/github/BerriAI_litellm/risk_report.json`
- `M tmp_agent/knowledge/external/github/OpenInterpreter_open_interpreter/attribution_map.json`
- `M tmp_agent/knowledge/external/github/OpenInterpreter_open_interpreter/capability_hypotheses.json`
- `M tmp_agent/knowledge/external/github/OpenInterpreter_open_interpreter/curation_report.json`
- `M tmp_agent/knowledge/external/github/OpenInterpreter_open_interpreter/pattern_report.json`
- `M tmp_agent/knowledge/external/github/OpenInterpreter_open_interpreter/risk_report.json`
- `M tmp_agent/knowledge/external/github/Significant_Gravitas_AutoGPT/attribution_map.json`
- `M tmp_agent/knowledge/external/github/Significant_Gravitas_AutoGPT/capability_hypotheses.json`
- `M tmp_agent/knowledge/external/github/Significant_Gravitas_AutoGPT/curation_report.json`
- `M tmp_agent/knowledge/external/github/Significant_Gravitas_AutoGPT/pattern_report.json`
- `M tmp_agent/knowledge/external/github/Significant_Gravitas_AutoGPT/risk_report.json`
- `M tmp_agent/knowledge/external/github/crewAIInc_crewAI/attribution_map.json`
- `M tmp_agent/knowledge/external/github/crewAIInc_crewAI/capability_hypotheses.json`
- `M tmp_agent/knowledge/external/github/crewAIInc_crewAI/curation_report.json`
- `M tmp_agent/knowledge/external/github/crewAIInc_crewAI/pattern_report.json`
- `M tmp_agent/knowledge/external/github/crewAIInc_crewAI/risk_report.json`
- `M tmp_agent/knowledge/external/github/langchain_ai_langchain/attribution_map.json`
- `M tmp_agent/knowledge/external/github/langchain_ai_langchain/capability_hypotheses.json`
- `M tmp_agent/knowledge/external/github/langchain_ai_langchain/curation_report.json`
- `M tmp_agent/knowledge/external/github/langchain_ai_langchain/pattern_report.json`
- `M tmp_agent/knowledge/external/github/langchain_ai_langchain/risk_report.json`
- `M tmp_agent/knowledge/external/github/langchain_ai_langgraph/attribution_map.json`
- `M tmp_agent/knowledge/external/github/langchain_ai_langgraph/capability_hypotheses.json`
- `M tmp_agent/knowledge/external/github/langchain_ai_langgraph/curation_report.json`
- `M tmp_agent/knowledge/external/github/langchain_ai_langgraph/pattern_report.json`
- `M tmp_agent/knowledge/external/github/langchain_ai_langgraph/risk_report.json`
- `M tmp_agent/knowledge/external/github/microsoft_TaskWeaver/attribution_map.json`
- `M tmp_agent/knowledge/external/github/microsoft_TaskWeaver/capability_hypotheses.json`
- `M tmp_agent/knowledge/external/github/microsoft_TaskWeaver/curation_report.json`
- `M tmp_agent/knowledge/external/github/microsoft_TaskWeaver/pattern_report.json`
- `M tmp_agent/knowledge/external/github/microsoft_TaskWeaver/risk_report.json`
- `M tmp_agent/knowledge/external/github/microsoft_autogen/attribution_map.json`
- `M tmp_agent/knowledge/external/github/microsoft_autogen/capability_hypotheses.json`
- `M tmp_agent/knowledge/external/github/microsoft_autogen/curation_report.json`
- `M tmp_agent/knowledge/external/github/microsoft_autogen/pattern_report.json`
- `M tmp_agent/knowledge/external/github/microsoft_autogen/risk_report.json`
- `M tmp_agent/knowledge/external/github/microsoft_semantic_kernel/attribution_map.json`
- `M tmp_agent/knowledge/external/github/microsoft_semantic_kernel/capability_hypotheses.json`
- `M tmp_agent/knowledge/external/github/microsoft_semantic_kernel/curation_report.json`
- `M tmp_agent/knowledge/external/github/microsoft_semantic_kernel/pattern_report.json`
- `M tmp_agent/knowledge/external/github/microsoft_semantic_kernel/risk_report.json`
- `M tmp_agent/knowledge/external/github/run_llama_llama_index/attribution_map.json`
- `M tmp_agent/knowledge/external/github/run_llama_llama_index/capability_hypotheses.json`
- `M tmp_agent/knowledge/external/github/run_llama_llama_index/curation_report.json`
- `M tmp_agent/knowledge/external/github/run_llama_llama_index/pattern_report.json`
- `M tmp_agent/knowledge/external/github/run_llama_llama_index/risk_report.json`

## Recommendation
Create future FRONT-BRAIN-V9-IMPORT-SIDE-EFFECTS-HARDENING-01 to remove import/TestClient side effects.
