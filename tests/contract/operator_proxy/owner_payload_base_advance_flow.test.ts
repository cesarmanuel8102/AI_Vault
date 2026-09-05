import test from "node:test";
import assert from "node:assert/strict";
import {createHash} from "node:crypto";
import {mkdtempSync,readFileSync} from "node:fs";
import {tmpdir} from "node:os";
import {join} from "node:path";
import type {CandidateExecutionAdapter} from "../../../scripts/operator_proxy/candidate_execution.js";
import {newLifecycle} from "../../../scripts/operator_proxy/autonomous_flow.js";
import {parseCorrectionPayloadV1} from "../../../scripts/operator_proxy/correction_payload.js";
import {ExternalEffectBoundary} from "../../../scripts/operator_proxy/external_effect_guard.js";
import {parseOwnerPayloadRepairCommitReceipt} from "../../../scripts/operator_proxy/governed_builder.js";
import {LifecycleStore} from "../../../scripts/operator_proxy/lifecycle_store.js";
import {OwnerRepairEffectiveBaseLedger} from "../../../scripts/operator_proxy/owner_repair_effective_base.js";
import {OwnerRepairReceiptLedger} from "../../../scripts/operator_proxy/owner_repair_receipt_ledger.js";
import {ProductionEffects} from "../../../scripts/operator_proxy/production_effects.js";
import type {OwnerAuthorizedPayloadRepairGrant, ProxySpec} from "../../../scripts/operator_proxy/types.js";

const sha40=(character:string)=>character.repeat(40);
const sha64=(character:string)=>character.repeat(64);
const frozen=sha40("a"),failed=sha40("b"),effective=sha40("c"),synchronized=sha40("d"),candidate=sha40("e"),advanced=sha40("f"),foreign=sha40("0");
const authorizationId="CESAR-BRAIN-101-OPERATOR-PROXY-20260722-01";
const correctionPayload={schema_version:1 as const,requirements:[{requirement_id:"owner-repair",instruction:"repair only the approved docs payload"}],preserved_invariants:["HUMAN_FINAL_AUTHORITY"]};

export const spec:ProxySpec={
  schema_version:1,authorization_id:authorizationId,repository:"cesarmanuel8102/AI_Vault",roadmap_id:"BRAIN-101",roadmap_version:"1",roadmap_item_id:"R3.4",expected_base_sha:frozen,
  executor:"codex_control_plane",risk:"LOW",allowed_paths:["docs/"],forbidden_paths:["trading/"],acceptance:["pass"],test_commands:["git diff --check"],deployment_allowed:false,
  deployment_mode:"NO_DEPLOY",front_id:"BRAIN-101-R3-OWNER-BASE-ADVANCE-01",work_branch:"control-plane/owner-base-advance",
};

export const grant:OwnerAuthorizedPayloadRepairGrant={
  schema_version:1,authorization_id:authorizationId,grant_key:sha64("1"),owner_principal:"cesarmanuel8102",repository:spec.repository,roadmap_id:spec.roadmap_id,
  roadmap_item_id:spec.roadmap_item_id,front_id:spec.front_id!,issue:701,pr:702,work_branch:spec.work_branch!,canonical_base_sha:frozen,failed_head_sha:failed,
  eligible_failure_class:"CI_FAILED",max_extra_builds:1,correction_payload:correctionPayload,
  correction_payload_sha256:parseCorrectionPayloadV1(correctionPayload).sha256,owner_comment_id:"5000000702",authorization_body_sha256:sha64("3"),
};

function sha(value:string){return createHash("sha256").update(value,"utf8").digest("hex");}

