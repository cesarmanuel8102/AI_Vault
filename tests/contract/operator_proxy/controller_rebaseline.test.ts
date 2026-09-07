import test from "node:test";
import assert from "node:assert/strict";
import {projectHistoricalAttempt,verifyFunctionalEvidenceForRebaseline} from "../../../scripts/operator_proxy/controller_rebaseline.js";
import type {LifecycleRecord} from "../../../scripts/operator_proxy/types.js";

const exhaustedOwnerRecord=():LifecycleRecord=>({
  schema_version:1,
  front_id:"BRAIN-101-CONTROLLER-SYNTHETIC-01",
  roadmap_item_id:"R9.9",
  state:"BUILDING",
  issue:401,
  pr:402,
  base_sha:"a".repeat(40),
  head_sha:"b".repeat(40),
  builder_session:"builder-historical",
  repair_cycles:2,
  deployment_mode:"NO_DEPLOY",
  completed_effects:[`issue:401`,`build:${"b".repeat(40)}`],
  owner_payload_repair:{grant_key:"c".repeat(64),consumed_event_sha256:"d".repeat(64),build_attempt_id:"e".repeat(64)},
  updated_utc:"2026-09-07T00:00:00.000Z"
});

test("projects an exhausted Owner attempt without changing its lifecycle record",()=>{
  const record=exhaustedOwnerRecord(),before=structuredClone(record);
  const projected=projectHistoricalAttempt(record);
  assert.equal(projected.repair_cycles,2);
  assert.equal(projected.front_id,record.front_id);
  assert.match(projected.historical_sha256,/^[0-9a-f]{64}$/);
  assert.deepEqual(record,before);
});

test("rejects a nonexhausted or incomplete Owner attempt",()=>{
  assert.throws(()=>projectHistoricalAttempt({...exhaustedOwnerRecord(),repair_cycles:1}),/historical Owner attempt/);
  assert.throws(()=>projectHistoricalAttempt({...exhaustedOwnerRecord(),owner_payload_repair:undefined}),/historical Owner attempt/);
});

const validEvidenceInput=()=>({
  item_id:"R9.9",
  task_id:"BRAIN-101-SYNTHETIC-EVIDENCE-01",
  evidence_path:"docs/roadmap/evidence/SYNTHETIC.md",
  canonical_ref:"a".repeat(40),
  evidence_bytes:Buffer.from("Status: PASSED\nPIPELINE=INTENT\nPIPELINE=PLAN\nACK_TASK_ID=BRAIN-101-SYNTHETIC-EVIDENCE-01\n","utf8"),
  required_markers:["Status: PASSED","PIPELINE=INTENT","PIPELINE=PLAN","ACK_TASK_ID=BRAIN-101-SYNTHETIC-EVIDENCE-01"],
  hard_limits:{human_final_authority:true,auto_merge:false,canonical_local_sync:false,live_trading:false,real_money:false}
});

test("accepts pinned passed functional evidence with every required marker",()=>{
  const assertion=verifyFunctionalEvidenceForRebaseline(validEvidenceInput());
  assert.equal(assertion.status,"PASSED");
  assert.match(assertion.evidence_sha256,/^[0-9a-f]{64}$/);
  assert.match(assertion.assertion_sha256,/^[0-9a-f]{64}$/);
});

test("rejects incomplete evidence and constitutional limit drift",()=>{
  const missingAck=validEvidenceInput();missingAck.evidence_bytes=Buffer.from("Status: PASSED\nPIPELINE=INTENT\nPIPELINE=PLAN\n","utf8");
  assert.throws(()=>verifyFunctionalEvidenceForRebaseline(missingAck),/evidence marker missing/);
  const liveTrading=validEvidenceInput();liveTrading.hard_limits.live_trading=true;
  assert.throws(()=>verifyFunctionalEvidenceForRebaseline(liveTrading),/hard limits invalid/);
});
