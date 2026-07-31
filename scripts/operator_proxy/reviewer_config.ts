import type {ReviewerInput} from "./reviewer_backend.js";

export const REVIEWER_MODELS={
  glm:"ollama-cloud/glm-5.2",
  qwen:"ollama-cloud/qwen3.5:397b",
  nemotron:"ollama-cloud/nemotron-3-ultra",
  kimi:"ollama-cloud/kimi-k2.7-code",
  deepseekFlash:"ollama-cloud/deepseek-v4-flash",
  deepseekPro:"ollama-cloud/deepseek-v4-pro",
} as const;

export const REVIEWER_QUALIFICATION={
  [REVIEWER_MODELS.glm]:{qualified:true,passed:5,total:5},
  [REVIEWER_MODELS.qwen]:{qualified:true,passed:5,total:5},
  [REVIEWER_MODELS.nemotron]:{qualified:true,passed:5,total:5},
  [REVIEWER_MODELS.kimi]:{qualified:true,passed:5,total:5},
  [REVIEWER_MODELS.deepseekFlash]:{qualified:false,passed:3,total:5},
  [REVIEWER_MODELS.deepseekPro]:{qualified:false,passed:4,total:5},
} as const;

const agentLoopPath=(path:string)=>path.startsWith("scripts/agent_loop/")||path.startsWith("tests/contract/test_agent_loop_");

export function reviewerRoute(input:ReviewerInput):string[]{
  const models=input.changedFiles.some(agentLoopPath)
    ? [REVIEWER_MODELS.glm,REVIEWER_MODELS.nemotron,REVIEWER_MODELS.qwen]
    : input.risk==="LOW"
      ? [REVIEWER_MODELS.qwen,REVIEWER_MODELS.glm,REVIEWER_MODELS.nemotron]
      : [REVIEWER_MODELS.glm,REVIEWER_MODELS.qwen,REVIEWER_MODELS.nemotron];
  return models.filter(model=>model!==input.builderModel).slice(0,3);
}

export function reviewerArbiter(input:ReviewerInput,used:string[]):string|undefined{
  return [REVIEWER_MODELS.nemotron,REVIEWER_MODELS.qwen,REVIEWER_MODELS.glm,REVIEWER_MODELS.kimi].find(model=>model!==input.builderModel&&!used.includes(model));
}
