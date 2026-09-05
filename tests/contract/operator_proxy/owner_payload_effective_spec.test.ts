import test from "node:test";
import assert from "node:assert/strict";
import {createHash} from "node:crypto";
import {mkdtempSync} from "node:fs";
import {tmpdir} from "node:os";
import {join} from "node:path";
import {ExternalEffectBoundary} from "../../../scripts/operator_proxy/external_effect_guard.js";
import {AutonomousFlow} from "../../../scripts/operator_proxy/autonomous_flow.js";
import {reconcileUntilStable} from "../../../scripts/operator_proxy/autonomous_runtime.js";
import {LifecycleStore} from "../../../scripts/operator_proxy/lifecycle_store.js";
import {issueBody} from "../../../scripts/operator_proxy/spec_contract.js";
import {OwnerRepairEffectiveBaseLedger} from "../../../scripts/operator_proxy/owner_repair_effective_base.js";
import {OwnerRepairReceiptLedger} from "../../../scripts/operator_proxy/owner_repair_receipt_ledger.js";
import {ProductionEffects} from "../../../scripts/operator_proxy/production_effects.js";
import type {LifecycleRecord,OwnerAuthorizedPayloadRepairGrant,ProxySpec} from "../../../scripts/operator_proxy/types.js";

const sha40=(character:string)=>character.repeat(40);
const sha64=(character:string)=>character.repeat(64);
const frozen=sha40("a"),failed=sha40("b"),effective=sha40("c"),synchronized=sha40("d"),candidate=sha40("e"),merge=sha40("f"),advanced=sha40("0");
const authorizationId="CESAR-BRAIN-101-OPERATOR-PROXY-20260722-01";
const canonicalBranch="codex/own-capital-sustainable-return";
const digest=(value:string)=>createHash("sha256").update(Buffer.from(value,"utf8")).digest("hex");

const frozenSpec:ProxySpec={
  schema_version:1,authorization_id:authorizationId,repository:"cesarmanuel8102/AI_Vault",roadmap_id:"BRAIN-101",roadmap_version:"1.0.0",roadmap_item_id:"R3.4",expected_base_sha:frozen,
  executor:"codex_control_plane",risk:"LOW",allowed_paths:["docs/"],forbidden_paths:["trading/"],acceptance:["pass"],test_commands:["git diff --check"],deployment_allowed:false,
  objective:"resolve the owner-approved documentation repair",deployment_mode:"NO_DEPLOY",front_id:"BRAIN-101-R3-OWNER-EFFECTIVE-SPEC-01",work_branch:"control-plane/owner-effective-spec",
};

const grant:OwnerAuthorizedPayloadRepairGrant={
  schema_version:1,authorization_id:authorizationId,grant_key:sha64("1"),owner_principal:"cesarmanuel8102",repository:frozenSpec.repository,roadmap_id:frozenSpec.roadmap_id,
  roadmap_item_id:frozenSpec.roadmap_item_id,front_id:frozenSpec.front_id!,issue:701,pr:702,work_branch:frozenSpec.work_branch!,canonical_base_sha:frozen,failed_head_sha:failed,
  eligible_failure_class:"CI_FAILED",max_extra_builds:1,correction_payload:{schema_version:1,requirements:[{requirement_id:"owner-repair",instruction:"repair only the approved documentation payload"}],preserved_invariants:["HUMAN_FINAL_AUTHORITY"]},
  correction_payload_sha256:sha64("2"),owner_comment_id:"5000000702",authorization_body_sha256:sha64("3"),
};

