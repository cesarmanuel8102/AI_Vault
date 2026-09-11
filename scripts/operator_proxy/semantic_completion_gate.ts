import {createHash} from "node:crypto";
import type {EvidenceLevel,SemanticCompletionDecisionV1,SemanticCompletionInputV1,SemanticCompletionReasonCode} from "./types.js";

const levels:EvidenceLevel[]=["L0_PRESENCE","L1_STATIC","L2_UNIT","L3_CONTRACT","L4_SIMULATED_INTEGRATION","L5_LOCAL_E2E","L6_RUNTIME","L7_EXTERNAL_PAPER","L8_SOAK","L9_ADVERSARIAL_TARGET_ENVIRONMENT"];
const sha40=/^[0-9a-f]{40}$/;
const sha256=/^[0-9a-f]{64}$/;
const inputKeys=["schema_version","phase_or_item_id","source_sha","evaluated_at_utc","requirements","evidence","deferments"];

function sha(value:string){return createHash("sha256").update(value).digest("hex");}
function canonical(value:unknown):string {
  if(Array.isArray(value))return `[${value.map(canonical).join(",")}]`;
  if(value&&typeof value==="object")return `{${Object.keys(value as Record<string,unknown>).sort().map(key=>`${JSON.stringify(key)}:${canonical((value as Record<string,unknown>)[key])}`).join(",")}}`;
  return JSON.stringify(value);
}
function assertExactKeys(value:Record<string,unknown>,keys:string[],label:string){
  for(const key of Object.keys(value))if(!keys.includes(key))throw new Error(`unknown ${label} field: ${key}`);
}
function assertDate(value:string,label:string){if(Number.isNaN(Date.parse(value)))throw new Error(`${label} timestamp invalid`);}

export function evaluateSemanticCompletion(input:SemanticCompletionInputV1):SemanticCompletionDecisionV1 {
  assertExactKeys(input as unknown as Record<string,unknown>,inputKeys,"semantic completion");
  if(input.schema_version!==1||!input.phase_or_item_id||!sha40.test(input.source_sha))throw new Error("semantic completion input invalid");
  assertDate(input.evaluated_at_utc,"semantic completion");
  if(!Array.isArray(input.requirements)||input.requirements.length===0||!Array.isArray(input.evidence)||!Array.isArray(input.deferments))throw new Error("semantic completion collections invalid");
  const ids=new Set<string>();
  for(const requirement of input.requirements){
    if(ids.has(requirement.requirement_id))throw new Error("duplicate semantic requirement");
    ids.add(requirement.requirement_id);
    if(!requirement.requirement_id||!requirement.parent_phase||!sha256.test(requirement.original_spec_sha256)||!sha256.test(requirement.requirement_text_sha256)||!levels.includes(requirement.minimum_evidence_level))throw new Error("semantic requirement invalid");
  }
  const evidenceRefs:string[]=[];let satisfied=0;
  for(const requirement of input.requirements){
    const matching=input.evidence.filter(e=>e.requirement_id===requirement.requirement_id);
    if(matching.length===1){
      const evidence=matching[0];
      if(evidence.source_sha===input.source_sha&&evidence.certified_implementation_sha===input.source_sha&&sha256.test(evidence.artifact_sha256)&&sha(evidence.artifact_bytes)===evidence.artifact_sha256&&levels.indexOf(evidence.evidence_level)>=levels.indexOf(requirement.minimum_evidence_level)&&requirement.required_evidence_kinds.includes(evidence.evidence_kind)&&(!requirement.runtime_binding_required||Boolean(evidence.runtime_binding))){satisfied++;evidenceRefs.push(evidence.evidence_id);}
    }
  }
  const base={schema_version:1 as const,phase_or_item_id:input.phase_or_item_id,original_requirement_refs:input.requirements.map(r=>r.requirement_id),requirements_total:input.requirements.length,requirements_satisfied:satisfied,requirements_deferred_valid:0,requirements_blocked:input.requirements.length-satisfied,evidence_refs:evidenceRefs,decision:satisfied===input.requirements.length?"PASS" as const:"BLOCK" as const,reason_codes:[] as SemanticCompletionReasonCode[],source_sha:input.source_sha,evaluated_at_utc:input.evaluated_at_utc};
  return {...base,decision_artifact_sha256:sha(canonical(base))};
}