import {createHash} from "node:crypto";
import {DEFAULT_HARD_LIMITS,type HardLimits} from "./campaign_state.js";
import {resolveOwnerPrincipal} from "./owner_principal_resolver.js";
import type {NormalizedDecision,OwnerAuthoritySources,OwnerAuthorizedCriticalMerge,Review} from "./types.js";

export interface OwnerCriticalMergeEvidenceV1 {schema_version:1;marker:"OWNER_AUTHORIZED_CRITICAL_MERGE_V1";authorization_id:string;repository:string;issue:number;front_id:string;pr:number;base_branch:string;base_sha:string;head_branch:string;head_sha:string;policy_decision_id:string;policy_decision_key:string;policy_sha256:string;policy_outcome:"ESCALATE_TO_OWNER";ci_evidence_id:string;ci_evidence_sha256:string;review_receipt_id:string;review_receipt_sha256:string;reviewer_model:string;review_verdict:"PASS";review_findings_count:0;risk:"CRITICAL";action:"OWNER_AUTHORIZED_CRITICAL_MERGE";max_uses:1;hard_limits:HardLimits;authorization_body_sha256:string}
export interface CriticalMergeCiEvidence {evidence_id:string;evidence_sha256:string;head_sha:string}
export interface CriticalMergeReviewReceipt {receipt_id:string;receipt_sha256:string;head_sha:string;model:string;verdict:Review;findings_count:number}
export interface OwnerCriticalMergeVerificationInput {authorization:{comment_id:string;author_login:string;evidence:unknown};sources:OwnerAuthoritySources;decision:NormalizedDecision;ci:CriticalMergeCiEvidence;review:CriticalMergeReviewReceipt;base_branch:string;head_branch:string}

const plain=(value:unknown):value is Record<string,unknown>=>!!value&&typeof value==="object"&&!Array.isArray(value)&&Object.getPrototypeOf(value)===Object.prototype;
const exactKeys=(value:Record<string,unknown>,keys:readonly string[])=>Object.keys(value).length===keys.length&&keys.every(key=>Object.hasOwn(value,key));
const canonical=(value:unknown):unknown=>Array.isArray(value)?value.map(canonical):plain(value)?Object.fromEntries(Object.keys(value).sort().map(key=>[key,canonical(value[key])])):value;
const sha=(value:string)=>createHash("sha256").update(value,"utf8").digest("hex");
const canonicalSha=(value:unknown)=>sha(`${JSON.stringify(canonical(value))}\n`);
const sha40=(value:unknown)=>typeof value==="string"&&/^[0-9a-f]{40}$/.test(value);
const sha64=(value:unknown)=>typeof value==="string"&&/^[0-9a-f]{64}$/.test(value);
const positive=(value:unknown)=>Number.isSafeInteger(value)&&(value as number)>0;
const text=(value:unknown)=>typeof value==="string"&&value.trim()===value&&value.length>0;
const hardLimits=(value:unknown):value is HardLimits=>plain(value)&&exactKeys(value,["HUMAN_FINAL_AUTHORITY","AUTO_MERGE","CANONICAL_LOCAL_SYNC","LIVE_TRADING","REAL_MONEY"])&&value.HUMAN_FINAL_AUTHORITY===true&&value.AUTO_MERGE===false&&value.CANONICAL_LOCAL_SYNC===false&&value.LIVE_TRADING===false&&value.REAL_MONEY===false;
const canonicalHardLimits=(value:HardLimits)=>Object.keys(DEFAULT_HARD_LIMITS).every(key=>value[key as keyof HardLimits]===DEFAULT_HARD_LIMITS[key as keyof HardLimits]);

export function parseOwnerCriticalMergeEvidenceV1(value:unknown):OwnerCriticalMergeEvidenceV1 {
  const keys=["schema_version","marker","authorization_id","repository","issue","front_id","pr","base_branch","base_sha","head_branch","head_sha","policy_decision_id","policy_decision_key","policy_sha256","policy_outcome","ci_evidence_id","ci_evidence_sha256","review_receipt_id","review_receipt_sha256","reviewer_model","review_verdict","review_findings_count","risk","action","max_uses","hard_limits","authorization_body_sha256"] as const;
  if(!plain(value)||!exactKeys(value,keys)||value.schema_version!==1||value.marker!=="OWNER_AUTHORIZED_CRITICAL_MERGE_V1"||!text(value.authorization_id)||!text(value.repository)||!positive(value.issue)||!text(value.front_id)||!positive(value.pr)||!text(value.base_branch)||!sha40(value.base_sha)||!text(value.head_branch)||!sha40(value.head_sha)||!text(value.policy_decision_id)||!sha64(value.policy_decision_key)||!sha64(value.policy_sha256)||value.policy_outcome!=="ESCALATE_TO_OWNER"||!text(value.ci_evidence_id)||!sha64(value.ci_evidence_sha256)||!text(value.review_receipt_id)||!sha64(value.review_receipt_sha256)||!text(value.reviewer_model)||value.review_verdict!=="PASS"||value.review_findings_count!==0||value.risk!=="CRITICAL"||value.action!=="OWNER_AUTHORIZED_CRITICAL_MERGE"||value.max_uses!==1||!hardLimits(value.hard_limits)||!sha64(value.authorization_body_sha256))throw new Error("owner critical merge evidence invalid");
  const {authorization_body_sha256,...body}=value;
  if(authorization_body_sha256!==canonicalSha(body))throw new Error("owner critical merge authorization body hash invalid");
  return value as unknown as OwnerCriticalMergeEvidenceV1;
}