function immutableFiles(revision="E"){
  const roadmap=JSON.stringify({roadmap_id:frozenSpec.roadmap_id,roadmap_version:frozenSpec.roadmap_version,revision});
  const manifest=JSON.stringify({
    roadmap_id:frozenSpec.roadmap_id,roadmap_version:frozenSpec.roadmap_version,repository:frozenSpec.repository,integration_branch:canonicalBranch,approval_status:"HUMAN_ADOPTED",
    r0_status:"CLOSED_HUMAN_ADOPTED",human_final_authority:true,auto_merge:false,canonical_local_sync:false,live_trading_enabled:false,roadmap_path:"docs/roadmap/BRAIN_101_ROADMAP.md",
    roadmap_sha256:digest(roadmap),roadmap_items:{[frozenSpec.roadmap_item_id]:{status:"AUTHORIZED_ACTIVE",dependencies:[]}},
  });
  return {roadmap,manifest};
}

function ownerReceipt(buildAttempt:string,consumedEvent:string,bindingEvent:string){
  return [
    `fix(control-plane): owner payload repair ${frozenSpec.front_id}`,"",
    `OWNER_AUTHORIZATION_ID=${authorizationId}`,
    `OWNER_GRANT_KEY=${grant.grant_key}`,
    `OWNER_BUILD_ATTEMPT_ID=${buildAttempt}`,
    `OWNER_CONSUMED_EVENT_SHA256=${consumedEvent}`,
    `OWNER_FROZEN_BASE_SHA=${frozen}`,
    `OWNER_EFFECTIVE_BASE_SHA=${effective}`,
    `OWNER_EFFECTIVE_BASE_BINDING_SHA256=${bindingEvent}`,
    `OWNER_SYNCHRONIZED_HEAD_SHA=${synchronized}`,
    "BUILDER_BACKEND=opencode_ollama",
    "BUILDER_MODEL=ollama-cloud/kimi-k2.7-code",
    "PROVIDER_SESSION=owner-provider-session",
  ].join("\n");
}

type Fixture={
  root:string;
  effects:ProductionEffects;
  spec:ProxySpec;
  state:LifecycleRecord;
  setTip:(next:string)=>void;
  setIssueBody:(next:string)=>void;
  removeAncestry:(older:string,newer:string)=>void;
  mutations:string[];
};

