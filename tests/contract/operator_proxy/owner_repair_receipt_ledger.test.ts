import test from "node:test";
import assert from "node:assert/strict";
import {appendFileSync,mkdtempSync,readFileSync,writeFileSync} from "node:fs";
import {tmpdir} from "node:os";
import {join} from "node:path";
import {OwnerRepairReceiptLedger} from "../../../scripts/operator_proxy/owner_repair_receipt_ledger.js";
import type {OwnerAuthorizedPayloadRepairGrant} from "../../../scripts/operator_proxy/types.js";

const sha=(character:string)=>character.repeat(64);
const grant=(front_id="BRAIN-101-R3-OWNER-RECEIPT-01",grant_key=sha("a")):OwnerAuthorizedPayloadRepairGrant=>({schema_version:1,authorization_id:"CESAR-BRAIN-101-OPERATOR-PROXY-20260722-01",grant_key,owner_principal:"cesarmanuel8102",repository:"cesarmanuel8102/AI_Vault",roadmap_id:"BRAIN-101",roadmap_item_id:"R3.4",front_id,issue:248,pr:249,work_branch:"control-plane/owner-receipt",canonical_base_sha:"b".repeat(40),failed_head_sha:"c".repeat(40),eligible_failure_class:"CI_FAILED",max_extra_builds:1,correction_payload:{schema_version:1,requirements:[{requirement_id:"fix",instruction:"Fix only the approved contract."}],preserved_invariants:["HUMAN_FINAL_AUTHORITY"]},correction_payload_sha256:sha("d"),owner_comment_id:"5000000001",authorization_body_sha256:sha("e")});
const ledger=()=>new OwnerRepairReceiptLedger(mkdtempSync(join(tmpdir(),"owner-receipt-ledger-")));

test("append-only receipt ledger derives the only legal owner repair phase chain",()=>{
  const store=ledger(),g=grant();
  const verified=store.appendVerified(g);
  const consumed=store.consume(g.grant_key);
  const dispatched=store.markBuildDispatched(g.grant_key);
  const bound=store.bindHead(g.grant_key,"f".repeat(40));
  const terminal=store.terminalize(g.grant_key,"CI_FAILED");
  assert.deepEqual([verified.phase,consumed.phase,dispatched.phase,bound.phase,terminal.phase],["VERIFIED","CONSUMED","BUILD_DISPATCHED","HEAD_BOUND","TERMINAL"]);
  assert.equal(consumed.build_attempt_id,store.deriveReceiptView(g.grant_key).build_attempt_id);
  assert.equal(dispatched.predecessor_event_sha256,consumed.event_sha256);
  assert.equal(bound.predecessor_event_sha256,dispatched.event_sha256);
});

test("receipt ledger rejects duplicate conflicting reordered and corrupted event chains",()=>{
  const store=ledger(),g=grant();
  store.appendVerified(g);
  assert.throws(()=>store.appendVerified(g),/receipt/i);
  assert.throws(()=>store.markBuildDispatched(g.grant_key),/receipt/i);
  const consumed=store.consume(g.grant_key);
  const path=join(store.root,"owner-repair-receipts.jsonl");
  appendFileSync(path,`${JSON.stringify({...consumed,sequence:9})}\n`);
  assert.throws(()=>store.deriveReceiptView(g.grant_key),/receipt/i);
});

test("receipt ledger persists the deterministic attempt before dispatch and denies a second owner exception for the front",()=>{
  const store=ledger(),first=grant(),second=grant(first.front_id,sha("f"));
  store.appendVerified(first);
  const consumed=store.consume(first.grant_key);
  assert.match(consumed.build_attempt_id??"",/^[0-9a-f]{64}$/);
  assert.equal(store.hasConsumedOwnerException(first.front_id),true);
  store.appendVerified(second);
  assert.throws(()=>store.consume(second.grant_key),/owner exception.*consumed|receipt/i);
  assert.match(readFileSync(join(store.root,"owner-repair-receipts.jsonl"),"utf8"),/BUILD_DISPATCHED|CONSUMED/);
});

test("consume rechecks the per-front exception invariant inside the append lock",()=>{
  const first=ledger(),one=grant(),two=grant(one.front_id,sha("f"));
  first.appendVerified(one);first.appendVerified(two);const second=new OwnerRepairReceiptLedger(first.root);
  let injected=false;
  (first as any).hasConsumedOwnerException=()=>{if(!injected){injected=true;second.consume(two.grant_key);}return false;};
  assert.throws(()=>first.consume(one.grant_key),/owner exception.*consumed/);
  const events=readFileSync(join(first.root,"owner-repair-receipts.jsonl"),"utf8").trim().split("\n").map(line=>JSON.parse(line));
  assert.equal(events.filter(event=>event.front_id===one.front_id&&event.phase==="CONSUMED").length,1);
});

test("receipt ledger fails closed while another process owns the append transaction",()=>{
  const store=ledger();
  writeFileSync(join(store.root,"owner-repair-receipts.lock"),"held");
  assert.throws(()=>store.appendVerified(grant()),/receipt lock unavailable/);
});

test("durable grant snapshot is recoverable by exact lifecycle identity after consumption",()=>{
  const store=ledger(),g=grant();
  store.appendVerified(g);store.consume(g.grant_key);
  assert.deepEqual(store.findGrantSnapshot({front_id:g.front_id,issue:g.issue,pr:g.pr,failed_head_sha:g.failed_head_sha}),g);
  assert.equal(store.findGrantSnapshot({front_id:g.front_id,issue:g.issue,pr:g.pr,failed_head_sha:"f".repeat(40)}),undefined);
});
