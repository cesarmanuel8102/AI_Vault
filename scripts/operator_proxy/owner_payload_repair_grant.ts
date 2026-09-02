import {createHash} from "node:crypto";
import {DEFAULT_HARD_LIMITS,type HardLimits} from "./campaign_state.js";
import {parseCorrectionPayloadV1} from "./correction_payload.js";
import {resolveOwnerPrincipal} from "./owner_principal_resolver.js";
import type {OwnerAuthoritySources,OwnerAuthorizedPayloadRepairGrant,ProxySpec} from "./types.js";

export interface OwnerGrantEvidenceV1 {schema_version:1;marker:"OWNER_AUTHORIZED_PAYLOAD_REPAIR_V1";authorization_id:string;grant_key:string;repository:string;roadmap_id:string;roadmap_item_id:string;front_id:string;issue:number;pr:number;work_branch:string;canonical_base_sha:string;failed_head_sha:string;eligible_failure_class:"CI_FAILED";max_extra_builds:1;correction_payload_sha256:string;hard_limits:HardLimits;authorization_body_sha256:string}
export interface OwnerGrantVerificationInput {spec:ProxySpec;issue:number;pr:number;failed_head_sha:string;failure_class:string;ordinary_payload_repairs:number;sources:OwnerAuthoritySources;comment:{comment_id:string;author_login:string;evidence:unknown};correction_payload:unknown}

const plain=(value:unknown):value is Record<string,unknown>=>!!value&&typeof value==="object"&&!Array.isArray(value)&&Object.getPrototypeOf(value)===Object.prototype;
const exactKeys=(value:Record<string,unknown>,keys:readonly string[])=>Object.keys(value).length===keys.length&&keys.every(key=>Object.hasOwn(value,key));
const sha=(value:string)=>createHash("sha256").update(value,"utf8").digest("hex");
const canonical=(value:unknown):unknown=>Array.isArray(value)?value.map(canonical):plain(value)?Object.fromEntries(Object.keys(value).sort().map(key=>[key,canonical(value[key])])):value;
const sha40=(value:unknown)=>typeof value==="string"&&/^[0-9a-f]{40}$/.test(value);
const sha64=(value:unknown)=>typeof value==="string"&&/^[0-9a-f]{64}$/.test(value);
const positive=(value:unknown)=>Number.isSafeInteger(value)&&(value as number)>0;
const hardLimits=(value:unknown):value is HardLimits=>plain(value)&&exactKeys(value,["HUMAN_FINAL_AUTHORITY","AUTO_MERGE","CANONICAL_LOCAL_SYNC","LIVE_TRADING","REAL_MONEY"])&&value.HUMAN_FINAL_AUTHORITY===true&&value.AUTO_MERGE===false&&value.CANONICAL_LOCAL_SYNC===false&&value.LIVE_TRADING===false&&value.REAL_MONEY===false;
const canonicalHardLimits=(value:HardLimits)=>Object.keys(DEFAULT_HARD_LIMITS).every(key=>value[key as keyof HardLimits]===DEFAULT_HARD_LIMITS[key as keyof HardLimits]);

export function parseOwnerGrantEvidenceV1(value:unknown):OwnerGrantEvidenceV1 {
  const keys=["schema_version","marker","authorization_id","grant_key","repository","roadmap_id","roadmap_item_id","front_id","issue","pr","work_branch","canonical_base_sha","failed_head_sha","eligible_failure_class","max_extra_builds","correction_payload_sha256","hard_limits","authorization_body_sha256"] as const;
  if(!plain(value)||!exactKeys(value,keys)||value.schema_version!==1||value.marker!=="OWNER_AUTHORIZED_PAYLOAD_REPAIR_V1"||typeof value.authorization_id!=="string"||!sha64(value.grant_key)||typeof value.repository!=="string"||typeof value.roadmap_id!=="string"||typeof value.roadmap_item_id!=="string"||typeof value.front_id!=="string"||typeof value.work_branch!=="string"||!positive(value.issue)||!positive(value.pr)||!sha40(value.canonical_base_sha)||!sha40(value.failed_head_sha)||value.eligible_failure_class!=="CI_FAILED"||value.max_extra_builds!==1||!sha64(value.correction_payload_sha256)||!sha64(value.authorization_body_sha256)||!hardLimits(value.hard_limits))throw new Error("owner grant evidence invalid");
  const {authorization_body_sha256,...body}=value;
  if(authorization_body_sha256!==sha(`${JSON.stringify(canonical(body))}\n`))throw new Error("owner grant authorization body hash invalid");
  return value as unknown as OwnerGrantEvidenceV1;
}

export function verifyOwnerAuthorizedPayloadRepairGrant(input:OwnerGrantVerificationInput):OwnerAuthorizedPayloadRepairGrant {
  const evidence=parseOwnerGrantEvidenceV1(input.comment?.evidence);
  const owner_principal=resolveOwnerPrincipal(input.spec,input.sources);
  const payload=parseCorrectionPayloadV1(input.correction_payload);
  if(input.failure_class!=="CI_FAILED"||input.ordinary_payload_repairs!==2||!sha40(input.failed_head_sha)||typeof input.comment?.comment_id!=="string"||!/^\d+$/.test(input.comment.comment_id)||input.comment.author_login!==owner_principal)throw new Error("owner grant invalid");
  if(!input.spec.front_id||!input.spec.work_branch||evidence.authorization_id!==input.spec.authorization_id||evidence.repository!==input.spec.repository||evidence.roadmap_id!==input.spec.roadmap_id||evidence.roadmap_item_id!==input.spec.roadmap_item_id||evidence.front_id!==input.spec.front_id||evidence.issue!==input.issue||evidence.pr!==input.pr||evidence.work_branch!==input.spec.work_branch||evidence.canonical_base_sha!==input.spec.expected_base_sha||evidence.failed_head_sha!==input.failed_head_sha||evidence.eligible_failure_class!==input.failure_class||evidence.max_extra_builds!==1||evidence.correction_payload_sha256!==payload.sha256||!canonicalHardLimits(evidence.hard_limits))throw new Error("owner grant invalid");
  return {schema_version:1,authorization_id:evidence.authorization_id,grant_key:evidence.grant_key,owner_principal,repository:evidence.repository,roadmap_id:evidence.roadmap_id,roadmap_item_id:evidence.roadmap_item_id,front_id:evidence.front_id,issue:evidence.issue,pr:evidence.pr,work_branch:evidence.work_branch,canonical_base_sha:evidence.canonical_base_sha,failed_head_sha:evidence.failed_head_sha,eligible_failure_class:"CI_FAILED",max_extra_builds:1,correction_payload:payload.payload,correction_payload_sha256:payload.sha256,owner_comment_id:input.comment.comment_id,authorization_body_sha256:evidence.authorization_body_sha256};
}
