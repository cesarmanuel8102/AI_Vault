import test from "node:test";
import assert from "node:assert/strict";
import {OwnerPayloadRepairOrchestrator} from "../../../scripts/operator_proxy/owner_payload_repair_orchestrator.js";

const base = "a".repeat(40), failed = "b".repeat(40), head = "c".repeat(40);

test("owner repair persists every durable boundary before dispatch and adopts only after lineage", async () => {
  const events: string[] = [];
  const orchestrator = new OwnerPayloadRepairOrchestrator({
    verify: () => { events.push("verify"); return {grant_key:"d".repeat(64), authorization_id:"AUTH", front_id:"BRAIN-101-R3-OWNER-01", failed_head_sha:failed}; },
    receipt: {
      view: () => undefined,
      verified: () => { events.push("VERIFIED"); return {phase:"VERIFIED" as const}; },
      consumed: () => { events.push("CONSUMED"); return {phase:"CONSUMED" as const, event_sha256:"e".repeat(64), build_attempt_id:"f".repeat(64)}; },
      dispatched: () => { events.push("BUILD_DISPATCHED"); return {phase:"BUILD_DISPATCHED" as const, event_sha256:"1".repeat(64), predecessor_event_sha256:"e".repeat(64), build_attempt_id:"f".repeat(64)}; },
      headBound: () => { events.push("HEAD_BOUND"); },
    },
    lifecycle: {
      authorize: state => { events.push("OWNER_REPAIR_AUTHORIZED"); return {...state,state:"OWNER_REPAIR_AUTHORIZED" as const}; },
      begin: state => { events.push("BUILDING"); return {...state,state:"BUILDING" as const}; },
      adopt: () => { events.push("CI_PENDING"); return {state:"CI_PENDING", repair_cycles:2, head_sha:head, base_sha:base}; },
    },
    authorizeTransport: receipt => { events.push(`guard:${receipt.phase}`); return {build_attempt_id:"f".repeat(64)}; },
    dispatch: capability => { events.push(`dispatch:${capability.build_attempt_id}`); return {new_head_sha:head, provenance:{authorization_id:"AUTH", grant_key:"d".repeat(64), build_attempt_id:"f".repeat(64), consumed_event_sha256:"e".repeat(64)}}; },
    verifyLineage: candidate => { events.push(`lineage:${candidate.new_head_sha}`); return candidate.new_head_sha === head; },
  });

  const result = await orchestrator.resume({state:"BLOCKED", last_error:"CI_FAILED", repair_cycles:2, head_sha:failed, base_sha:base});
  assert.equal(result.state, "CI_PENDING");
  assert.equal(result.repair_cycles, 2);
  assert.deepEqual(events, ["verify", "VERIFIED", "CONSUMED", "OWNER_REPAIR_AUTHORIZED", "BUILDING", "BUILD_DISPATCHED", "guard:BUILD_DISPATCHED", `dispatch:${"f".repeat(64)}`, `lineage:${head}`, "HEAD_BOUND", "CI_PENDING"]);
});

test("owner repair does not bind a head when lineage rejects the published candidate", async () => {
  let dispatched = 0, bound = 0;
  const orchestrator = new OwnerPayloadRepairOrchestrator({
    verify: () => ({grant_key:"d".repeat(64), authorization_id:"AUTH", front_id:"BRAIN-101-R3-OWNER-01", failed_head_sha:failed}),
    receipt: {view:()=>({phase:"CONSUMED" as const,event_sha256:"e".repeat(64),build_attempt_id:"f".repeat(64)}),verified:()=>{throw new Error("unexpected")},consumed:()=>({phase:"CONSUMED" as const,event_sha256:"e".repeat(64),build_attempt_id:"f".repeat(64)}),dispatched:()=>({phase:"BUILD_DISPATCHED" as const,event_sha256:"1".repeat(64),predecessor_event_sha256:"e".repeat(64),build_attempt_id:"f".repeat(64)}),headBound:()=>{bound++;}},
    lifecycle: {authorize:state=>({...state,state:"OWNER_REPAIR_AUTHORIZED" as const}),begin:state=>({...state,state:"BUILDING" as const}),adopt:()=>({state:"CI_PENDING",repair_cycles:2,head_sha:head,base_sha:base})},
    authorizeTransport:()=>({build_attempt_id:"f".repeat(64)}),
    dispatch:()=>{dispatched++;return {new_head_sha:failed,provenance:{authorization_id:"AUTH",grant_key:"d".repeat(64),build_attempt_id:"f".repeat(64),consumed_event_sha256:"e".repeat(64)}};},
    verifyLineage:()=>false,
  });
  await assert.rejects(() => orchestrator.resume({state:"BLOCKED",last_error:"CI_FAILED",repair_cycles:2,head_sha:failed,base_sha:base}), /lineage/);
  assert.equal(dispatched, 1);
  assert.equal(bound, 0);
});