function candidateReceipt(buildAttempt:string,consumed:string,binding:string,effectiveBase=effective){
  return [
    `fix(control-plane): owner payload repair ${spec.front_id}`,"",
    `OWNER_AUTHORIZATION_ID=${authorizationId}`,
    `OWNER_GRANT_KEY=${grant.grant_key}`,
    `OWNER_BUILD_ATTEMPT_ID=${buildAttempt}`,
    `OWNER_CONSUMED_EVENT_SHA256=${consumed}`,
    `OWNER_FROZEN_BASE_SHA=${frozen}`,
    `OWNER_EFFECTIVE_BASE_SHA=${effectiveBase}`,
    `OWNER_EFFECTIVE_BASE_BINDING_SHA256=${binding}`,
    `OWNER_SYNCHRONIZED_HEAD_SHA=${synchronized}`,
    "BUILDER_BACKEND=opencode_ollama",
    "BUILDER_MODEL=ollama-cloud/kimi-k2.7-code",
    "PROVIDER_SESSION=owner-provider-session",
  ].join("\n");
}

function manifest(){
  const roadmap=JSON.stringify({roadmap_id:spec.roadmap_id,roadmap_version:spec.roadmap_version});
  const value={
    roadmap_id:spec.roadmap_id,roadmap_version:spec.roadmap_version,repository:spec.repository,integration_branch:"codex/own-capital-sustainable-return",approval_status:"HUMAN_ADOPTED",
    r0_status:"CLOSED_HUMAN_ADOPTED",human_final_authority:true,auto_merge:false,canonical_local_sync:false,live_trading_enabled:false,roadmap_path:"docs/roadmap/BRAIN_101_ROADMAP.md",
    roadmap_sha256:sha(roadmap),roadmap_items:{[spec.roadmap_item_id]:{status:"AUTHORIZED_ACTIVE",dependencies:[]}},
  };
  return {roadmap,manifest:JSON.stringify(value)};
}

export type Fixture={
  root:string; store:LifecycleStore; receipts:OwnerRepairReceiptLedger; bases:OwnerRepairEffectiveBaseLedger; effects:ProductionEffects; state:any;
  calls:{runtime:string[];sync:number;publication:number;provider:string[]}; setTip:(value:string)=>void; setRuntime:(value:string)=>void; setRemote:(value:string)=>void;
};

