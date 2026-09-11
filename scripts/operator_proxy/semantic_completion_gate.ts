import {createHash} from "node:crypto";
import type {EvidenceLevel,SemanticCompletionDecisionV1,SemanticCompletionInputV1,SemanticCompletionReasonCode} from "./types.js";

const levels:EvidenceLevel[]=["L0_PRESENCE","L1_STATIC","L2_UNIT","L3_CONTRACT","L4_SIMULATED_INTEGRATION","L5_LOCAL_E2E","L6_RUNTIME","L7_EXTERNAL_PAPER","L8_SOAK","L9_ADVERSARIAL_TARGET_ENVIRONMENT"];
const sha40=/^[0-9a-f]{40}$/;
const sha256=/^[0-9a-f]{64}$/;
const inputKeys=["schema_version","phase_or_item_id","source_sha","evaluated_at_utc","requirements","evidence","deferments","expected_requirement_ids","expected_requirements","deferment_authorizations"];
const requirementKeys=["requirement_id","parent_phase","original_spec_path","original_spec_sha256","requirement_text_sha256","minimum_evidence_level","required_evidence_kinds","runtime_binding_required","deferment_policy","parent_requirement_ids","required_environments","independent_verifier_required","minimum_duration_seconds","minimum_sample_size"];
const evidenceKeys=["evidence_id","requirement_id","evidence_kind","evidence_level","source_sha","certified_implementation_sha","artifact_path","artifact_sha256","environment","runtime_binding","observed_at_utc","producer_id","assertion_type","observation","verifier"];
const observationKeys=["duration_seconds","sample_size"];
const verifierKeys=["verifier_id","source_sha","independent"];
const defermentKeys=["deferment_id","requirement_id","authorization_source","reason","successor_owner","scope","expiration_or_revisit_condition","evidence_refs"];
const authorizationKeys=["authorization_id","requirement_id","authorization_source_sha","authorized_by","scope","authorized_at_utc"];

function sha(value:string){return createHash("sha256").update(value).digest("hex");}
function canonical(value:unknown):string {
  if(Array.isArray(value))return `[${value.map(canonical).join(",")}]`;
  if(value&&typeof value==="object")return `{${Object.keys(value as Record<string,unknown>).sort().map(key=>`${JSON.stringify(key)}:${canonical((value as Record<string,unknown>)[key])}`).join(",")}}`;
  return JSON.stringify(value);
}
function record(value:unknown,label:string):Record<string,unknown>{
  if(!value||typeof value!=="object"||Array.isArray(value)||Object.getPrototypeOf(value)!==Object.prototype)throw new Error(`${label} invalid`);
  return value as Record<string,unknown>;
}
function assertExactKeys(value:Record<string,unknown>,keys:string[],label:string){
  for(const key of Reflect.ownKeys(value))if(typeof key!=="string"||!keys.includes(key))throw new Error(`unknown ${label} field: ${String(key)}`);
  for(const key of keys)if(!Object.prototype.hasOwnProperty.call(value,key))throw new Error(`missing ${label} field: ${key}`);
}
function assertString(value:unknown,label:string){if(typeof value!=="string"||value.length===0)throw new Error(`${label} invalid`);}
function assertStringArray(value:unknown,label:string){if(!Array.isArray(value)||value.some(item=>typeof item!=="string"||item.length===0))throw new Error(`${label} invalid`);}
function assertDate(value:string,label:string){if(Number.isNaN(Date.parse(value)))throw new Error(`${label} timestamp invalid`);}
function canonicalRequirement(value:SemanticCompletionInputV1["requirements"][number]){
  return canonical({...value,parent_requirement_ids:[...value.parent_requirement_ids].sort(),required_environments:[...value.required_environments].sort(),required_evidence_kinds:[...value.required_evidence_kinds].sort()});
}
function validateRequirement(requirement:SemanticCompletionInputV1["requirements"][number]):void{
  const value=record(requirement,"semantic requirement");
  assertExactKeys(value,requirementKeys,"semantic requirement");
  if(!sha256.test(requirement.original_spec_sha256)||!sha256.test(requirement.requirement_text_sha256)||!levels.includes(requirement.minimum_evidence_level)||typeof requirement.runtime_binding_required!=="boolean"||!["FORBIDDEN","EXPLICIT_AUTHORIZATION_REQUIRED"].includes(requirement.deferment_policy))throw new Error("semantic requirement invalid");
  assertString(requirement.requirement_id,"semantic requirement");assertString(requirement.parent_phase,"semantic requirement");assertString(requirement.original_spec_path,"semantic requirement");assertStringArray(requirement.required_evidence_kinds,"semantic requirement");assertStringArray(requirement.parent_requirement_ids,"semantic requirement");assertStringArray(requirement.required_environments,"semantic requirement");
  if(typeof requirement.independent_verifier_required!=="boolean"||typeof requirement.minimum_duration_seconds!=="number"||typeof requirement.minimum_sample_size!=="number")throw new Error("semantic requirement invalid");
}

