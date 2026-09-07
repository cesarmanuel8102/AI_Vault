import {createHash} from "node:crypto";
import type {ControllerRebaselinePlan,ControllerRebaselinePlanInputV1,ControllerSupersessionReceiptV1,FunctionalEvidenceAssertionV1,FunctionalEvidenceInputV1,HistoricalAttemptRefV1,LifecycleRecord,RebaselineHardLimitsInputV1,RebaselineHardLimitsV1} from "./types.js";

const sha1=/^[0-9a-f]{40}$/;
const sha256=/^[0-9a-f]{64}$/;

function canonical(value:unknown):unknown {return Array.isArray(value)?value.map(canonical):value&&typeof value==="object"?Object.fromEntries(Object.entries(value as Record<string,unknown>).sort(([left],[right])=>left.localeCompare(right)).map(([key,child])=>[key,canonical(child)])):value;}
function canonicalJson(value: unknown): string {return JSON.stringify(canonical(value));}

function canonicalSha256(value: unknown): string {
  return createHash("sha256").update(Buffer.from(canonicalJson(value),"utf8")).digest("hex");
}

function normalizeHardLimits(value: RebaselineHardLimitsInputV1): RebaselineHardLimitsV1 {
  if (value.human_final_authority!==true || value.auto_merge!==false || value.canonical_local_sync!==false || value.live_trading!==false || value.real_money!==false) throw new Error("functional evidence hard limits invalid");
  return {human_final_authority:true,auto_merge:false,canonical_local_sync:false,live_trading:false,real_money:false};
}

export function projectHistoricalAttempt(record: LifecycleRecord): HistoricalAttemptRefV1 {
  const repair=record.owner_payload_repair,issue=record.issue,pr=record.pr,failedHead=record.head_sha;
  if (
    record.state==="TERMINAL_COMPLETED" || record.repair_cycles!==2 || !repair ||
    typeof issue!=="number" || !Number.isInteger(issue) || issue<=0 || typeof pr!=="number" || !Number.isInteger(pr) || pr<=0 ||
    !sha1.test(record.base_sha) || !sha1.test(failedHead??"") ||
    !sha256.test(repair.grant_key) || !sha256.test(repair.consumed_event_sha256) || !sha256.test(repair.build_attempt_id)
  ) throw new Error("historical Owner attempt invalid or not exhausted");
  if (issue===undefined || pr===undefined || failedHead===undefined) throw new Error("historical Owner attempt invalid or not exhausted");
  const core={
    schema_version:1 as const,
    front_id:record.front_id,
    roadmap_item_id:record.roadmap_item_id,
    lifecycle_state:record.state,
    issue,
    pr,
    base_sha:record.base_sha,
    failed_head_sha:failedHead,
    repair_cycles:2 as const,
    grant_key:repair.grant_key,
    consumed_event_sha256:repair.consumed_event_sha256,
    build_attempt_id:repair.build_attempt_id
  };
  return {...core,historical_sha256:canonicalSha256(core)};
}

export function verifyFunctionalEvidenceForRebaseline(input: FunctionalEvidenceInputV1): FunctionalEvidenceAssertionV1 {
  if (!/^[A-Z0-9][A-Z0-9._-]{2,127}$/.test(input.item_id) || !/^[A-Z0-9][A-Z0-9._-]{5,127}$/.test(input.task_id) || !sha1.test(input.canonical_ref) || !/^docs\/[A-Za-z0-9._/-]+$/.test(input.evidence_path) || input.evidence_path.includes("..")) throw new Error("functional evidence identity invalid");
  const hardLimits=normalizeHardLimits(input.hard_limits);
  if (!Array.isArray(input.required_markers) || input.required_markers.length===0 || new Set(input.required_markers).size!==input.required_markers.length || input.required_markers.some(marker=>typeof marker!=="string" || !marker.trim() || marker.includes("\n") || marker.includes("\r"))) throw new Error("functional evidence markers invalid");
  const evidence=Buffer.from(input.evidence_bytes),text=evidence.toString("utf8");
  if (!evidence.length) throw new Error("functional evidence empty");
  for (const marker of input.required_markers) if (!text.includes(marker)) throw new Error("functional evidence marker missing");
  const core={schema_version:1 as const,item_id:input.item_id,task_id:input.task_id,evidence_path:input.evidence_path,canonical_ref:input.canonical_ref,evidence_sha256:createHash("sha256").update(evidence).digest("hex"),required_markers:[...input.required_markers],hard_limits:hardLimits,status:"PASSED" as const};
  return {...core,assertion_sha256:canonicalSha256(core)};
}