function fixture(options:{closeoutOnly?:boolean;historicalHashes?:boolean}={}):Fixture {
  const root=mkdtempSync(join(tmpdir(),"owner-effective-spec-"));
  const receipts=new OwnerRepairReceiptLedger(join(root,"owner-repair-receipts"));
  const bases=new OwnerRepairEffectiveBaseLedger(join(root,"owner-repair-receipts"));
  receipts.appendVerified(grant);
  const consumed=receipts.consume(grant.grant_key);
  const dispatched=receipts.markBuildDispatched(grant.grant_key);
  const frozenFiles=immutableFiles("F");
  const historicalSpec=options.historicalHashes?{...frozenSpec,roadmap_sha256:digest(frozenFiles.roadmap),manifest_sha256:digest(frozenFiles.manifest)}:frozenSpec;
  const spec=options.closeoutOnly?{...historicalSpec,closeout_only:true}:historicalSpec;
  let tip=effective,body=`${issueBody(spec).trim()}\n\nOPERATOR_PROXY_PR: ${grant.pr}\n`;
  const effectiveFiles=immutableFiles(),advancedFiles=immutableFiles("M"),mutations:string[]=[];
  const ancestry=new Set([
    `${frozen}:${effective}`,`${frozen}:${failed}`,`${frozen}:${synchronized}`,`${failed}:${synchronized}`,`${effective}:${synchronized}`,
    `${frozen}:${candidate}`,`${failed}:${candidate}`,`${effective}:${candidate}`,`${synchronized}:${candidate}`,`${candidate}:${merge}`,`${effective}:${advanced}`,`${frozen}:${advanced}`,`${merge}:${advanced}`,
  ]);
  const isAncestor=(older:string,newer:string)=>older===newer||ancestry.has(`${older}:${newer}`);
  const binding=bases.bind({
    grant_key:grant.grant_key,front_id:grant.front_id,authorization_id:grant.authorization_id,build_attempt_id:dispatched.build_attempt_id!,frozen_base_sha:frozen,effective_base_sha:effective,
    failed_head_sha:failed,build_dispatched_event_sha256:dispatched.event_sha256,canonical_branch:canonicalBranch,installed_runtime_sha:effective,predecessor_event_sha256:dispatched.event_sha256,
  },{receipts,currentTip:effective,installedRuntimeSha:effective,doctorPassed:true,isAncestor});
  receipts.bindHead(grant.grant_key,candidate);
  const bus:any={
    setMutationGuard:()=>{},branchHead:()=>tip,isAncestor,issueSnapshot:()=>({state:"OPEN",labels:["operator:building"],body}),
    commitMessage:(head:string)=>{assert.equal(head,candidate);return ownerReceipt(dispatched.build_attempt_id!,consumed.event_sha256,binding.event_sha256);},
    fileAt:(path:string,ref:string)=>{const files=ref===frozen?frozenFiles:ref===effective?effectiveFiles:ref===advanced?advancedFiles:undefined;assert.ok(files,`unexpected immutable ref ${ref}`);return path.endsWith("BRAIN_101_ROADMAP.md")?files.roadmap:files.manifest;},
    createGovernedIssue:()=>{mutations.push("createGovernedIssue");throw new Error("unexpected mutation");},replaceIssueBodyExact:()=>{mutations.push("replaceIssueBodyExact");throw new Error("unexpected mutation");},reconcileLabel:()=>{mutations.push("reconcileLabel");throw new Error("unexpected mutation");},commentOnce:()=>{mutations.push("commentOnce");throw new Error("unexpected mutation");},
  };
  const effects=new ProductionEffects(bus,{} as any,root,root,new ExternalEffectBoundary(root,bus,()=>true));
  const state:LifecycleRecord={
    schema_version:1,front_id:grant.front_id,roadmap_item_id:grant.roadmap_item_id,state:"CI_PENDING",issue:grant.issue,pr:grant.pr,base_sha:effective,head_sha:candidate,builder_session:"owner-owner-provider-session",repair_cycles:2,deployment_mode:"NO_DEPLOY",completed_effects:[`issue:${grant.issue}`,`build:${candidate}`],
    owner_payload_repair:{grant_key:grant.grant_key,consumed_event_sha256:consumed.event_sha256,build_attempt_id:dispatched.build_attempt_id!,frozen_base_sha:frozen,failed_head_sha:failed,effective_base_sha:effective,effective_base_binding_sha256:binding.event_sha256,synchronized_head_sha:synchronized},updated_utc:new Date().toISOString(),
  };
  return {root,effects,spec,state,setTip:next=>{tip=next;},setIssueBody:next=>{body=next;},removeAncestry:(older,next)=>{ancestry.delete(`${older}:${next}`);},mutations};
}

test("adopted owner state resolves immutable frozen authority at its persisted effective base",()=>{
  const value=fixture(),result=value.effects.resolveOwnerPayloadExecutionSpec(frozenSpec,value.state),{roadmap,manifest}=immutableFiles();
  assert.deepEqual(result,{...frozenSpec,expected_base_sha:effective,roadmap_sha256:digest(roadmap),manifest_sha256:digest(manifest)});
});

test("ordinary lifecycle state returns its incoming spec without consulting owner ledgers",()=>{
  const value=fixture(),ordinary={...value.state,owner_payload_repair:undefined};
  assert.equal(value.effects.resolveOwnerPayloadExecutionSpec(frozenSpec,ordinary),frozenSpec);
});

test("forged adoption state without a matching receipt chain is denied",()=>{
  const value=fixture(),forged=structuredClone(value.state);
  forged.owner_payload_repair!.grant_key=sha64("9");
  assert.throws(()=>value.effects.resolveOwnerPayloadExecutionSpec(frozenSpec,forged),/owner receipt missing|authority invalid/);
});