function validateInput(input:SemanticCompletionInputV1):Set<string>{
  const root=record(input,"semantic completion");
  assertExactKeys(root,inputKeys,"semantic completion");
  if(input.schema_version!==1||!input.phase_or_item_id||!sha40.test(input.source_sha))throw new Error("semantic completion input invalid");
  assertDate(input.evaluated_at_utc,"semantic completion");
  if(!Array.isArray(input.requirements)||input.requirements.length===0||!Array.isArray(input.evidence)||!Array.isArray(input.deferments)||!Array.isArray(input.expected_requirements)||!Array.isArray(input.deferment_authorizations))throw new Error("semantic completion collections invalid");
  const ids=new Set<string>();
  for(const requirement of input.requirements){
    validateRequirement(requirement);
    if(ids.has(requirement.requirement_id))throw new Error("duplicate semantic requirement");
    ids.add(requirement.requirement_id);
  }
  const expectedIds=new Set<string>();
  for(const expected of input.expected_requirements){validateRequirement(expected);if(expectedIds.has(expected.requirement_id))throw new Error("duplicate expected semantic requirement");expectedIds.add(expected.requirement_id);}
  const identityMismatches=new Set<string>();
  if(input.expected_requirements.length!==input.requirements.length)for(const requirement of [...input.requirements,...input.expected_requirements])identityMismatches.add(requirement.requirement_id);
  for(const requirement of input.requirements){
    const expected=input.expected_requirements.find(candidate=>candidate.requirement_id===requirement.requirement_id);
    if(!expected||canonicalRequirement(expected)!==canonicalRequirement(requirement))identityMismatches.add(requirement.requirement_id);
  }
  const evidenceIds=new Set<string>();
  for(const evidence of input.evidence){
    const value=record(evidence,"semantic evidence");
    assertExactKeys(value,evidenceKeys,"semantic evidence");
    if(!levels.includes(evidence.evidence_level)||!sha40.test(evidence.source_sha)||!sha40.test(evidence.certified_implementation_sha)||!sha256.test(evidence.artifact_sha256))throw new Error("semantic evidence invalid");
    if(evidenceIds.has(evidence.evidence_id))throw new Error("duplicate semantic evidence");
    evidenceIds.add(evidence.evidence_id);
    for(const field of ["evidence_id","requirement_id","evidence_kind","artifact_path","environment","producer_id"])assertString((evidence as unknown as Record<string,unknown>)[field],"semantic evidence");
    if(typeof evidence.runtime_binding!=="string")throw new Error("semantic evidence invalid");
    if(!["OBSERVATION","BOOLEAN"].includes(evidence.assertion_type))throw new Error("semantic evidence invalid");
    assertDate(evidence.observed_at_utc,"semantic evidence");
    const observation=record(evidence.observation,"semantic observation");assertExactKeys(observation,observationKeys,"semantic observation");
    if(typeof observation.duration_seconds!=="number"||typeof observation.sample_size!=="number")throw new Error("semantic observation invalid");
    const verifier=record(evidence.verifier,"semantic verifier");assertExactKeys(verifier,verifierKeys,"semantic verifier");
    if(typeof verifier.verifier_id!=="string"||!sha40.test(String(verifier.source_sha))||typeof verifier.independent!=="boolean")throw new Error("semantic verifier invalid");
  }
  assertStringArray(input.expected_requirement_ids,"semantic completion");
  for(const deferment of input.deferments){
    const value=record(deferment,"semantic deferment");assertExactKeys(value,defermentKeys,"semantic deferment");
    for(const field of defermentKeys.slice(0,7))assertString(value[field],"semantic deferment");
    assertStringArray(value.evidence_refs,"semantic deferment");
  }
  for(const authorization of input.deferment_authorizations){
    const value=record(authorization,"deferment authorization");assertExactKeys(value,authorizationKeys,"deferment authorization");
    for(const field of authorizationKeys.slice(0,5))assertString(value[field],"deferment authorization");
    if(!sha256.test(String(value.authorization_source_sha)))throw new Error("deferment authorization invalid");
    assertDate(String(value.authorized_at_utc),"deferment authorization");
  }
  return identityMismatches;
}

