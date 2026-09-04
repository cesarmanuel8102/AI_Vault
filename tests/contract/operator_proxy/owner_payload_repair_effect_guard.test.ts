import test from "node:test";
import assert from "node:assert/strict";
import {mkdtempSync,mkdirSync} from "node:fs";
import {tmpdir} from "node:os";
import {join} from "node:path";
import {ExternalEffectBoundary} from "../../../scripts/operator_proxy/external_effect_guard.js";
import type {OwnerAuthorizedCriticalMerge} from "../../../scripts/operator_proxy/types.js";

const base="a".repeat(40),head="b".repeat(40),attempt="c".repeat(64),consumed="d".repeat(64),grantKey="e".repeat(64),dispatch="f".repeat(64);
const spec:any={authorization_id:"AUTH",repository:"cesarmanuel8102/AI_Vault",roadmap_id:"BRAIN-101",roadmap_item_id:"R3.5",expected_base_sha:base,front_id:"BRAIN-101-R3-OWNER-01",work_branch:"control-plane/owner",allowed_paths:["docs/"],forbidden_paths:["trading/"]};
const state:any={schema_version:1,front_id:spec.front_id,roadmap_item_id:spec.roadmap_item_id,state:"BUILDING",issue:1,pr:2,base_sha:base,head_sha:head,repair_cycles:2,deployment_mode:"NO_DEPLOY",completed_effects:["issue:1",`build:${head}`],owner_payload_repair:{grant_key:grantKey,build_attempt_id:attempt,consumed_event_sha256:consumed},updated_utc:new Date().toISOString()};
const grant:any={authorization_id:"AUTH",grant_key:grantKey,repository:spec.repository,roadmap_id:spec.roadmap_id,roadmap_item_id:spec.roadmap_item_id,front_id:spec.front_id,issue:1,pr:2,work_branch:spec.work_branch,canonical_base_sha:base,failed_head_sha:head,eligible_failure_class:"CI_FAILED",max_extra_builds:1};
const receipt=(phase="BUILD_DISPATCHED"):any=>({phase,grant_key:grantKey,front_id:spec.front_id,authorization_id:"AUTH",failed_head_sha:head,build_attempt_id:attempt,predecessor_event_sha256:consumed,event_sha256:dispatch});
function guard(){const root=mkdtempSync(join(tmpdir(),"owner-guard-"));mkdirSync(join(root,"state"));return new ExternalEffectBoundary(root,{branchHead:()=>base,issuePaused:()=>false,prIdentity:()=>({headRefOid:head})} as any,()=>true);}
test("owner transport capability requires the exact durable BUILD_DISPATCHED receipt and is not forgeable",()=>{
  const context={spec,state,grant,build_attempt_id:attempt,consumed_event_sha256:consumed,build_dispatched_event_sha256:dispatch};const boundary=guard(),cap=boundary.authorizeOwnerPayloadRepairTransport(context,receipt());
  assert.doesNotThrow(()=>boundary.assertOwnerPayloadRepairTransport(cap));
  for(const [name,mutate] of [["consumed",(x:any)=>x.phase="CONSUMED"],["head-bound",(x:any)=>x.phase="HEAD_BOUND"],["event",(x:any)=>x.event_sha256="0".repeat(64)],["predecessor",(x:any)=>x.predecessor_event_sha256="0".repeat(64)],["front",(x:any)=>x.front_id="OTHER"],["grant",(x:any)=>x.grant_key="0".repeat(64)],["authorization",(x:any)=>x.authorization_id="OTHER"],["attempt",(x:any)=>x.build_attempt_id="0".repeat(64)],["failed-head",(x:any)=>x.failed_head_sha="0".repeat(40)]] as const){const value=receipt();mutate(value);assert.throws(()=>guard().authorizeOwnerPayloadRepairTransport(context,value),/denied/,name);}
  assert.throws(()=>boundary.assertOwnerPayloadRepairTransport({...cap}),/denied/);
});

test("owner transport capability is cleared when lifecycle leaves the exceptional build",()=>{
  const boundary=guard(),cap=boundary.authorizeOwnerPayloadRepairTransport({spec,state,grant,build_attempt_id:attempt,consumed_event_sha256:consumed,build_dispatched_event_sha256:dispatch},receipt());
  boundary.bind(spec,{...state,state:"CI_PENDING",head_sha:"0".repeat(40),owner_payload_repair:undefined});
  assert.throws(()=>boundary.assertOwnerPayloadRepairTransport(cap),/owner payload repair transport denied/);
});