export function fixture(options:{runtime?:string;tip?:string;remoteCandidate?:boolean;advanceAfterBind?:boolean}={}):Fixture {
  const root=mkdtempSync(join(tmpdir(),"owner-base-advance-flow-"));
  const store=new LifecycleStore(join(root,"lifecycle"));
  const receipts=new OwnerRepairReceiptLedger(join(root,"owner-repair-receipts"));
  const bases=new OwnerRepairEffectiveBaseLedger(join(root,"owner-repair-receipts"));
  const verified=receipts.appendVerified(grant),consumed=receipts.consume(grant.grant_key);
  let state:any={...newLifecycle(spec),state:"BLOCKED",last_error:"CI_FAILED",issue:grant.issue,pr:grant.pr,base_sha:frozen,head_sha:failed,builder_session:"ordinary-builder",repair_cycles:2,completed_effects:[`issue:${grant.issue}`,`build:${failed}`]};
  store.save(state);
  state=store.authorizeOwnerPayloadRepair(state,receipts,consumed);
  state=store.beginOwnerPayloadRepairBuild(state,consumed);
  const dispatched=receipts.markBuildDispatched(grant.grant_key);
  assert.equal(verified.phase,"VERIFIED");
  assert.equal(dispatched.phase,"BUILD_DISPATCHED");
  assert.equal(state.base_sha,frozen);

  let tip=options.tip??effective,runtime=options.runtime??effective,remote=options.remoteCandidate?candidate:failed;
  const calls={runtime:[] as string[],sync:0,publication:0,provider:[] as string[]};
  const {roadmap,manifest:manifestText}=manifest();
  let identity:any={
    author:{login:grant.owner_principal},baseRefName:"codex/own-capital-sustainable-return",baseRefOid:options.remoteCandidate?effective:frozen,
    headRefName:spec.work_branch,headRefOid:remote,headRepository:{nameWithOwner:spec.repository},isCrossRepository:false,isDraft:true,state:"OPEN",files:[{path:"docs/repair.md"}],
  };
  const messages=new Map<string,string>();
  const bus:any={
    setMutationGuard:()=>{},branchHead:()=>tip,remoteBranchHead:()=>remote,isAncestor:(older:string,newer:string)=>older===newer||new Set([`${frozen}:${effective}`,`${frozen}:${failed}`,`${frozen}:${synchronized}`,`${failed}:${synchronized}`,`${effective}:${synchronized}`,`${synchronized}:${candidate}`,`${effective}:${candidate}`,`${failed}:${candidate}`,`${frozen}:${candidate}`,`${candidate}:${advanced}`]).has(`${older}:${newer}`),
    issuePaused:()=>false,issueComments:()=>{throw new Error("fresh owner grant observation is forbidden during ledger recovery");},prIdentity:()=>identity,commitMessage:(head:string)=>messages.get(head)??"",fileAt:(path:string)=>path.endsWith("BRAIN_101_ROADMAP.md")?roadmap:manifestText,
  };
  const boundary=new ExternalEffectBoundary(root,bus,()=>true);
  const effects=new ProductionEffects(bus,{} as any,join(process.cwd(),"..",".."),root,boundary);
  effects.bindLifecycle(spec,state);
  effects.ownerRepairRuntimeSha=(observedTip:string)=>{calls.runtime.push(observedTip);return runtime;};
  const builder:any=effects.builder;
  builder.isOwnerPayloadRepairBaseSync=()=>false;
  builder.synchronizeOwnerPayloadRepairBase=(_spec:ProxySpec,_grant:OwnerAuthorizedPayloadRepairGrant,_capability:any,assertCapability:()=>void)=>{
    calls.sync++;
    if(options.advanceAfterBind){tip=advanced;assertCapability();}
    assertCapability();
    remote=synchronized;
    identity={...identity,baseRefOid:effective,headRefOid:synchronized};
    return {synchronized_head_sha:synchronized};
  };
  builder.ownerPayloadRepairPublicationAdapter=(_spec:ProxySpec,_grant:OwnerAuthorizedPayloadRepairGrant,_capability:any,assertCapability:()=>void,resume:any):CandidateExecutionAdapter=>{
    calls.publication++;
    assert.equal(resume.binding.frozen_base_sha,frozen);
    assert.equal(resume.binding.effective_base_sha,effective);
    assert.equal(resume.synchronized_head_sha,synchronized);
    return {
      prepare:()=>({worktree:"C:/owner-base-advance",starting_head:synchronized}),
      validateExistingDraftPr:()=>assert.deepEqual(identity,{...identity,baseRefOid:effective,headRefOid:synchronized}),
      invokeProvider:async request=>{
        assertCapability();
        calls.provider.push(request.idempotency_key??"");
        return {executor_role:"codex_control_plane",builder_backend:"opencode_ollama",builder_model:"ollama-cloud/kimi-k2.7-code",builder_session:"owner-provider-session",provider_session:"owner-provider-session",base_sha:synchronized,head_sha:candidate,branch:spec.work_branch!};
      },
      changedPaths:()=>["docs/repair.md"],runDeclaredTests:()=>{},diffCheck:()=>{},commit:(_worktree,receipt)=>{messages.set(candidate,receipt);return candidate;},
      push:(_worktree,head)=>{
        assertCapability();
        assert.equal(head,candidate);
        remote=candidate;
        identity={...identity,headRefOid:candidate};
      },
      remoteHead:()=>remote,
      existingDraftPr:()=>({number:grant.pr,repository:spec.repository,issue:grant.issue,work_branch:spec.work_branch!,base_sha:effective,head_sha:candidate,is_draft:true,is_open:true,same_repository:true,non_fork:true,author_login:grant.owner_principal,base_ref_name:"codex/own-capital-sustainable-return",base_ref_oid:effective,head_ref_name:spec.work_branch!,head_ref_oid:candidate,changed_paths:["docs/repair.md"]}),
      createDraftPr:()=>{throw new Error("owner repair must retain its existing Draft PR");},bindPrToIssue:()=>{},
    };
  };
  return {root,store,receipts,bases,effects,state,calls,setTip:value=>{tip=value;},setRuntime:value=>{runtime=value;},setRemote:value=>{remote=value;identity={...identity,headRefOid:value,baseRefOid:effective};}};
}