export function evaluateSemanticCompletion(input:SemanticCompletionInputV1,verifiedArtifacts:ReadonlyMap<string,string>):SemanticCompletionDecisionV1 {
  const identityMismatches=validateInput(input);
  const evidenceRefs:string[]=[];const reasonCodes=new Set<SemanticCompletionReasonCode>();let satisfied=0;
  for(const expected of input.expected_requirement_ids)if(!input.requirements.some(requirement=>requirement.requirement_id===expected))reasonCodes.add("MISSING_REQUIREMENT");
  if(identityMismatches.size>0)reasonCodes.add("REQUIREMENT_IDENTITY_MISMATCH");
  const deferred=new Set<string>();
  const evidenceById=new Map(input.evidence.map(evidence=>[evidence.evidence_id,evidence]));
  for(const deferment of input.deferments){
    const requirement=input.requirements.find(candidate=>candidate.requirement_id===deferment.requirement_id);
    const authorization=input.deferment_authorizations.find(candidate=>candidate.authorization_id===deferment.authorization_source&&candidate.requirement_id===deferment.requirement_id&&candidate.scope===deferment.scope);
    const referencedEvidenceIds=new Set(deferment.evidence_refs);
    const referencesValid=referencedEvidenceIds.size>0&&referencedEvidenceIds.size===deferment.evidence_refs.length&&[...referencedEvidenceIds].every(reference=>evidenceById.get(reference)?.requirement_id===deferment.requirement_id);
    if(!requirement||requirement.deferment_policy!=="EXPLICIT_AUTHORIZATION_REQUIRED"||!authorization||!referencesValid)reasonCodes.add("INVALID_DEFERMENT");else deferred.add(requirement.requirement_id);
  }
  const results=new Map<string,boolean>(),pending=[...input.requirements].sort((left,right)=>left.requirement_id.localeCompare(right.requirement_id));
  while(pending.length){
    let progress=false;
    for(let index=pending.length-1;index>=0;index--){
      const requirement=pending[index];
      if(requirement.parent_requirement_ids.some(parentId=>!input.requirements.some(parent=>parent.requirement_id===parentId))){reasonCodes.add("PARENT_REQUIREMENT_UNSATISFIED");results.set(requirement.requirement_id,false);pending.splice(index,1);progress=true;continue;}
      if(requirement.parent_requirement_ids.some(parentId=>!results.has(parentId)))continue;
      if(requirement.parent_requirement_ids.some(parentId=>results.get(parentId)!==true)){reasonCodes.add("PARENT_REQUIREMENT_UNSATISFIED");results.set(requirement.requirement_id,false);pending.splice(index,1);progress=true;continue;}
      if(deferred.has(requirement.requirement_id)){results.set(requirement.requirement_id,true);pending.splice(index,1);progress=true;continue;}
    const matching=input.evidence.filter(e=>e.requirement_id===requirement.requirement_id);
    if(matching.length===0){if(deferred.has(requirement.requirement_id)){results.set(requirement.requirement_id,true);}else{reasonCodes.add("MISSING_EVIDENCE");results.set(requirement.requirement_id,false);}pending.splice(index,1);progress=true;continue;}
    if(matching.length===1){
      const evidence=matching[0],bytes=verifiedArtifacts.get(evidence.artifact_path);
      let code:SemanticCompletionReasonCode|undefined;
      if(evidence.source_sha!==input.source_sha||evidence.certified_implementation_sha!==input.source_sha)code="STALE_SOURCE_SHA";
      else if(bytes===undefined||sha(bytes)!==evidence.artifact_sha256)code="ARTIFACT_HASH_MISMATCH";
      else if(evidence.assertion_type==="BOOLEAN")code="NAKED_BOOLEAN_ASSERTION";
      else if(evidence.producer_id===evidence.verifier.verifier_id)code="SELF_REFERENTIAL_EVIDENCE";
      else if(requirement.independent_verifier_required&&!evidence.verifier.independent)code="INDEPENDENT_AUDIT_MISSING";
      else if(requirement.runtime_binding_required&&evidence.runtime_binding.length===0)code="RUNTIME_BINDING_MISSING";
      else if(!requirement.required_evidence_kinds.includes(evidence.evidence_kind)||!requirement.required_environments.includes(evidence.environment))code="WRONG_EVIDENCE_KIND";
      else if(levels.indexOf(evidence.evidence_level)<levels.indexOf(requirement.minimum_evidence_level))code=requirement.minimum_evidence_level==="L8_SOAK"&&evidence.evidence_level==="L4_SIMULATED_INTEGRATION"?"SIMULATION_SUBSTITUTION":"INSUFFICIENT_EVIDENCE_LEVEL";
      else if(evidence.observation.duration_seconds<requirement.minimum_duration_seconds||evidence.observation.sample_size<requirement.minimum_sample_size)code="INSUFFICIENT_EVIDENCE_LEVEL";
      if(code){reasonCodes.add(code);results.set(requirement.requirement_id,false);}else{satisfied++;evidenceRefs.push(evidence.evidence_id);results.set(requirement.requirement_id,true);}pending.splice(index,1);progress=true;
    }
    }
    if(!progress){for(const requirement of pending){reasonCodes.add("CYCLIC_REQUIREMENT_DEPENDENCY");results.set(requirement.requirement_id,false);}pending.length=0;}
  }
  const order:SemanticCompletionReasonCode[]=["MISSING_REQUIREMENT","REQUIREMENT_IDENTITY_MISMATCH","MISSING_EVIDENCE","INSUFFICIENT_EVIDENCE_LEVEL","WRONG_EVIDENCE_KIND","STALE_SOURCE_SHA","ARTIFACT_HASH_MISMATCH","RUNTIME_BINDING_MISSING","SELF_REFERENTIAL_EVIDENCE","NAKED_BOOLEAN_ASSERTION","SIMULATION_SUBSTITUTION","INVALID_DEFERMENT","PARENT_REQUIREMENT_UNSATISFIED","CYCLIC_REQUIREMENT_DEPENDENCY","INDEPENDENT_AUDIT_MISSING"];
  const ordered=order.filter(code=>reasonCodes.has(code));
  const base={schema_version:1 as const,phase_or_item_id:input.phase_or_item_id,original_requirement_refs:Object.freeze(input.requirements.map(r=>r.requirement_id).sort()),requirements_total:input.requirements.length,requirements_satisfied:satisfied,requirements_deferred_valid:deferred.size,requirements_blocked:input.requirements.length-satisfied-deferred.size,evidence_refs:Object.freeze(evidenceRefs.sort()),decision:satisfied+deferred.size===input.requirements.length&&ordered.length===0?"PASS" as const:"BLOCK" as const,reason_codes:Object.freeze(ordered),source_sha:input.source_sha,evaluated_at_utc:input.evaluated_at_utc};
  return Object.freeze({...base,decision_artifact_sha256:sha(canonical(base))});
}