function sameLimits(left:RebaselineHardLimitsV1,right:RebaselineHardLimitsV1):boolean {return left.human_final_authority===true&&right.human_final_authority===true&&left.auto_merge===false&&right.auto_merge===false&&left.canonical_local_sync===false&&right.canonical_local_sync===false&&left.live_trading===false&&right.live_trading===false&&left.real_money===false&&right.real_money===false;}
function supersessionKey(input:ControllerRebaselinePlanInputV1):string {return canonicalSha256({repository:input.canonical.repository,roadmap_item_id:input.canonical.roadmap_item_id,historical_attempt_sha256:input.historical.historical_sha256,functional_evidence_assertion_sha256:input.evidence.assertion_sha256});}
function receiptMatches(input:ControllerRebaselinePlanInputV1,receipt:ControllerSupersessionReceiptV1,key:string):boolean {
  const {canonical:binding,historical,evidence}=input;
  return receipt.schema_version===1&&receipt.controller==="CODEX_GOVERNED_CONTROLLER"&&receipt.supersession_key===key&&sha256.test(receipt.event_sha256)&&receipt.repository===binding.repository&&receipt.roadmap_item_id===binding.roadmap_item_id&&receipt.canonical_base_sha===binding.canonical_base_sha&&receipt.manifest_sha256===binding.manifest_sha256&&receipt.roadmap_sha256===binding.roadmap_sha256&&receipt.historical_attempt_sha256===historical.historical_sha256&&receipt.front_id===historical.front_id&&receipt.failed_head_sha===historical.failed_head_sha&&receipt.grant_key===historical.grant_key&&receipt.consumed_event_sha256===historical.consumed_event_sha256&&receipt.build_attempt_id===historical.build_attempt_id&&receipt.functional_evidence_ref===evidence.canonical_ref&&receipt.functional_evidence_path===evidence.evidence_path&&receipt.functional_evidence_sha256===evidence.evidence_sha256&&receipt.functional_evidence_assertion_sha256===evidence.assertion_sha256&&receipt.persistent_agent_loop_enabled===false&&sameLimits(binding.hard_limits,receipt.hard_limits);
}

export function planControllerRebaseline(input:ControllerRebaselinePlanInputV1):ControllerRebaselinePlan {
  const {canonical:binding,historical,evidence}=input;
  if(!binding||!historical||!evidence||!Array.isArray(input.receipts)||!binding.repository||!binding.roadmap_item_id||!sha1.test(binding.canonical_base_sha)||!sha256.test(binding.manifest_sha256)||!sha256.test(binding.roadmap_sha256)||!sameLimits(binding.hard_limits,binding.hard_limits)||historical.roadmap_item_id!==binding.roadmap_item_id||historical.base_sha!==binding.canonical_base_sha||evidence.item_id!==binding.roadmap_item_id||evidence.canonical_ref!==binding.canonical_base_sha||!sameLimits(binding.hard_limits,evidence.hard_limits))return {status:"BLOCKED",reason:"canonical binding invalid"};
  const key=supersessionKey(input),matching=input.receipts.filter(receipt=>receipt.supersession_key===key);
  if(matching.length>1)return {status:"BLOCKED",reason:"supersession receipt ambiguous"};
  if(matching.length===1&&!receiptMatches(input,matching[0]!,key))return {status:"BLOCKED",reason:"supersession receipt mismatch"};
  if(matching.length===0)return binding.item_status==="AUTHORIZED_ACTIVE"?{status:"REBASELINE_REQUIRED",supersession_key:key}:{status:"BLOCKED",reason:"closed item missing supersession receipt"};
  return binding.item_status==="CLOSED_RUNTIME_VERIFIED"?{status:"ALREADY_SUPERSEDED",supersession_key:key}:{status:"CLOSEOUT_ALLOWED",supersession_key:key};
}