test("repair-limit exhaustion resumes only through the existing Owner receipt chain",async()=>{
  const orchestrator=new OwnerPayloadRepairOrchestrator({
    verify:()=>({grant_key:"d".repeat(64),authorization_id:"AUTH",front_id:"BRAIN-101-R3-OWNER-01",failed_head_sha:failed}),
    receipt:{view:()=>undefined,verified:()=>({phase:"VERIFIED" as const}),consumed:()=>({phase:"CONSUMED" as const,event_sha256:"e".repeat(64),build_attempt_id:"f".repeat(64)}),dispatched:()=>({phase:"BUILD_DISPATCHED" as const,event_sha256:"1".repeat(64),predecessor_event_sha256:"e".repeat(64),build_attempt_id:"f".repeat(64)}),headBound:()=>{}},
    lifecycle:{authorize:state=>({...state,state:"OWNER_REPAIR_AUTHORIZED" as const}),begin:state=>({...state,state:"BUILDING" as const}),adopt:()=>({state:"CI_PENDING" as const,repair_cycles:2,head_sha:head,base_sha:base})},
    authorizeTransport:()=>({build_attempt_id:"f".repeat(64)}),
    dispatch:()=>({new_head_sha:head,provenance:{authorization_id:"AUTH",grant_key:"d".repeat(64),build_attempt_id:"f".repeat(64),consumed_event_sha256:"e".repeat(64)}}),
    verifyLineage:()=>true,
  });
  const result=await orchestrator.resume({state:"BLOCKED",last_error:"REPAIR_LIMIT_REACHED",repair_cycles:2,head_sha:failed,base_sha:base});
  assert.equal(result.state,"CI_PENDING");
  assert.equal(result.repair_cycles,2);
});

test("owner authorization preflight blocks before any receipt is consumed",async()=>{
  let consumed=0,dispatched=0;
  const orchestrator=new OwnerPayloadRepairOrchestrator({
    verify:()=>({grant_key:"d".repeat(64),authorization_id:"AUTH",front_id:"BRAIN-101-R3-OWNER-01",failed_head_sha:failed}),
    receipt:{view:()=>undefined,verified:()=>({phase:"VERIFIED" as const}),consumed:()=>{consumed++;return {phase:"CONSUMED" as const,event_sha256:"e".repeat(64),build_attempt_id:"f".repeat(64)};},dispatched:()=>{dispatched++;throw new Error("unexpected");},headBound:()=>{throw new Error("unexpected");}},
    lifecycle:{authorize:()=>{throw new Error("unexpected");},begin:()=>{throw new Error("unexpected");},adopt:()=>{throw new Error("unexpected");}},
    authorizeTransport:()=>{throw new Error("unexpected");},dispatch:()=>{throw new Error("unexpected");},verifyLineage:()=>false,
    preflight:()=>{throw new Error("owner authorization reconciliation denied");},
  } as any);
  await assert.rejects(()=>orchestrator.resume({state:"BLOCKED",last_error:"CI_FAILED",repair_cycles:2,head_sha:failed,base_sha:base}),/reconciliation denied/);
  assert.equal(consumed,0);assert.equal(dispatched,0);
});
