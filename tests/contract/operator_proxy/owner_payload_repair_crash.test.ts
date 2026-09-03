import test from "node:test";
import assert from "node:assert/strict";
import {OwnerPayloadRepairOrchestrator} from "../../../scripts/operator_proxy/owner_payload_repair_orchestrator.js";

const base="a".repeat(40),failed="b".repeat(40),head="c".repeat(40),grant="d".repeat(64),consumed="e".repeat(64),attempt="f".repeat(64),dispatched="1".repeat(64);

test("restart after BUILD_DISPATCHED redelivers only the persisted logical owner attempt",async()=>{
  let consumedCalls=0,dispatches=0,bound=0;const seen:string[]=[];
  const orchestrator=new OwnerPayloadRepairOrchestrator({
    verify:()=>({grant_key:grant,authorization_id:"AUTH",front_id:"BRAIN-101-R3-CRASH-01",failed_head_sha:failed}),
    receipt:{view:()=>({phase:"BUILD_DISPATCHED" as const,event_sha256:dispatched,predecessor_event_sha256:consumed,build_attempt_id:attempt}),verified:()=>{throw new Error("unexpected")},consumed:()=>{consumedCalls++;throw new Error("unexpected")},dispatched:()=>{throw new Error("unexpected")},headBound:()=>{bound++;}},
    lifecycle:{authorize:()=>{throw new Error("unexpected")},begin:()=>{throw new Error("unexpected")},adopt:state=>({...state,state:"CI_PENDING" as const,head_sha:head,repair_cycles:2})},
    authorizeTransport:receipt=>{assert.equal(receipt.build_attempt_id,attempt);return {build_attempt_id:attempt};},
    dispatch:capability=>{dispatches++;seen.push(capability.build_attempt_id);return {new_head_sha:head,provenance:{authorization_id:"AUTH",grant_key:grant,build_attempt_id:capability.build_attempt_id,consumed_event_sha256:consumed}};},
    verifyLineage:candidate=>candidate.new_head_sha===head,
  });
  const result=await orchestrator.resume({state:"BUILDING",repair_cycles:2,head_sha:failed,base_sha:base});
  assert.equal(result.state,"CI_PENDING");assert.equal(result.repair_cycles,2);assert.equal(consumedCalls,0);assert.equal(dispatches,1);assert.deepEqual(seen,[attempt]);assert.equal(bound,1);
});

test("restart after HEAD_BOUND reconciles the published candidate without another provider delivery",async()=>{
  let recovered=0,dispatches=0;
  const ports:any={
    verify:()=>({grant_key:grant,authorization_id:"AUTH",front_id:"BRAIN-101-R3-CRASH-01",failed_head_sha:failed}),
    receipt:{view:()=>({phase:"HEAD_BOUND",event_sha256:"2".repeat(64),predecessor_event_sha256:dispatched,build_attempt_id:attempt,new_head_sha:head}),verified:()=>{throw new Error("unexpected")},consumed:()=>{throw new Error("unexpected")},dispatched:()=>{throw new Error("unexpected")},headBound:()=>{throw new Error("unexpected")}},
    lifecycle:{authorize:()=>{throw new Error("unexpected")},begin:()=>{throw new Error("unexpected")},adopt:()=>{throw new Error("unexpected")}},
    authorizeTransport:()=>{throw new Error("unexpected")},dispatch:()=>{dispatches++;throw new Error("unexpected")},verifyLineage:()=>false,
    reconcileHeadBound:(state:any,receipt:any)=>{recovered++;assert.equal(receipt.new_head_sha,head);return {...state,state:"CI_PENDING",head_sha:head,repair_cycles:2};},
  };
  const result=await new OwnerPayloadRepairOrchestrator(ports).resume({state:"BUILDING",repair_cycles:2,head_sha:failed,base_sha:base});
  assert.equal(result.state,"CI_PENDING");assert.equal(result.head_sha,head);assert.equal(recovered,1);assert.equal(dispatches,0);
});

test("restart after a remote publish adopts the exact candidate before redelivery",async()=>{
  let discoveries=0,dispatches=0,bound=0;
  const ports:any={
    verify:()=>({grant_key:grant,authorization_id:"AUTH",front_id:"BRAIN-101-R3-CRASH-01",failed_head_sha:failed}),
    receipt:{view:()=>({phase:"BUILD_DISPATCHED",event_sha256:dispatched,predecessor_event_sha256:consumed,build_attempt_id:attempt}),verified:()=>{throw new Error("unexpected")},consumed:()=>{throw new Error("unexpected")},dispatched:()=>{throw new Error("unexpected")},headBound:()=>{bound++;}},
    lifecycle:{authorize:()=>{throw new Error("unexpected")},begin:()=>{throw new Error("unexpected")},adopt:(state:any)=>({...state,state:"CI_PENDING",head_sha:head,repair_cycles:2})},
    findPublishedCandidate:(_state:any,receipt:any)=>{discoveries++;assert.equal(receipt.build_attempt_id,attempt);return {new_head_sha:head,provenance:{authorization_id:"AUTH",grant_key:grant,build_attempt_id:attempt,consumed_event_sha256:consumed}};},
    authorizeTransport:()=>{throw new Error("unexpected")},dispatch:()=>{dispatches++;throw new Error("unexpected")},verifyLineage:(candidate:any)=>candidate.new_head_sha===head,
  };
  const result=await new OwnerPayloadRepairOrchestrator(ports).resume({state:"BUILDING",repair_cycles:2,head_sha:failed,base_sha:base});
  assert.equal(result.state,"CI_PENDING");assert.equal(discoveries,1);assert.equal(dispatches,0);assert.equal(bound,1);
});

