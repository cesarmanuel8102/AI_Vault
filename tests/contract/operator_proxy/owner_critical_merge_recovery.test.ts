import test from "node:test";
import assert from "node:assert/strict";
import {mkdtempSync} from "node:fs";
import {tmpdir} from "node:os";
import {join} from "node:path";
import {LifecycleStore} from "../../../scripts/operator_proxy/lifecycle_store.js";
import {AutonomousFlow} from "../../../scripts/operator_proxy/autonomous_flow.js";
import {OwnerCriticalMergeReceiptLedger} from "../../../scripts/operator_proxy/owner_critical_merge_receipt_ledger.js";
import {ProductionEffects} from "../../../scripts/operator_proxy/production_effects.js";
import {Ledger} from "../../../scripts/operator_proxy/decision_ledger.js";
import type {LifecycleRecord,OwnerAuthorizedCriticalMerge} from "../../../scripts/operator_proxy/types.js";

const base="a".repeat(40),head="b".repeat(40);
const authorization=():OwnerAuthorizedCriticalMerge=>({schema_version:1,authorization_id:"CESAR-BRAIN-101-OPERATOR-PROXY-20260722-01",critical_merge_key:"c".repeat(64),owner_principal:"cesarmanuel8102",owner_comment_id:"5000002771",repository:"cesarmanuel8102/AI_Vault",issue:277,front_id:"BRAIN-101-R3-OWNER-CRITICAL-MERGE-01",pr:277,base_branch:"codex/own-capital-sustainable-return",base_sha:base,head_branch:"control-plane/critical-merge",head_sha:head,policy_decision_id:"critical-policy-decision",policy_decision_key:"d".repeat(64),policy_sha256:"e".repeat(64),policy_outcome:"ESCALATE_TO_OWNER",ci_evidence_id:"ci-run-277",ci_evidence_sha256:"f".repeat(64),review_receipt_id:"review-277",review_receipt_sha256:"1".repeat(64),reviewer_model:"ollama-cloud/deepseek-v4-pro",review_verdict:"PASS",review_findings_count:0,risk:"CRITICAL",action:"OWNER_AUTHORIZED_CRITICAL_MERGE",max_uses:1,authorization_body_sha256:"2".repeat(64)});
const escalated=():LifecycleRecord=>({schema_version:1,front_id:authorization().front_id,roadmap_item_id:"R3.4",state:"ESCALATED",issue:277,pr:277,base_sha:base,head_sha:head,builder_session:"builder-277",reviewer_session:"reviewer-277",decision_id:"critical-policy-decision",repair_cycles:2,deployment_mode:"NO_DEPLOY",completed_effects:["issue:277",`build:${head}`],last_error:"OWNER_AUTHORITY_REQUIRED",updated_utc:"2026-09-04T00:00:00.000Z"});

test("only the dedicated owner operation moves an exact escalated CRITICAL lifecycle into MERGING",()=>{
  const root=mkdtempSync(join(tmpdir(),"critical-merge-recovery-")),store=new LifecycleStore(join(root,"lifecycle")),receipts=new OwnerCriticalMergeReceiptLedger(join(root,"receipts")),grant=authorization(),state=escalated();
  store.save(state);receipts.appendVerified(grant);const consumed=receipts.consume(grant.critical_merge_key);
  assert.throws(()=>store.advance(state,"MERGING"),/owner critical merge transition requires dedicated operation/);
  const merging=store.beginOwnerCriticalMerge(state,receipts,grant,consumed);
  assert.equal(merging.state,"MERGING");assert.equal(merging.repair_cycles,2);
  assert.deepEqual(merging.owner_critical_merge,{critical_merge_key:grant.critical_merge_key,consumed_event_sha256:consumed.event_sha256});
});

test("dedicated owner operation rejects a replayed or non-exact consumed receipt",()=>{
  const root=mkdtempSync(join(tmpdir(),"critical-merge-recovery-denied-")),store=new LifecycleStore(join(root,"lifecycle")),receipts=new OwnerCriticalMergeReceiptLedger(join(root,"receipts")),grant=authorization(),state=escalated();
  store.save(state);receipts.appendVerified(grant);const consumed=receipts.consume(grant.critical_merge_key);
  const merging=store.beginOwnerCriticalMerge(state,receipts,grant,consumed);
  assert.throws(()=>store.beginOwnerCriticalMerge(merging,receipts,grant,consumed),/owner critical merge lifecycle authorization denied/);
  assert.throws(()=>store.beginOwnerCriticalMerge(state,receipts,{...grant,head_sha:"3".repeat(40)},consumed),/owner critical merge lifecycle authorization denied/);
});

test("autonomous flow resumes an escalated CRITICAL merge only through its dedicated effect",async()=>{
  const root=mkdtempSync(join(tmpdir(),"critical-merge-flow-")),store=new LifecycleStore(join(root,"lifecycle")),receipts=new OwnerCriticalMergeReceiptLedger(join(root,"receipts")),grant=authorization(),state=escalated();
  store.save(state);receipts.appendVerified(grant);const consumed=receipts.consume(grant.critical_merge_key);
  const flow=new AutonomousFlow(store,{bindLifecycle:()=>{},ensureIssue:()=>{throw new Error("unexpected");},ensureBuild:async()=>{throw new Error("unexpected");},ci:()=>"PENDING",review:()=>{throw new Error("unexpected");},policy:()=>{throw new Error("unexpected");},ensureMerge:()=>{throw new Error("ordinary merge must not run");},ensureInstall:()=>"PASS",ensureRuntimePilot:()=>"PENDING",ensureCloseout:async()=>"PENDING",discoverNext:()=>{},resumeOwnerCriticalMerge:(_spec:any,current:any,currentStore:any)=>currentStore.beginOwnerCriticalMerge(current,receipts,grant,consumed)} as any);
  const next=await flow.step({front_id:grant.front_id,roadmap_item_id:"R3.4",expected_base_sha:base} as any);
  assert.equal(next.state,"MERGING");assert.equal(next.owner_critical_merge?.critical_merge_key,grant.critical_merge_key);
});

test("production critical merge adapter waits without Owner evidence and performs no ordinary merge",async()=>{
  const root=mkdtempSync(join(tmpdir(),"critical-merge-production-wait-")),store=new LifecycleStore(join(root,"lifecycle")),state=escalated();store.save(state);
  let ordinaryMerges=0;const bus:any={setMutationGuard:()=>{},issueComments:()=>[],merge:()=>{ordinaryMerges++;return "c".repeat(40)}};
  const effects=new ProductionEffects(bus,new Ledger(join(root,"ledger")),root,root,{assert:()=>{}} as any);
  const result=await effects.resumeOwnerCriticalMerge({front_id:state.front_id,roadmap_item_id:state.roadmap_item_id,expected_base_sha:base,work_branch:authorization().head_branch} as any,state,store);
  assert.equal(result,"PENDING");assert.equal(ordinaryMerges,0);
});
