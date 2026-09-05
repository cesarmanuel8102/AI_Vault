import test from "node:test";
import assert from "node:assert/strict";
import {mkdtempSync,readFileSync} from "node:fs";
import {tmpdir} from "node:os";
import {join} from "node:path";
import {AutonomousFlow} from "../../../scripts/operator_proxy/autonomous_flow.js";
import {LifecycleStore} from "../../../scripts/operator_proxy/lifecycle_store.js";
import type {LifecycleRecord, ProxySpec} from "../../../scripts/operator_proxy/types.js";

const frozen="a".repeat(40),failed="b".repeat(40),effective="c".repeat(40),head="d".repeat(40);
const spec:ProxySpec={schema_version:1,authorization_id:"CESAR-BRAIN-101-OPERATOR-PROXY-20260722-01",repository:"cesarmanuel8102/AI_Vault",roadmap_id:"BRAIN-101",roadmap_version:"1",roadmap_item_id:"R3.4",expected_base_sha:frozen,executor:"codex_control_plane",risk:"MEDIUM",allowed_paths:["docs/"],forbidden_paths:["trading/"],acceptance:["pass"],test_commands:[],deployment_allowed:false,front_id:"BRAIN-101-R3-EFFECTIVE-FLOW-01",work_branch:"control-plane/effective-flow",deployment_mode:"NO_DEPLOY"};

function effectiveOwner(state:"CI_PENDING"|"BLOCKED"|"BUILDING"="CI_PENDING"):LifecycleRecord {
  return {schema_version:1,front_id:spec.front_id!,roadmap_item_id:spec.roadmap_item_id,state,issue:101,pr:102,base_sha:effective,head_sha:head,builder_session:"owner-builder",repair_cycles:2,deployment_mode:"NO_DEPLOY",completed_effects:["issue:101",`build:${head}`],last_error:state==="BLOCKED"?"CI_FAILED":undefined,owner_payload_repair:{grant_key:"e".repeat(64),consumed_event_sha256:"f".repeat(64),build_attempt_id:"1".repeat(64),frozen_base_sha:frozen,failed_head_sha:failed,effective_base_sha:effective,effective_base_binding_sha256:"2".repeat(64),synchronized_head_sha:"3".repeat(40)},updated_utc:new Date().toISOString()};
}

function legacyOwner():LifecycleRecord {
  return {...effectiveOwner("BUILDING"),base_sha:frozen,owner_payload_repair:{grant_key:"e".repeat(64),consumed_event_sha256:"f".repeat(64),build_attempt_id:"1".repeat(64)} };
}

function store(record:LifecycleRecord){const value=new LifecycleStore(join(mkdtempSync(join(tmpdir(),"owner-effective-flow-")),"state"));value.save(record);return value;}

function effects(overrides:Record<string,unknown>={}){
  return {bindLifecycle:()=>{},ensureIssue:()=>101,ensureBuild:async()=>"PENDING",ci:()=>"PENDING",review:()=>{throw new Error("unexpected");},policy:()=>{throw new Error("unexpected");},ensureMerge:()=>head,ensureInstall:()=>"PASS",ensureRuntimePilot:()=>"PASS",ensureCloseout:async()=>"PASS",discoverNext:()=>{},...overrides} as any;
}

test("effective Owner state resolves its execution spec before lifecycle binding",async()=>{
  const state=effectiveOwner(),saved=store(state);let resolved=0,bound:ProxySpec|undefined;
  const flow=new AutonomousFlow(saved,effects({resolveOwnerPayloadExecutionSpec:(frozenSpec:ProxySpec,record:LifecycleRecord)=>{resolved++;assert.equal(frozenSpec.expected_base_sha,frozen);assert.equal(record.base_sha,effective);return {...frozenSpec,expected_base_sha:effective,roadmap_sha256:"4".repeat(64),manifest_sha256:"5".repeat(64)};},bindLifecycle:(executionSpec:ProxySpec)=>{bound=executionSpec;}}));
  const result=await flow.step(spec);
  assert.equal(result.state,"CI_PENDING");assert.equal(resolved,1);assert.equal(bound?.expected_base_sha,effective);
});

test("effective Owner state fails closed without an execution spec resolver",async()=>{
  await assert.rejects(()=>new AutonomousFlow(store(effectiveOwner()),effects()).step(spec),/effective execution spec resolver unavailable/);
});

test("partial effective Owner anchors cannot bypass the resolver or write lifecycle state",async()=>{
  const partial=effectiveOwner();partial.owner_payload_repair={grant_key:"e".repeat(64),consumed_event_sha256:"f".repeat(64),build_attempt_id:"1".repeat(64),effective_base_sha:"not-a-sha"};
  const saved=store(partial),before=readFileSync(saved.path(spec.front_id!),"utf8");let bound=0,ci=0;
  await assert.rejects(()=>new AutonomousFlow(saved,effects({bindLifecycle:()=>{bound++;},ci:()=>{ci++;return "PENDING";}})).step(spec),/effective execution spec resolver unavailable/);
  assert.equal(readFileSync(saved.path(spec.front_id!),"utf8"),before);assert.equal(bound,0);assert.equal(ci,0);
});

test("only persisted effective Owner state invokes the resolver",async()=>{
  let resolved=0;
  const result=await new AutonomousFlow(store({...legacyOwner(),state:"CI_PENDING"}),effects({resolveOwnerPayloadExecutionSpec:()=>{resolved++;throw new Error("unexpected");}})).step(spec);
  assert.equal(result.state,"CI_PENDING");assert.equal(resolved,0);
});

test("post-adoption BLOCKED and BUILDING states never redispatch Owner transport",async()=>{
  for(const state of [effectiveOwner("BLOCKED"),effectiveOwner("BUILDING")]){
    let dispatches=0;
    const flow=new AutonomousFlow(store(state),effects({resolveOwnerPayloadExecutionSpec:(value:ProxySpec)=>({...value,expected_base_sha:effective}),resumeOwnerPayloadRepair:async()=>{dispatches++;return "PENDING";}}));
    const result=await flow.step(spec);
    assert.equal(result.state,state.state);assert.equal(dispatches,0,state.state);
  }
});