test("every persisted owner adoption anchor is required",()=>{
  const changes:Record<string,string>={grant_key:sha64("9"),consumed_event_sha256:sha64("8"),build_attempt_id:sha64("7"),frozen_base_sha:sha40("6"),failed_head_sha:sha40("5"),effective_base_sha:sha40("4"),effective_base_binding_sha256:sha64("3"),synchronized_head_sha:sha40("2")};
  for(const [key,replacement] of Object.entries(changes)){
    const value=fixture(),state=structuredClone(value.state);
    (state.owner_payload_repair as any)[key]=replacement;
    assert.throws(()=>value.effects.resolveOwnerPayloadExecutionSpec(frozenSpec,state),/owner effective|owner payload repair|owner receipt missing/,key);
  }
});

test("candidate provenance requires the complete frozen, effective, synchronized, and candidate lineage",()=>{
  for(const [older,newer] of [[frozen,effective],[effective,synchronized],[synchronized,candidate]] as const){
    const value=fixture();
    value.removeAncestry(older,newer);
    assert.throws(()=>value.effects.resolveOwnerPayloadExecutionSpec(frozenSpec,value.state),/roadmap binding invalid|receipt binding invalid|receipt ancestry invalid|candidate drift/);
  }
});

test("immutable issue authority and incoming execution spec must remain exact",()=>{
  const wrongIssue=fixture();
  wrongIssue.setIssueBody(`${issueBody({...frozenSpec,expected_base_sha:sha40("9")}).trim()}\n\nOPERATOR_PROXY_PR: ${grant.pr}\n`);
  assert.throws(()=>wrongIssue.effects.resolveOwnerPayloadExecutionSpec(frozenSpec,wrongIssue.state),/frozen spec mismatch/);

  const wrongIncoming=fixture();
  assert.throws(()=>wrongIncoming.effects.resolveOwnerPayloadExecutionSpec({...frozenSpec,risk:"MEDIUM"},wrongIncoming.state),/frozen spec mismatch/);
});

test("pre-merge canonical-tip drift fails before any mutation",()=>{
  const value=fixture();
  value.setTip(advanced);
  assert.throws(()=>value.effects.resolveOwnerPayloadExecutionSpec(frozenSpec,value.state),/candidate drift/);
  assert.deepEqual(value.mutations,[]);
});

test("post-merge owner recovery preserves effective authority and requires recorded merge ancestry",()=>{
  const value=fixture(),merged:LifecycleRecord={...value.state,state:"MERGED",head_sha:merge,completed_effects:[...value.state.completed_effects,`merge:${merge}`]};
  const resolved=value.effects.resolveOwnerPayloadExecutionSpec(frozenSpec,merged);
  assert.equal(resolved.expected_base_sha,effective);

  const unproven={...merged,completed_effects:value.state.completed_effects};
  assert.throws(()=>value.effects.resolveOwnerPayloadExecutionSpec(frozenSpec,unproven),/merge evidence invalid/);
});

test("a later post-merge tick rebinds the owner lifecycle to canonical M and reaches the closeout terminal",async()=>{
  const value=fixture({closeoutOnly:true,historicalHashes:true}),store=new LifecycleStore(join(value.root,"lifecycle")),{roadmap,manifest}=immutableFiles("M"),specM={...value.spec,expected_base_sha:advanced,roadmap_sha256:digest(roadmap),manifest_sha256:digest(manifest)};
  const merged:LifecycleRecord={...value.state,state:"MERGED",head_sha:merge,completed_effects:[...value.state.completed_effects,`merge:${merge}`]};
  value.setTip(advanced);
  store.save(merged);
  assert.equal(value.effects.dryRunReconciliation(specM,merged).plan.move,"REBIND_POST_MERGE_BASE");
  const closure=reconcileUntilStable(value.effects,store,specM,merged);
  assert.deepEqual(closure.moves,["REBIND_POST_MERGE_BASE"]);
  assert.equal(closure.status,"FLOW_ENTERABLE");
  assert.equal(closure.state.base_sha,advanced);
  const terminal=await new AutonomousFlow(store,value.effects).step(specM);
  assert.equal(terminal.state,"TERMINAL_COMPLETED");
});
