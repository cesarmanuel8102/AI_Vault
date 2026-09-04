import test from "node:test";
import assert from "node:assert/strict";
import {createHash} from "node:crypto";
import {appendFileSync,mkdtempSync,readFileSync,writeFileSync} from "node:fs";
import {tmpdir} from "node:os";
import {join} from "node:path";
import {OwnerCriticalMergeReceiptLedger} from "../../../scripts/operator_proxy/owner_critical_merge_receipt_ledger.js";
import type {OwnerAuthorizedCriticalMerge} from "../../../scripts/operator_proxy/types.js";

const authorization=(head_sha="b".repeat(40),critical_merge_key="a".repeat(64)):OwnerAuthorizedCriticalMerge=>({schema_version:1,authorization_id:"CESAR-BRAIN-101-OPERATOR-PROXY-20260722-01",critical_merge_key,owner_principal:"cesarmanuel8102",owner_comment_id:"5000002771",repository:"cesarmanuel8102/AI_Vault",issue:277,front_id:"BRAIN-101-R3-OWNER-CRITICAL-MERGE-01",pr:277,base_branch:"codex/own-capital-sustainable-return",base_sha:"c".repeat(40),head_branch:"control-plane/critical-merge",head_sha,policy_decision_id:"critical-policy-decision",policy_decision_key:"d".repeat(64),policy_sha256:"e".repeat(64),policy_outcome:"ESCALATE_TO_OWNER",ci_evidence_id:"ci-run-277",ci_evidence_sha256:"f".repeat(64),review_receipt_id:"review-277",review_receipt_sha256:"1".repeat(64),reviewer_model:"ollama-cloud/deepseek-v4-pro",review_verdict:"PASS",review_findings_count:0,risk:"CRITICAL",action:"OWNER_AUTHORIZED_CRITICAL_MERGE",max_uses:1,authorization_body_sha256:"2".repeat(64)});
const ledger=()=>new OwnerCriticalMergeReceiptLedger(mkdtempSync(join(tmpdir(),"owner-critical-merge-ledger-")));
const canonicalize=(value:unknown):unknown=>Array.isArray(value)?value.map(canonicalize):value&&typeof value==="object"?Object.fromEntries(Object.entries(value as Record<string,unknown>).sort(([a],[b])=>a.localeCompare(b)).map(([key,child])=>[key,canonicalize(child)])):value;
const eventHash=(event:Record<string,unknown>)=>{const {event_sha256,...body}=event;return createHash("sha256").update(`${JSON.stringify(canonicalize(body))}\n`,"utf8").digest("hex");};

test("critical merge receipt ledger derives the only legal append-only phase chain",()=>{
  const store=ledger(),grant=authorization();
  const verified=store.appendVerified(grant);
  const consumed=store.consume(grant.critical_merge_key);
  const dispatched=store.markMergeDispatched(grant.critical_merge_key);
  const bound=store.bindMergedSha(grant.critical_merge_key,"3".repeat(40));
  assert.deepEqual([verified.phase,consumed.phase,dispatched.phase,bound.phase],["VERIFIED","CONSUMED","MERGE_DISPATCHED","MERGED_BOUND"]);
  assert.equal(dispatched.predecessor_event_sha256,consumed.event_sha256);
  assert.equal(bound.predecessor_event_sha256,dispatched.event_sha256);
  assert.equal(bound.merge_commit_sha,"3".repeat(40));
});

test("critical merge receipt ledger rejects replay, duplicate phase, conflicting predecessor, and changed identity",()=>{
  const store=ledger(),grant=authorization();
  store.appendVerified(grant);
  assert.throws(()=>store.appendVerified(grant),/critical merge receipt/i);
  assert.throws(()=>store.markMergeDispatched(grant.critical_merge_key),/critical merge receipt/i);
  const consumed=store.consume(grant.critical_merge_key);
  assert.throws(()=>store.consume(grant.critical_merge_key),/critical merge receipt/i);
  const path=join(store.root,"owner-critical-merge-receipts.jsonl");
  appendFileSync(path,`${JSON.stringify({...consumed,sequence:2,predecessor_event_sha256:null})}\n`);
  assert.throws(()=>store.deriveReceiptView(grant.critical_merge_key),/critical merge receipt/i);
});

test("post-CONSUMED crash retains the only exact authorization and prohibits a changed-head reuse",()=>{
  const store=ledger(),grant=authorization();
  store.appendVerified(grant);const consumed=store.consume(grant.critical_merge_key);
  assert.equal(store.deriveReceiptView(grant.critical_merge_key).event_sha256,consumed.event_sha256);
  assert.throws(()=>store.assertCurrentConsumedReceipt({...consumed,head_sha:"4".repeat(40)}),/critical merge receipt/i);
  assert.match(readFileSync(join(store.root,"owner-critical-merge-receipts.jsonl"),"utf8"),/CONSUMED/);
});

test("critical merge receipt ledger fails closed while its append transaction is locked",()=>{
  const store=ledger();
  writeFileSync(join(store.root,"owner-critical-merge-receipts.lock"),"held");
  assert.throws(()=>store.appendVerified(authorization()),/critical merge receipt lock unavailable/);
});

test("critical merge receipt ledger rejects a hash-valid snapshot whose identity differs from its event",()=>{
  const store=ledger(),grant=authorization();store.appendVerified(grant);
  const path=join(store.root,"owner-critical-merge-receipts.jsonl"),event=JSON.parse(readFileSync(path,"utf8")) as Record<string,unknown>;
  const snapshot={...(event.immutable_authorization_snapshot as Record<string,unknown>),head_sha:"4".repeat(40)};
  event.immutable_authorization_snapshot=snapshot;
  event.immutable_authorization_snapshot_sha256=createHash("sha256").update(`${JSON.stringify(canonicalize(snapshot))}\n`,"utf8").digest("hex");
  event.event_sha256=eventHash(event);writeFileSync(path,`${JSON.stringify(event)}\n`);
  assert.throws(()=>store.deriveReceiptView(grant.critical_merge_key),/critical merge receipt/i);
});
