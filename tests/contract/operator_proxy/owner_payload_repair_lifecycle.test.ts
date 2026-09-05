import test from "node:test";
import assert from "node:assert/strict";
import {mkdtempSync,readFileSync} from "node:fs";
import {tmpdir} from "node:os";
import {join} from "node:path";
import {LifecycleStore} from "../../../scripts/operator_proxy/lifecycle_store.js";
import {OwnerRepairReceiptLedger} from "../../../scripts/operator_proxy/owner_repair_receipt_ledger.js";
import type {LifecycleRecord,OwnerAuthorizedPayloadRepairGrant} from "../../../scripts/operator_proxy/types.js";

const grant:OwnerAuthorizedPayloadRepairGrant={schema_version:1,authorization_id:"CESAR-BRAIN-101-OPERATOR-PROXY-20260722-01",grant_key:"a".repeat(64),owner_principal:"cesarmanuel8102",repository:"cesarmanuel8102/AI_Vault",roadmap_id:"BRAIN-101",roadmap_item_id:"R3.4",front_id:"BRAIN-101-R3-OWNER-LIFECYCLE-01",issue:248,pr:249,work_branch:"control-plane/owner-lifecycle",canonical_base_sha:"b".repeat(40),failed_head_sha:"c".repeat(40),eligible_failure_class:"CI_FAILED",max_extra_builds:1,correction_payload:{schema_version:1,requirements:[{requirement_id:"fix",instruction:"Preserve prior repair evidence."}],preserved_invariants:["HUMAN_FINAL_AUTHORITY"]},correction_payload_sha256:"d".repeat(64),owner_comment_id:"5000000001",authorization_body_sha256:"e".repeat(64)};
const blocked=():LifecycleRecord=>({schema_version:1,front_id:grant.front_id,roadmap_item_id:grant.roadmap_item_id,state:"BLOCKED",last_error:"CI_FAILED",issue:grant.issue,pr:grant.pr,base_sha:grant.canonical_base_sha,head_sha:grant.failed_head_sha,builder_session:"builder-original",repair_cycles:2,deployment_mode:"NO_DEPLOY",completed_effects:[`issue:${grant.issue}`,`build:${grant.failed_head_sha}`],updated_utc:new Date().toISOString()});

test("consumed owner receipt authorizes then begins one exceptional build without altering ordinary repair accounting",()=>{
  const root=mkdtempSync(join(tmpdir(),"owner-lifecycle-")),store=new LifecycleStore(join(root,"lifecycle")),receipts=new OwnerRepairReceiptLedger(join(root,"receipts"));
  receipts.appendVerified(grant);const consumed=receipts.consume(grant.grant_key);const initial=blocked();store.save(initial);
  const authorized=store.authorizeOwnerPayloadRepair(initial,receipts,consumed);
  assert.equal(authorized.state,"OWNER_REPAIR_AUTHORIZED");
  assert.equal(authorized.repair_cycles,2);
  assert.deepEqual(authorized.completed_effects,initial.completed_effects);
  assert.deepEqual(authorized.owner_payload_repair,{grant_key:grant.grant_key,consumed_event_sha256:consumed.event_sha256,build_attempt_id:consumed.build_attempt_id});
  const building=store.beginOwnerPayloadRepairBuild(authorized,consumed);
  assert.equal(building.state,"BUILDING");
  assert.equal(building.repair_cycles,2);
  const events=readFileSync(join(root,"lifecycle","events.jsonl"),"utf8");
  assert.match(events,/lifecycle_owner_payload_repair_authorized/);
  assert.match(events,/lifecycle_owner_payload_repair_build_started/);
  assert.doesNotMatch(events,/lifecycle_repair_build_replaced/);
});

test("owner lifecycle transition rejects a non-consumed receipt and any non-exhausted or non-CI blocked record",()=>{
  const root=mkdtempSync(join(tmpdir(),"owner-lifecycle-denied-")),store=new LifecycleStore(join(root,"lifecycle")),receipts=new OwnerRepairReceiptLedger(join(root,"receipts"));
  const verified=receipts.appendVerified(grant),consumed=receipts.consume(grant.grant_key);
  for(const record of [{...blocked(),repair_cycles:1},{...blocked(),last_error:"POLICY_BLOCK"},{...blocked(),front_id:"OTHER-FRONT-01"}])assert.throws(()=>store.authorizeOwnerPayloadRepair(record,receipts,consumed),/owner payload repair.*denied/);
  assert.throws(()=>store.authorizeOwnerPayloadRepair(blocked(),receipts,verified),/owner payload repair.*denied/);
  assert.throws(()=>store.authorizeOwnerPayloadRepair(blocked(),new OwnerRepairReceiptLedger(join(root,"other-receipts")),consumed),/owner payload repair.*denied/);
  assert.throws(()=>store.authorizeOwnerPayloadRepair({...blocked(),front_id:"OTHER-FRONT-01"},receipts,{...consumed,front_id:"OTHER-FRONT-01"}),/owner payload repair.*denied/);
});

test("owner adoption preserves the exhausted repair budget without an ordinary repair replacement event",()=>{
  const root=mkdtempSync(join(tmpdir(),"owner-lifecycle-adopt-")),store=new LifecycleStore(join(root,"lifecycle")),receipts=new OwnerRepairReceiptLedger(join(root,"receipts"));
  receipts.appendVerified(grant);const consumed=receipts.consume(grant.grant_key);const authorized=store.authorizeOwnerPayloadRepair(blocked(),receipts,consumed),building=store.beginOwnerPayloadRepairBuild(authorized,consumed);
  const adopted=store.adoptOwnerPayloadRepairCandidate(building,{pr:grant.pr,head_sha:"f".repeat(40),builder_session:"owner-build-session",grant_key:grant.grant_key,build_attempt_id:consumed.build_attempt_id!,consumed_event_sha256:consumed.event_sha256});
  assert.equal(adopted.state,"CI_PENDING");assert.equal(adopted.repair_cycles,2);assert.deepEqual(adopted.completed_effects,[`issue:${grant.issue}`,`build:${"f".repeat(40)}`]);
  const events=readFileSync(join(root,"lifecycle","events.jsonl"),"utf8");assert.match(events,/lifecycle_owner_payload_repair_candidate_adopted/);assert.doesNotMatch(events,/lifecycle_repair_build_replaced/);
});