const criticalAuthorization=():OwnerAuthorizedCriticalMerge=>({schema_version:1,authorization_id:"CESAR-BRAIN-101-OPERATOR-PROXY-20260722-01",critical_merge_key:"1".repeat(64),owner_principal:"cesarmanuel8102",owner_comment_id:"5000002771",repository:"cesarmanuel8102/AI_Vault",issue:7,front_id:"BRAIN-101-R3-OWNER-CRITICAL-01",pr:8,base_branch:"codex/own-capital-sustainable-return",base_sha:base,head_branch:"control-plane/critical-merge",head_sha:head,policy_decision_id:"critical-policy-decision",policy_decision_key:"2".repeat(64),policy_sha256:"3".repeat(64),policy_outcome:"ESCALATE_TO_OWNER",ci_evidence_id:"ci-run-8",ci_evidence_sha256:"4".repeat(64),review_receipt_id:"review-8",review_receipt_sha256:"5".repeat(64),reviewer_model:"ollama-cloud/deepseek-v4-pro",review_verdict:"PASS",review_findings_count:0,risk:"CRITICAL",action:"OWNER_AUTHORIZED_CRITICAL_MERGE",max_uses:1,authorization_body_sha256:"6".repeat(64)});
const criticalReceipt=(authorization=criticalAuthorization()):any=>({schema_version:1,critical_merge_key:authorization.critical_merge_key,sequence:2,phase:"MERGE_DISPATCHED",predecessor_event_sha256:"7".repeat(64),event_sha256:"8".repeat(64),authorization_id:authorization.authorization_id,repository:authorization.repository,issue:authorization.issue,front_id:authorization.front_id,pr:authorization.pr,base_branch:authorization.base_branch,base_sha:authorization.base_sha,head_branch:authorization.head_branch,head_sha:authorization.head_sha,policy_decision_id:authorization.policy_decision_id,policy_decision_key:authorization.policy_decision_key,immutable_authorization_snapshot_sha256:"9".repeat(64),created_at:"2026-09-04T00:00:00.000Z"});

test("owner critical merge capability requires one exact dispatched receipt and current trusted Draft PR identity",()=>{
  const authorization=criticalAuthorization(),root=mkdtempSync(join(tmpdir(),"critical-guard-"));mkdirSync(join(root,"state"));let identity:any={author:{login:"cesarmanuel8102"},baseRefName:authorization.base_branch,baseRefOid:base,headRefName:authorization.head_branch,headRefOid:head,headRepository:{nameWithOwner:authorization.repository},isCrossRepository:false,isDraft:true,state:"OPEN",mergeable:"MERGEABLE"};
  const boundary=new ExternalEffectBoundary(root,{branchHead:()=>base,issuePaused:()=>false,prIdentity:()=>identity} as any,()=>true),spec:any={authorization_id:authorization.authorization_id,repository:authorization.repository,front_id:authorization.front_id,roadmap_item_id:"R3.4",expected_base_sha:base,risk:"CRITICAL"},state:any={schema_version:1,front_id:authorization.front_id,roadmap_item_id:"R3.4",state:"ESCALATED",issue:authorization.issue,pr:authorization.pr,base_sha:base,head_sha:head,decision_id:authorization.policy_decision_id,repair_cycles:2,deployment_mode:"NO_DEPLOY",completed_effects:[],updated_utc:new Date().toISOString()};
  state.state="MERGING";state.owner_critical_merge={critical_merge_key:authorization.critical_merge_key,consumed_event_sha256:"7".repeat(64)};
  boundary.bind(spec,state);const capability=boundary.authorizeOwnerCriticalMerge({spec,state,authorization},criticalReceipt(authorization));
  assert.doesNotThrow(()=>boundary.assertOwnerCriticalMerge(capability));assert.doesNotThrow(()=>boundary.assert("merge",{issue:authorization.issue,pr:authorization.pr,expected_head:head}));
  for(const mutate of [(value:any)=>value.isCrossRepository=true,(value:any)=>value.headRepository.nameWithOwner="attacker/fork",(value:any)=>value.baseRefOid="0".repeat(40),(value:any)=>value.headRefOid="0".repeat(40),(value:any)=>value.isDraft=false,(value:any)=>value.state="CLOSED"]){const saved=identity;identity={...identity,author:{...identity.author},headRepository:{...identity.headRepository}};mutate(identity);assert.throws(()=>boundary.assert("merge",{issue:authorization.issue,pr:authorization.pr,expected_head:head}),/owner critical merge denied/);identity=saved;}
  assert.throws(()=>boundary.assert("merge",{issue:authorization.issue,pr:authorization.pr,expected_head:"0".repeat(40)}),/owner critical merge denied/);
});