test("owner base advance binds a descendant runtime, publishes one exact attempt, and adopts the effective base",async()=>{
  const value=fixture(),before=structuredClone(grant);
  const originalReceiptChain=readFileSync(join(value.receipts.root,"owner-repair-receipts.jsonl"),"utf8").trim().split(/\r?\n/).map(line=>JSON.parse(line));
  const result=await value.effects.resumeOwnerPayloadRepair(spec,value.state,value.store);
  if(result==="PENDING")assert.fail("owner payload repair unexpectedly remained pending");
  const receipt=value.receipts.deriveReceiptView(grant.grant_key),binding=value.bases.load(grant.grant_key),persisted=value.store.load(spec.front_id!)!;
  assert.equal(value.calls.sync,1);
  assert.equal(value.calls.publication,1);
  assert.deepEqual(value.calls.provider,[receipt.build_attempt_id]);
  assert.ok(value.calls.runtime.length>0);
  assert.ok(value.calls.runtime.every(value=>value===effective));
  assert.equal(receipt.phase,"HEAD_BOUND");
  assert.equal(receipt.new_head_sha,candidate);
  const receiptEvents=readFileSync(join(value.receipts.root,"owner-repair-receipts.jsonl"),"utf8").trim().split(/\r?\n/).map(line=>JSON.parse(line));
  assert.deepEqual(receiptEvents.slice(0,3),originalReceiptChain);
  assert.equal(binding!.frozen_base_sha,frozen);
  assert.equal(binding!.effective_base_sha,effective);
  assert.equal(result.base_sha,effective);
  assert.equal(persisted.base_sha,effective);
  assert.equal(persisted.repair_cycles,2);
  assert.deepEqual(value.receipts.findGrantSnapshot({front_id:grant.front_id,issue:grant.issue,pr:grant.pr,failed_head_sha:failed}),before);
  assert.deepEqual(before,grant);
  const parsed=parseOwnerPayloadRepairCommitReceipt((value as any).effects.bus?.commitMessage?.(candidate)??"",spec.front_id!);
  assert.deepEqual(parsed.provenance,{authorization_id:authorizationId,grant_key:grant.grant_key,build_attempt_id:receipt.build_attempt_id,consumed_event_sha256:value.state.owner_payload_repair.consumed_event_sha256});
  assert.deepEqual(parsed.effective_base,{frozen_base_sha:frozen,effective_base_sha:effective,binding_event_sha256:binding!.event_sha256,synchronized_head_sha:synchronized});
  assert.deepEqual((value.effects as any).ownerPayloadRepairBuilderReceipt(result,candidate,spec.front_id),{model:"ollama-cloud/kimi-k2.7-code",headCommit:candidate,status:"VERIFIED"});
  const message=(value.effects as any).bus.commitMessage(candidate);
  (value.effects as any).bus.commitMessage=()=>message.replace(`OWNER_EFFECTIVE_BASE_SHA=${effective}`,`OWNER_EFFECTIVE_BASE_SHA=${frozen}`);
  assert.throws(()=> (value.effects as any).ownerPayloadRepairBuilderReceipt(result,candidate,spec.front_id),/effective receipt binding invalid/);
  (value.effects as any).bus.commitMessage=()=>message.replace(`OWNER_CONSUMED_EVENT_SHA256=${value.state.owner_payload_repair.consumed_event_sha256}`,`OWNER_CONSUMED_EVENT_SHA256=${sha64("9")}`);
  assert.throws(()=> (value.effects as any).ownerPayloadRepairBuilderReceipt(result,candidate,spec.front_id),/receipt binding invalid/);
});

