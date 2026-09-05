import test from "node:test";
import assert from "node:assert/strict";
import {appendFileSync,mkdtempSync} from "node:fs";
import {tmpdir} from "node:os";
import {join} from "node:path";
import {AutonomousFlow,newLifecycle} from "../../../scripts/operator_proxy/autonomous_flow.js";
import {LifecycleStore} from "../../../scripts/operator_proxy/lifecycle_store.js";
import {OwnerPayloadRepairOrchestrator} from "../../../scripts/operator_proxy/owner_payload_repair_orchestrator.js";
import {ProductionEffects,verifyOwnerRepairInstalledRuntime} from "../../../scripts/operator_proxy/production_effects.js";
import {OwnerRepairReceiptLedger} from "../../../scripts/operator_proxy/owner_repair_receipt_ledger.js";
import type {OwnerAuthorizedPayloadRepairGrant,ProxySpec} from "../../../scripts/operator_proxy/types.js";

const base="a".repeat(40),failed="b".repeat(40),head="c".repeat(40),attempt="d".repeat(64),consumed="e".repeat(64),grant="f".repeat(64);
test("Owner effective base rejects an uninstalled development checkout before runtime effects",()=>{
  const root=mkdtempSync(join(tmpdir(),"owner-runtime-denied-"));
  assert.throws(()=>verifyOwnerRepairInstalledRuntime(root,process.cwd(),base),/installed runtime/);
});
const spec:ProxySpec={schema_version:1,authorization_id:"CESAR-BRAIN-101-OPERATOR-PROXY-20260722-01",repository:"cesarmanuel8102/AI_Vault",roadmap_id:"BRAIN-101",roadmap_version:"1",roadmap_item_id:"R3.4",expected_base_sha:base,executor:"codex_control_plane",risk:"LOW",allowed_paths:["docs/"],forbidden_paths:["scripts/operator_proxy/"],acceptance:["pass"],test_commands:["git diff --check"],deployment_allowed:false,deployment_mode:"NO_DEPLOY",front_id:"BRAIN-101-R3-OWNER-FLOW-01",work_branch:"control-plane/owner-flow"};

test("exhausted CI failure reaches ordinary CI through one owner attempt without ordinary repair semantics",async()=>{
  const store=new LifecycleStore(mkdtempSync(join(tmpdir(),"owner-flow-")));const blocked:any={...newLifecycle(spec),state:"BLOCKED",last_error:"CI_FAILED",issue:248,pr:249,head_sha:failed,builder_session:"ordinary-builder",repair_cycles:2,completed_effects:["issue:248",`build:${failed}`]};store.save(blocked);
  const events:string[]=[];let ordinaryBuilds=0,rawComments=0,ordinaryRepairEvents=0;
  const resume=async (_spec:ProxySpec,state:any)=>new OwnerPayloadRepairOrchestrator({
    verify:()=>({grant_key:grant,authorization_id:spec.authorization_id,front_id:spec.front_id!,failed_head_sha:failed}),
    receipt:{view:()=>undefined,verified:()=>({phase:"VERIFIED" as const}),consumed:()=>({phase:"CONSUMED" as const,event_sha256:consumed,build_attempt_id:attempt}),dispatched:()=>({phase:"BUILD_DISPATCHED" as const,event_sha256:"1".repeat(64),predecessor_event_sha256:consumed,build_attempt_id:attempt}),headBound:()=>events.push("HEAD_BOUND")},
    lifecycle:{authorize:value=>({...value,state:"OWNER_REPAIR_AUTHORIZED" as const}),begin:value=>({...value,state:"BUILDING" as const}),adopt:value=>({...value,state:"CI_PENDING" as const,head_sha:head,repair_cycles:2})},
    authorizeTransport:value=>{events.push(value.phase);return {build_attempt_id:attempt};},
    dispatch:value=>{events.push(`provider:${value.build_attempt_id}`);return {new_head_sha:head,provenance:{authorization_id:spec.authorization_id,grant_key:grant,build_attempt_id:attempt,consumed_event_sha256:consumed}};},
    verifyLineage:value=>{events.push(`lineage:${value.new_head_sha}`);return true;},
  }).resume(state);
  const effects:any={bindLifecycle:()=>{},ensureIssue:()=>{throw new Error("unexpected")},ensureBuild:()=>{ordinaryBuilds++;throw new Error("unexpected")},resumeOwnerPayloadRepair:resume,ci:()=>"PENDING",review:()=>{throw new Error("unexpected")},policy:()=>{throw new Error("unexpected")},ensureMerge:()=>{throw new Error("unexpected")},ensureInstall:()=>"PASS",ensureRuntimePilot:()=>"PASS",ensureCloseout:async()=>"PASS",discoverNext:()=>{}};
  const result=await new AutonomousFlow(store,effects).step(spec);
  assert.equal(result.state,"CI_PENDING");assert.equal(result.repair_cycles,2);assert.equal(ordinaryBuilds,0);assert.equal(rawComments,0);assert.equal(ordinaryRepairEvents,0);assert.deepEqual(events,["BUILD_DISPATCHED",`provider:${attempt}`,`lineage:${head}`,"HEAD_BOUND"]);
});

