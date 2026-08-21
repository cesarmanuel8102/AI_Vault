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
  [REVIEWER_MODELS.glm]:{qualified:false,passed:0,total:5},
  [REVIEWER_MODELS.qwen]:{qualified:false,passed:3,total:5},
  [REVIEWER_MODELS.nemotron]:{qualified:true,passed:5,total:5},
  [REVIEWER_MODELS.kimi]:{qualified:false,passed:0,total:5},
  [REVIEWER_MODELS.deepseekFlash]:{qualified:true,passed:5,total:5},
  [REVIEWER_MODELS.deepseekPro]:{qualified:true,passed:5,total:5},
} as const;

const safeModel=/^ollama-cloud\/[a-z0-9][a-z0-9.:-]{2,127}$/;

export function requiredBuilderModel(env=process.env):string{
  const model=env.OPERATOR_PROXY_BUILDER_MODEL;
  if(!model||!safeModel.test(model))throw new Error("builder model identity missing or invalid");
  return model;
}

export function verifiedBuilderModel(executor:"agent_loop"|"codex_control_plane",report?:unknown,env=process.env):string{
  if(executor==="codex_control_plane")return "codex-local";
  const configured=requiredBuilderModel(env),candidate=report as {model?:unknown}|undefined;
  if(!candidate||candidate.model!==configured)throw new Error("Agent Loop report model identity missing or mismatched");
  return configured;
}

export function verifiedAgentLoopCommitModel(message:string,frontId:string,reportModel?:unknown,env=process.env):string{
  const receipt=inspectAgentLoopCommitModel(message,frontId,reportModel,env);
  if(receipt.status==="MISSING")throw new Error("Agent Loop executor model receipt missing");
  return receipt.model;
}

export function inspectAgentLoopCommitModel(message:string,frontId:string,reportModel?:unknown,env=process.env):{status:"VERIFIED";model:string}|{status:"MISSING";model:string}{
  if(!/^[A-Z0-9][A-Z0-9._-]{5,127}$/.test(frontId))throw new Error("Agent Loop front identity invalid");
  const lines=message.replace(/\r\n/g,"\n").split("\n"),subject=`test(agent-loop): complete ${frontId}`,prefix="AGENT_LOOP_EXECUTOR_MODEL=";
  if(lines[0]!==subject)throw new Error("Agent Loop commit subject identity mismatch");
  const trailers=lines.slice(1).filter(line=>line.startsWith(prefix));
  if(trailers.length>1)throw new Error("Agent Loop executor model receipt ambiguous");
  const configured=requiredBuilderModel(env);
  if(trailers.length===0){if(reportModel!==undefined&&reportModel!==configured)throw new Error("Agent Loop executor model receipt mismatch");return {status:"MISSING",model:configured};}
  const model=trailers[0].slice(prefix.length);
  if(model!==configured||reportModel!==undefined&&reportModel!==model)throw new Error("Agent Loop executor model receipt mismatch");
  return {status:"VERIFIED",model};
}

export function reviewerRoute(input:ReviewerInput):string[]{
  // The configured reviewer is fixed; a builder never reviews itself.
  return input.builderModel===REVIEWER_MODELS.deepseekPro?[]:[REVIEWER_MODELS.deepseekPro];
}