export function verifyOwnerAuthorizedCriticalMerge(input:OwnerCriticalMergeVerificationInput):OwnerAuthorizedCriticalMerge {
  const evidence=parseOwnerCriticalMergeEvidenceV1(input.authorization?.evidence);
  const owner_principal=resolveOwnerPrincipal({authorization_id:evidence.authorization_id,repository:evidence.repository},input.sources);
  const decision=input.decision,ci=input.ci,review=input.review;
  if(!input.authorization||!/^\d+$/.test(input.authorization.comment_id)||input.authorization.author_login!==owner_principal||!sha40(ci?.head_sha)||!text(ci?.evidence_id)||!sha64(ci?.evidence_sha256)||!sha40(review?.head_sha)||!text(review?.receipt_id)||!sha64(review?.receipt_sha256)||!text(review?.model)||review.verdict!=="PASS"||review.findings_count!==0)throw new Error("owner critical merge invalid");
  const reviewDecision="review_findings_count" in decision&&"review_consistent" in decision?decision:undefined;
  if(!reviewDecision||decision.risk!=="CRITICAL"||decision.policy_decision!=="ESCALATE_TO_OWNER"||decision.allowed_action!=="NONE"||decision.deterministic_gate!=="PASS"||decision.codex_review!=="PASS"||reviewDecision.review_findings_count!==0||!reviewDecision.review_consistent||!canonicalHardLimits(evidence.hard_limits))throw new Error("owner critical merge invalid");
  if(evidence.authorization_id!==decision.authorization_id||evidence.repository!==decision.repository||evidence.issue!==decision.issue||evidence.pr!==decision.pr||evidence.base_sha!==decision.base_sha||evidence.head_sha!==decision.head_sha||evidence.base_branch!==input.base_branch||evidence.head_branch!==input.head_branch||evidence.policy_decision_id!==decision.decision_id||evidence.policy_decision_key!==decision.decision_key||evidence.policy_sha256!==decision.policy_sha256||evidence.ci_evidence_id!==ci.evidence_id||evidence.ci_evidence_sha256!==ci.evidence_sha256||evidence.head_sha!==ci.head_sha||evidence.review_receipt_id!==review.receipt_id||evidence.review_receipt_sha256!==review.receipt_sha256||evidence.reviewer_model!==review.model||evidence.review_verdict!==review.verdict||evidence.review_findings_count!==review.findings_count||evidence.head_sha!==review.head_sha)throw new Error("owner critical merge invalid");
  const critical_merge_key=canonicalSha({authorization_body_sha256:evidence.authorization_body_sha256,owner_comment_id:input.authorization.comment_id,owner_principal});
  return {schema_version:1,authorization_id:evidence.authorization_id,critical_merge_key,owner_principal,owner_comment_id:input.authorization.comment_id,repository:evidence.repository,issue:evidence.issue,front_id:evidence.front_id,pr:evidence.pr,base_branch:evidence.base_branch,base_sha:evidence.base_sha,head_branch:evidence.head_branch,head_sha:evidence.head_sha,policy_decision_id:evidence.policy_decision_id,policy_decision_key:evidence.policy_decision_key,policy_sha256:evidence.policy_sha256,policy_outcome:"ESCALATE_TO_OWNER",ci_evidence_id:evidence.ci_evidence_id,ci_evidence_sha256:evidence.ci_evidence_sha256,review_receipt_id:evidence.review_receipt_id,review_receipt_sha256:evidence.review_receipt_sha256,reviewer_model:evidence.reviewer_model,review_verdict:"PASS",review_findings_count:0,risk:"CRITICAL",action:"OWNER_AUTHORIZED_CRITICAL_MERGE",max_uses:1,authorization_body_sha256:evidence.authorization_body_sha256};
}
