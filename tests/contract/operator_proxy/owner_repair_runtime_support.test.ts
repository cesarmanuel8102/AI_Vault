import test from "node:test";
import assert from "node:assert/strict";
import {mkdtempSync,readFileSync,writeFileSync} from "node:fs";
import {createHash} from "node:crypto";
import {tmpdir} from "node:os";
import {join} from "node:path";
import {OwnerRepairRuntimeSupportLedger} from "../../../scripts/operator_proxy/owner_repair_runtime_support.js";
import {OwnerRepairEffectiveBaseLedger} from "../../../scripts/operator_proxy/owner_repair_effective_base.js";
import {OwnerRepairReceiptLedger} from "../../../scripts/operator_proxy/owner_repair_receipt_ledger.js";
import type {OwnerAuthorizedPayloadRepairGrant} from "../../../scripts/operator_proxy/types.js";

const sha40=(value:string)=>value.repeat(40);
const sha64=(value:string)=>value.repeat(64);
const base=sha40("b"),effective=sha40("c"),runtime=sha40("d"),foreign=sha40("e"),advanced=sha40("9");
const canonical=(value:unknown):unknown=>Array.isArray(value)?value.map(canonical):value&&typeof value==="object"?Object.fromEntries(Object.entries(value as Record<string,unknown>).sort(([left],[right])=>left.localeCompare(right)).map(([key,child])=>[key,canonical(child)])):value;
const supportDigest=(event:Record<string,unknown>)=>{const {event_sha256,...body}=event;return createHash("sha256").update(`${JSON.stringify(canonical(body))}\n`,"utf8").digest("hex");};

function setup(){
  const root=mkdtempSync(join(tmpdir(),"owner-runtime-support-"));
  const receipts=new OwnerRepairReceiptLedger(join(root,"receipts"));
  const grant:OwnerAuthorizedPayloadRepairGrant={schema_version:1,authorization_id:"CESAR-BRAIN-101-OPERATOR-PROXY-20260722-01",grant_key:sha64("a"),owner_principal:"cesarmanuel8102",repository:"cesarmanuel8102/AI_Vault",roadmap_id:"BRAIN-101",roadmap_item_id:"R3.4",front_id:"OWNER-RUNTIME-SUPPORT",issue:248,pr:249,work_branch:"control-plane/owner-runtime-support",canonical_base_sha:base,failed_head_sha:sha40("f"),eligible_failure_class:"CI_FAILED",max_extra_builds:1,correction_payload:{schema_version:1,requirements:[{requirement_id:"repair",instruction:"Apply the approved repair."}],preserved_invariants:["HUMAN_FINAL_AUTHORITY"]},correction_payload_sha256:sha64("1"),owner_comment_id:"5000000001",authorization_body_sha256:sha64("2")};
  receipts.appendVerified(grant);const consumed=receipts.consume(grant.grant_key),dispatched=receipts.markBuildDispatched(grant.grant_key);
  const bases=new OwnerRepairEffectiveBaseLedger(join(root,"bases"));
  const binding=bases.bind({grant_key:grant.grant_key,front_id:grant.front_id,authorization_id:grant.authorization_id,build_attempt_id:consumed.build_attempt_id!,frozen_base_sha:base,effective_base_sha:effective,failed_head_sha:grant.failed_head_sha,build_dispatched_event_sha256:dispatched.event_sha256,canonical_branch:"codex/own-capital-sustainable-return",installed_runtime_sha:effective,predecessor_event_sha256:dispatched.event_sha256},{receipts,currentTip:effective,installedRuntimeSha:effective,doctorPassed:true,isAncestor:(older:string,newer:string)=>older===newer||older===base&&[effective,runtime].includes(newer)});
  return {root,receipts,grant,binding};
}

test("binds an installed canonical descendant without changing the immutable effective base",()=>{
  const value=setup(),ledger=new OwnerRepairRuntimeSupportLedger(join(value.root,"supports"));
  const support=ledger.bind(value.binding,{currentTip:runtime,installedRuntimeSha:runtime,isAncestor:(older,newer)=>older===newer||older===effective&&newer===runtime});
  assert.equal(support.effective_base_sha,effective);
  assert.equal(support.runtime_support_sha,runtime);
  assert.equal(ledger.load(value.grant.grant_key)?.event_sha256,support.event_sha256);
});