test("every durable pre-head boundary preserves the single owner attempt and repair budget",async()=>{
  const cases:[string,any,undefined|"VERIFIED"|"CONSUMED"|"BUILD_DISPATCHED"][]=[
    ["before verified",{state:"BLOCKED",last_error:"CI_FAILED",repair_cycles:2,head_sha:failed,base_sha:base},undefined],
    ["after verified",{state:"BLOCKED",last_error:"CI_FAILED",repair_cycles:2,head_sha:failed,base_sha:base},"VERIFIED"],
    ["after consumed",{state:"BLOCKED",last_error:"CI_FAILED",repair_cycles:2,head_sha:failed,base_sha:base},"CONSUMED"],
    ["after authorization",{state:"OWNER_REPAIR_AUTHORIZED",repair_cycles:2,head_sha:failed,base_sha:base},"CONSUMED"],
    ["after build start",{state:"BUILDING",repair_cycles:2,head_sha:failed,base_sha:base},"CONSUMED"],
    ["after dispatch record",{state:"BUILDING",repair_cycles:2,head_sha:failed,base_sha:base},"BUILD_DISPATCHED"],
  ];
  for(const [name,state,phase] of cases){
    let verified=0,consumedCalls=0,dispatchedCalls=0,deliveries=0,bound=0;
    const consumedEvent={phase:"CONSUMED" as const,event_sha256:consumed,build_attempt_id:attempt};
    const dispatchedEvent={phase:"BUILD_DISPATCHED" as const,event_sha256:dispatched,predecessor_event_sha256:consumed,build_attempt_id:attempt};
    const receipt:any={view:()=>phase===undefined?undefined:phase==="VERIFIED"?{phase:"VERIFIED" as const}:phase==="CONSUMED"?consumedEvent:dispatchedEvent,verified:()=>{verified++;return {phase:"VERIFIED" as const};},consumed:()=>{consumedCalls++;return consumedEvent;},dispatched:()=>{dispatchedCalls++;return dispatchedEvent;},headBound:()=>{bound++;}};
    const result=await new OwnerPayloadRepairOrchestrator({
      verify:()=>({grant_key:grant,authorization_id:"AUTH",front_id:"BRAIN-101-R3-CRASH-01",failed_head_sha:failed}),receipt,
      lifecycle:{authorize:(value:any)=>({...value,state:"OWNER_REPAIR_AUTHORIZED" as const}),begin:(value:any)=>({...value,state:"BUILDING" as const}),adopt:(value:any)=>({...value,state:"CI_PENDING" as const,head_sha:head,repair_cycles:2})},
      authorizeTransport:entry=>{assert.equal(entry.build_attempt_id,attempt,`${name} must retain build attempt`);return {build_attempt_id:attempt};},
      dispatch:entry=>{deliveries++;return {new_head_sha:head,provenance:{authorization_id:"AUTH",grant_key:grant,build_attempt_id:entry.build_attempt_id,consumed_event_sha256:consumed}};},verifyLineage:()=>true,
    }).resume(state);
    assert.equal(result.state,"CI_PENDING",name);assert.equal(result.repair_cycles,2,name);assert.equal(deliveries,1,name);assert.equal(bound,1,name);assert.equal(verified,phase===undefined?1:0,name);assert.equal(consumedCalls,phase===undefined||phase==="VERIFIED"?1:0,name);assert.equal(dispatchedCalls,phase==="BUILD_DISPATCHED"?0:1,name);
  }
});

test("ambiguous remote candidate fails closed before a second provider delivery",async()=>{
  let dispatches=0,bound=0;
  const ports:any={
    verify:()=>({grant_key:grant,authorization_id:"AUTH",front_id:"BRAIN-101-R3-CRASH-01",failed_head_sha:failed}),
    receipt:{view:()=>({phase:"BUILD_DISPATCHED",event_sha256:dispatched,predecessor_event_sha256:consumed,build_attempt_id:attempt}),verified:()=>{throw new Error("unexpected")},consumed:()=>{throw new Error("unexpected")},dispatched:()=>{throw new Error("unexpected")},headBound:()=>{bound++;}},
    lifecycle:{authorize:()=>{throw new Error("unexpected")},begin:()=>{throw new Error("unexpected")},adopt:()=>{throw new Error("unexpected")}},
    findPublishedCandidate:()=>{throw new Error("owner repair remote candidate lineage invalid");},authorizeTransport:()=>{throw new Error("unexpected")},dispatch:()=>{dispatches++;throw new Error("unexpected")},verifyLineage:()=>false,
  };
  await assert.rejects(()=>new OwnerPayloadRepairOrchestrator(ports).resume({state:"BUILDING",repair_cycles:2,head_sha:failed,base_sha:base}),/remote candidate lineage/);
  assert.equal(dispatches,0);assert.equal(bound,0);
});