test("owner base advance rejects wrong runtime or a non-descendant tip before durable bind",async()=>{
  const runtimeMismatch=fixture({runtime:frozen});
  await assert.rejects(runtimeMismatch.effects.resumeOwnerPayloadRepair(spec,runtimeMismatch.state,runtimeMismatch.store),/runtime mismatch|effective base/i);
  assert.equal(runtimeMismatch.bases.load(grant.grant_key),undefined);
  assert.equal(runtimeMismatch.receipts.deriveReceiptView(grant.grant_key).phase,"BUILD_DISPATCHED");
  assert.deepEqual(runtimeMismatch.calls.provider,[]);

  const wrongTip=fixture({tip:foreign,runtime:foreign});
  await assert.rejects(wrongTip.effects.resumeOwnerPayloadRepair(spec,wrongTip.state,wrongTip.store),/ancestry|effective base/i);
  assert.equal(wrongTip.bases.load(grant.grant_key),undefined);
  assert.equal(wrongTip.receipts.deriveReceiptView(grant.grant_key).phase,"BUILD_DISPATCHED");
  assert.deepEqual(wrongTip.calls.provider,[]);
});

test("owner base advance rejects a canonical tip change after durable bind before provider dispatch",async()=>{
  const value=fixture({advanceAfterBind:true});
  await assert.rejects(value.effects.resumeOwnerPayloadRepair(spec,value.state,value.store),/owner payload repair|external effect|effective base/i);
  assert.equal(value.bases.load(grant.grant_key)!.effective_base_sha,effective);
  assert.equal(value.receipts.deriveReceiptView(grant.grant_key).phase,"BUILD_DISPATCHED");
  assert.deepEqual(value.calls.provider,[]);
});

test("owner base advance recovers an already remote candidate without provider redelivery",async()=>{
  const value=fixture({remoteCandidate:true});
  const dispatched=value.receipts.deriveReceiptView(grant.grant_key) as any;
  const binding=value.bases.bind({grant_key:grant.grant_key,front_id:grant.front_id,authorization_id:grant.authorization_id,build_attempt_id:dispatched.build_attempt_id,frozen_base_sha:frozen,effective_base_sha:effective,failed_head_sha:failed,build_dispatched_event_sha256:dispatched.event_sha256,canonical_branch:"codex/own-capital-sustainable-return",installed_runtime_sha:effective,predecessor_event_sha256:dispatched.event_sha256},{receipts:value.receipts,currentTip:effective,installedRuntimeSha:effective,doctorPassed:true,isAncestor:(older,newer)=>older===newer||older===frozen&&newer===effective});
  const receipt=candidateReceipt(dispatched.build_attempt_id,dispatched.predecessor_event_sha256,binding.event_sha256);
  assert.deepEqual(parseOwnerPayloadRepairCommitReceipt(receipt,spec.front_id!).effective_base,{frozen_base_sha:frozen,effective_base_sha:effective,binding_event_sha256:binding.event_sha256,synchronized_head_sha:synchronized});
  // The remote bus holds the exact parsed receipt before resume, so recovery must not redeliver the provider.
  (value.effects as any).bus.commitMessage=()=>receipt;
  const result=await value.effects.resumeOwnerPayloadRepair(spec,value.state,value.store);
  if(result==="PENDING")assert.fail("remote owner payload repair candidate unexpectedly remained pending");
  assert.equal(result.state,"CI_PENDING");
  assert.equal(result.base_sha,effective);
  assert.equal(value.receipts.deriveReceiptView(grant.grant_key).phase,"HEAD_BOUND");
  assert.equal(value.calls.sync,0);
  assert.equal(value.calls.publication,0);
  assert.deepEqual(value.calls.provider,[]);
});