test("rejects a foreign runtime and a runtime/tip mismatch",()=>{
  const value=setup(),ledger=new OwnerRepairRuntimeSupportLedger(join(value.root,"supports"));
  assert.throws(()=>ledger.bind(value.binding,{currentTip:foreign,installedRuntimeSha:foreign,isAncestor:(older,newer)=>older===newer}),/runtime support/i);
  assert.throws(()=>ledger.bind(value.binding,{currentTip:runtime,installedRuntimeSha:foreign,isAncestor:(older,newer)=>older===newer||older===effective&&newer===runtime}),/runtime support/i);
});

test("appends a strictly descendant runtime support chain and rejects rewind or fork",()=>{
  const value=setup(),ledger=new OwnerRepairRuntimeSupportLedger(join(value.root,"supports"));
  const first=ledger.bind(value.binding,{currentTip:runtime,installedRuntimeSha:runtime,isAncestor:(older,newer)=>older===newer||older===effective&&[runtime,advanced].includes(newer)});
  const second=ledger.bind(value.binding,{currentTip:advanced,installedRuntimeSha:advanced,isAncestor:(older,newer)=>older===newer||older===effective&&[runtime,advanced].includes(newer)||older===runtime&&newer===advanced});
  assert.equal(second.predecessor_event_sha256,first.event_sha256);
  assert.notEqual(second.event_sha256,first.event_sha256);
  assert.equal(ledger.load(value.grant.grant_key)?.runtime_support_sha,advanced);
  assert.throws(()=>ledger.bind(value.binding,{currentTip:runtime,installedRuntimeSha:runtime,isAncestor:(older,newer)=>older===newer||older===effective&&newer===runtime}),/conflict|ancestry/i);
  assert.throws(()=>ledger.bind(value.binding,{currentTip:foreign,installedRuntimeSha:foreign,isAncestor:(older,newer)=>older===newer||older===effective&&newer===foreign}),/conflict|ancestry/i);
});

test("rejects a hash-valid first support event that is not anchored to the immutable binding",()=>{
  const value=setup(),ledger=new OwnerRepairRuntimeSupportLedger(join(value.root,"supports"));
  const first=ledger.bind(value.binding,{currentTip:runtime,installedRuntimeSha:runtime,isAncestor:(older,newer)=>older===newer||older===effective&&newer===runtime});
  const path=join(value.root,"supports","owner-repair-runtime-support.jsonl"),forged={...first,predecessor_event_sha256:sha64("f")};
  forged.event_sha256=supportDigest(forged);
  writeFileSync(path,`${JSON.stringify(forged)}\n`,`utf8`);
  assert.throws(()=>ledger.bind(value.binding,{currentTip:advanced,installedRuntimeSha:advanced,isAncestor:(older,newer)=>older===newer||older===effective&&[runtime,advanced].includes(newer)||older===runtime&&newer===advanced}),/root|conflict/i);
  assert.notEqual(readFileSync(path,"utf8").trim(),"");
});

test("rejects a hash-valid duplicate runtime support transition",()=>{
  const value=setup(),ledger=new OwnerRepairRuntimeSupportLedger(join(value.root,"supports"));
  const first=ledger.bind(value.binding,{currentTip:runtime,installedRuntimeSha:runtime,isAncestor:(older,newer)=>older===newer||older===effective&&newer===runtime});
  const path=join(value.root,"supports","owner-repair-runtime-support.jsonl"),duplicate={...first,predecessor_event_sha256:first.event_sha256,created_at:"2026-09-07T00:00:01.000Z"};
  duplicate.event_sha256=supportDigest(duplicate);
  writeFileSync(path,`${JSON.stringify(first)}\n${JSON.stringify(duplicate)}\n`,`utf8`);
  assert.throws(()=>ledger.load(value.grant.grant_key),/duplicate/i);
});
