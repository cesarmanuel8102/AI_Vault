import test from "node:test";
import assert from "node:assert/strict";
import {createHash} from "node:crypto";
import {discoverOwnerAuthorizedCriticalMerge,parseOwnerCriticalMergeEvidenceV1,verifyOwnerAuthorizedCriticalMerge} from "../../../scripts/operator_proxy/owner_critical_merge_authorization.js";
import type {Decision,OwnerAuthoritySources} from "../../../scripts/operator_proxy/types.js";

const repository="cesarmanuel8102/AI_Vault",owner="cesarmanuel8102",base="a".repeat(40),head="b".repeat(40);
const limits={HUMAN_FINAL_AUTHORITY:true,AUTO_MERGE:false,CANONICAL_LOCAL_SYNC:false,LIVE_TRADING:false,REAL_MONEY:false} as const;
const canonicalize=(value:unknown):unknown=>Array.isArray(value)?value.map(canonicalize):value&&typeof value==="object"?Object.fromEntries(Object.entries(value as Record<string,unknown>).sort(([a],[b])=>a.localeCompare(b)).map(([key,child])=>[key,canonicalize(child)])):value;
const canonical=(value:Record<string,unknown>)=>`${JSON.stringify(canonicalize(value))}\n`;
const sha=(value:string)=>createHash("sha256").update(value,"utf8").digest("hex");
const sources:OwnerAuthoritySources={campaign_candidates:[],repository_candidates:[{repository,owner_principal:owner}]};
const decision:Decision={schema_version:2,decision_key:"c".repeat(64),decision_id:"critical-policy-decision",authorization_id:"CESAR-BRAIN-101-OPERATOR-PROXY-20260722-01",repository,issue:277,pr:277,base_sha:base,head_sha:head,roadmap_id:"BRAIN-101",roadmap_item_id:"R3.4",risk:"CRITICAL",deterministic_gate:"PASS",codex_review:"PASS",review_findings_count:0,review_consistent:true,policy_decision:"ESCALATE_TO_OWNER",allowed_action:"NONE",policy_sha256:"d".repeat(64),evidence_sha256:"e".repeat(64),created_utc:"2026-09-04T00:00:00.000Z"};
const ci={evidence_id:"ci-run-277",evidence_sha256:"f".repeat(64),head_sha:head};
const review={receipt_id:"review-277",receipt_sha256:"1".repeat(64),head_sha:head,model:"ollama-cloud/deepseek-v4-pro",verdict:"PASS" as const,findings_count:0};
const evidence=(overrides:Record<string,unknown>={})=>{const body={schema_version:1,marker:"OWNER_AUTHORIZED_CRITICAL_MERGE_V1",authorization_id:decision.authorization_id,repository,issue:277,front_id:"BRAIN-101-R3-OWNER-CRITICAL-MERGE-01",pr:277,base_branch:"codex/own-capital-sustainable-return",base_sha:base,head_branch:"control-plane/owner-authorized-payload-repair-resume-v1",head_sha:head,policy_decision_id:decision.decision_id,policy_decision_key:decision.decision_key,policy_sha256:decision.policy_sha256,policy_outcome:"ESCALATE_TO_OWNER",ci_evidence_id:ci.evidence_id,ci_evidence_sha256:ci.evidence_sha256,review_receipt_id:review.receipt_id,review_receipt_sha256:review.receipt_sha256,reviewer_model:review.model,review_verdict:"PASS",review_findings_count:0,risk:"CRITICAL",action:"OWNER_AUTHORIZED_CRITICAL_MERGE",max_uses:1,hard_limits:limits,...overrides};return {...body,authorization_body_sha256:sha(canonical(body))};};
const input=(overrides:Record<string,unknown>={})=>({authorization:{comment_id:"5000002771",author_login:owner,evidence:evidence()},sources,decision,ci,review,base_branch:"codex/own-capital-sustainable-return",head_branch:"control-plane/owner-authorized-payload-repair-resume-v1",...overrides});

test("Owner critical merge verifier accepts one canonically bound CRITICAL escalation",()=>{
  const authorization=verifyOwnerAuthorizedCriticalMerge(input());
  assert.equal(authorization.authorization_id,decision.authorization_id);
  assert.equal(authorization.policy_outcome,"ESCALATE_TO_OWNER");
  assert.equal(authorization.action,"OWNER_AUTHORIZED_CRITICAL_MERGE");
  assert.match(authorization.critical_merge_key,/^[0-9a-f]{64}$/);
  assert.equal(authorization.authorization_body_sha256,evidence().authorization_body_sha256);
});

test("Owner critical merge verifier rejects every stale or non-owner-bound authorization anchor",()=>{
  const invalid=[
    input({authorization:{comment_id:"5000002771",author_login:owner,evidence:evidence({repository:"other/repository"})}}),
    input({authorization:{comment_id:"5000002771",author_login:owner,evidence:evidence({pr:278})}}),
    input({authorization:{comment_id:"5000002771",author_login:owner,evidence:evidence({base_sha:"2".repeat(40)})}}),
    input({authorization:{comment_id:"5000002771",author_login:owner,evidence:evidence({head_sha:"3".repeat(40)})}}),
    input({ci:{...ci,evidence_sha256:"4".repeat(64)}}),
    input({review:{...review,receipt_sha256:"5".repeat(64)}}),
    input({review:{...review,findings_count:1}}),
    input({review:{...review,verdict:"CHANGES_REQUESTED"}}),
    input({decision:{...decision,policy_decision:"APPROVE",allowed_action:"MERGE"}}),
    input({authorization:{comment_id:"5000002771",author_login:"attacker",evidence:evidence()}}),
  ];
  for(const value of invalid)assert.throws(()=>verifyOwnerAuthorizedCriticalMerge(value as any),/owner critical merge|owner authority/i);
});

test("Owner critical merge evidence rejects unknown fields and a noncanonical body hash",()=>{
  const valid=evidence();
  assert.deepEqual(parseOwnerCriticalMergeEvidenceV1(valid),valid);
  assert.throws(()=>parseOwnerCriticalMergeEvidenceV1({...valid,unknown:true}),/owner critical merge evidence/i);
  assert.throws(()=>parseOwnerCriticalMergeEvidenceV1({...valid,authorization_body_sha256:"0".repeat(64)}),/authorization body hash/i);
});

test("Owner critical merge discovery accepts exactly one framed canonical Owner envelope",()=>{
  const valid=evidence(),comments=[{id:5000002771,author:{login:owner},body:`BEGIN_OWNER_AUTHORIZED_CRITICAL_MERGE_V1\n${JSON.stringify(valid)}\nEND_OWNER_AUTHORIZED_CRITICAL_MERGE_V1`}];
  const authorization=discoverOwnerAuthorizedCriticalMerge({comments,sources,decision,ci,review,base_branch:"codex/own-capital-sustainable-return",head_branch:"control-plane/owner-authorized-payload-repair-resume-v1"});
  assert.equal(authorization.critical_merge_key,verifyOwnerAuthorizedCriticalMerge(input()).critical_merge_key);
  assert.throws(()=>discoverOwnerAuthorizedCriticalMerge({comments:[...comments,comments[0]],sources,decision,ci,review,base_branch:"codex/own-capital-sustainable-return",head_branch:"control-plane/owner-authorized-payload-repair-resume-v1"}),/owner critical merge authorization evidence missing or ambiguous/);
});
