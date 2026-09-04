import test from "node:test";
import assert from "node:assert/strict";
import {mkdtempSync} from "node:fs";
import {tmpdir} from "node:os";
import {join} from "node:path";
import {executeOwnerAuthorizedCriticalMerge} from "../../../scripts/operator_proxy/owner_critical_merge_executor.js";
import {OwnerCriticalMergeReceiptLedger} from "../../../scripts/operator_proxy/owner_critical_merge_receipt_ledger.js";
import {execute} from "../../../scripts/operator_proxy/action_executor.js";
import {Ledger} from "../../../scripts/operator_proxy/decision_ledger.js";
import type {Decision,OwnerAuthorizedCriticalMerge} from "../../../scripts/operator_proxy/types.js";

const base="a".repeat(40),head="b".repeat(40),merge="c".repeat(40);
const authorization=():OwnerAuthorizedCriticalMerge=>({schema_version:1,authorization_id:"CESAR-BRAIN-101-OPERATOR-PROXY-20260722-01",critical_merge_key:"d".repeat(64),owner_principal:"cesarmanuel8102",owner_comment_id:"5000002771",repository:"cesarmanuel8102/AI_Vault",issue:277,front_id:"BRAIN-101-R3-OWNER-CRITICAL-MERGE-01",pr:277,base_branch:"codex/own-capital-sustainable-return",base_sha:base,head_branch:"control-plane/critical-merge",head_sha:head,policy_decision_id:"critical-policy-decision",policy_decision_key:"e".repeat(64),policy_sha256:"f".repeat(64),policy_outcome:"ESCALATE_TO_OWNER",ci_evidence_id:"ci-run-277",ci_evidence_sha256:"1".repeat(64),review_receipt_id:"review-277",review_receipt_sha256:"2".repeat(64),reviewer_model:"ollama-cloud/deepseek-v4-pro",review_verdict:"PASS",review_findings_count:0,risk:"CRITICAL",action:"OWNER_AUTHORIZED_CRITICAL_MERGE",max_uses:1,authorization_body_sha256:"3".repeat(64)});
const criticalDecision:Decision={schema_version:2,decision_key:"4".repeat(64),decision_id:"critical-policy-decision",authorization_id:authorization().authorization_id,repository:authorization().repository,issue:277,pr:277,base_sha:base,head_sha:head,roadmap_id:"BRAIN-101",roadmap_item_id:"R3.4",risk:"CRITICAL",deterministic_gate:"PASS",codex_review:"PASS",review_findings_count:0,review_consistent:true,policy_decision:"ESCALATE_TO_OWNER",allowed_action:"NONE",policy_sha256:authorization().policy_sha256,evidence_sha256:"5".repeat(64),created_utc:"2026-09-04T00:00:00.000Z"};

test("normal action executor still refuses a CRITICAL owner-escalated merge",()=>{
  let merges=0;const bus:any={merge:()=>{merges++;return merge;},verifyMerged:()=>merge},ledger=new Ledger(mkdtempSync(join(tmpdir(),"normal-critical-merge-")));
  assert.equal(execute(bus,ledger,criticalDecision,false),undefined);assert.equal(merges,0);
});

test("dedicated critical executor consumes one exact authorization and binds the merge receipt",()=>{
  const receipts=new OwnerCriticalMergeReceiptLedger(mkdtempSync(join(tmpdir(),"critical-merge-executor-")));let merges=0,revalidations=0;
  const result=executeOwnerAuthorizedCriticalMerge({authorization:authorization(),receipts,revalidate:()=>{revalidations++;},boundary:{authorizeOwnerCriticalMerge:(_context:any,receipt:any)=>receipt,assertOwnerCriticalMerge:()=>{}},bus:{mergeOwnerAuthorizedCritical:()=>{merges++;return merge;},verifyMerged:()=>merge}});
  assert.equal(result.merge_commit_sha,merge);assert.equal(merges,1);assert.equal(revalidations,2);assert.equal(receipts.deriveReceiptView(authorization().critical_merge_key).phase,"MERGED_BOUND");
});

test("dedicated critical executor reconciles an already-bound exact merge without another dispatch",()=>{
  const receipts=new OwnerCriticalMergeReceiptLedger(mkdtempSync(join(tmpdir(),"critical-merge-reconcile-"))),grant=authorization();receipts.appendVerified(grant);receipts.consume(grant.critical_merge_key);receipts.markMergeDispatched(grant.critical_merge_key);receipts.bindMergedSha(grant.critical_merge_key,merge);let merges=0;
  const result=executeOwnerAuthorizedCriticalMerge({authorization:grant,receipts,revalidate:()=>{},boundary:{authorizeOwnerCriticalMerge:()=>{throw new Error("must not authorize dispatched merge");},assertOwnerCriticalMerge:()=>{}},bus:{mergeOwnerAuthorizedCritical:()=>{merges++;return merge;},verifyMerged:()=>merge}});
  assert.equal(result.merge_commit_sha,merge);assert.equal(merges,0);
});

test("dedicated critical executor fails closed when revalidation rejects the exact identity",()=>{
  const receipts=new OwnerCriticalMergeReceiptLedger(mkdtempSync(join(tmpdir(),"critical-merge-stale-")));let merges=0;
  assert.throws(()=>executeOwnerAuthorizedCriticalMerge({authorization:authorization(),receipts,revalidate:()=>{throw new Error("critical identity changed");},boundary:{authorizeOwnerCriticalMerge:()=>{throw new Error("unreachable");},assertOwnerCriticalMerge:()=>{}},bus:{mergeOwnerAuthorizedCritical:()=>{merges++;return merge;},verifyMerged:()=>merge}}),/critical identity changed/);
  assert.equal(merges,0);assert.throws(()=>receipts.deriveReceiptView(authorization().critical_merge_key),/missing/);
});