test("exhausted CI failure without an Owner envelope remains terminal blocked",async()=>{
  const root=mkdtempSync(join(tmpdir(),"owner-flow-no-grant-")),store=new LifecycleStore(join(root,"lifecycle"));
  const blocked:any={...newLifecycle(spec),state:"BLOCKED",last_error:"CI_FAILED",issue:248,pr:249,head_sha:failed,builder_session:"ordinary-builder",repair_cycles:2,completed_effects:["issue:248",`build:${failed}`]};store.save(blocked);
  const bus:any={setMutationGuard:()=>{},issueComments:()=>[]};
  const boundary:any={assert:()=>{},bind:()=>{}};
  const effects=new ProductionEffects(bus,{} as any,join(process.cwd(),"..",".."),root,boundary);
  assert.equal(await effects.resumeOwnerPayloadRepair(spec,blocked,store),"PENDING");
  const persisted=store.load(spec.front_id!)!;
  assert.equal(persisted.state,"BLOCKED");assert.equal(persisted.repair_cycles,2);assert.equal(persisted.head_sha,failed);assert.equal(persisted.owner_payload_repair,undefined);
});

test("repair-limit exhausted state reaches the dedicated Owner path without a normal repair",async()=>{
  const store=new LifecycleStore(mkdtempSync(join(tmpdir(),"owner-flow-exhausted-")));
  const blocked:any={...newLifecycle(spec),state:"BLOCKED",last_error:"REPAIR_LIMIT_REACHED",issue:248,pr:249,head_sha:failed,builder_session:"ordinary-builder",repair_cycles:2,completed_effects:["issue:248",`build:${failed}`]};
  store.save(blocked);
  let ownerResumes=0,ordinaryBuilds=0;
  const effects:any={bindLifecycle:()=>{},ensureIssue:()=>{throw new Error("unexpected")},ensureBuild:()=>{ordinaryBuilds++;throw new Error("unexpected")},resumeOwnerPayloadRepair:async (_spec:ProxySpec,state:any)=>{ownerResumes++;assert.equal(state.front_id,blocked.front_id);assert.equal(state.last_error,"REPAIR_LIMIT_REACHED");assert.equal(state.repair_cycles,2);return {...state,state:"OWNER_REPAIR_AUTHORIZED" as const};},ci:()=>"PENDING",review:()=>{throw new Error("unexpected")},policy:()=>{throw new Error("unexpected")},ensureMerge:()=>{throw new Error("unexpected")},ensureInstall:()=>"PASS",ensureRuntimePilot:()=>"PASS",ensureCloseout:async()=>"PASS",discoverNext:()=>{}};
  const result=await new AutonomousFlow(store,effects).step(spec);
  assert.equal(result.state,"OWNER_REPAIR_AUTHORIZED");
  assert.equal(result.repair_cycles,2);
  assert.equal(ownerResumes,1);
  assert.equal(ordinaryBuilds,0);
});

test("a persisted Owner grant resumes repair-limit exhaustion only after two ordinary repairs",async()=>{
  const root=mkdtempSync(join(tmpdir(),"owner-flow-recovered-limit-")),store=new LifecycleStore(join(root,"lifecycle"));
  const blocked:any={...newLifecycle(spec),state:"BLOCKED",last_error:"REPAIR_LIMIT_REACHED",issue:248,pr:249,head_sha:failed,builder_session:"ordinary-builder",repair_cycles:2,completed_effects:["issue:248",`build:${failed}`]};
  store.save(blocked);
  appendFileSync(join(store.root,"events.jsonl"),`${JSON.stringify({event:"lifecycle_repair_build_replaced",issue:248,pr:249,decision_id:"repair-one"})}\n${JSON.stringify({event:"lifecycle_repair_build_replaced",issue:248,pr:249,decision_id:"repair-two"})}\n`);
  const ownerGrant:OwnerAuthorizedPayloadRepairGrant={schema_version:1,authorization_id:spec.authorization_id,grant_key:grant,owner_principal:"cesarmanuel8102",repository:spec.repository,roadmap_id:spec.roadmap_id,roadmap_item_id:spec.roadmap_item_id,front_id:spec.front_id!,issue:248,pr:249,work_branch:spec.work_branch!,canonical_base_sha:base,failed_head_sha:failed,eligible_failure_class:"CI_FAILED",max_extra_builds:1,correction_payload:{schema_version:1,requirements:[{requirement_id:"repair",instruction:"apply the approved correction"}],preserved_invariants:["HUMAN_FINAL_AUTHORITY"]},correction_payload_sha256:"1".repeat(64),owner_comment_id:"5000000001",authorization_body_sha256:"2".repeat(64)};
  const receipts=new OwnerRepairReceiptLedger(join(root,"owner-repair-receipts"));receipts.appendVerified(ownerGrant);receipts.consume(ownerGrant.grant_key);
  const effects:any=new ProductionEffects({setMutationGuard:()=>{}} as any,{} as any,join(process.cwd(),"..",".."),root,{assert:()=>{},bind:()=>{}} as any);
  effects.assertOwnerPayloadRepairAuthorizationPlan=()=>{throw new Error("recovered grant reached preflight");};
  await assert.rejects(effects.resumeOwnerPayloadRepair(spec,blocked,store),/recovered grant reached preflight/);
});
