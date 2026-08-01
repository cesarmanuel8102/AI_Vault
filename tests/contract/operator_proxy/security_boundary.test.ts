import test from "node:test";
import assert from "node:assert/strict";
import {existsSync,mkdtempSync,mkdirSync,rmSync,writeFileSync} from "node:fs";
import {tmpdir} from "node:os";
import {join} from "node:path";
import {EXTERNAL_EFFECT_REGISTRY,ExternalEffectBoundary} from "../../../scripts/operator_proxy/external_effect_guard.js";
import type {LifecycleRecord,ProxySpec} from "../../../scripts/operator_proxy/types.js";
import {GitHubBus} from "../../../scripts/operator_proxy/github_bus.js";
import {RequestCoordinator} from "../../../scripts/operator_proxy/request_coordinator.js";

const base="a".repeat(40),head="b".repeat(40);
const spec:ProxySpec={schema_version:1,authorization_id:"CESAR-BRAIN-101-OPERATOR-PROXY-20260722-01",repository:"cesarmanuel8102/AI_Vault",roadmap_id:"BRAIN-101",roadmap_version:"1.0.0",roadmap_item_id:"R1.1",expected_base_sha:base,executor:"codex_control_plane",risk:"LOW",allowed_paths:["docs/x.md"],forbidden_paths:["trading/"],acceptance:["pass"],test_commands:["git diff --check"],deployment_allowed:false,front_id:"BRAIN-101-R1-SECURITY-BOUNDARY-01",deployment_mode:"NO_DEPLOY"};
const installSpec:ProxySpec={...spec,deployment_mode:"INSTALL_ONLY",install_target:"agent_loop_worker"},artifact="c".repeat(64),config="d".repeat(64);
const installReceipt=()=>({schema_version:2,kind:"install",sha:base,repository:spec.repository,front_id:spec.front_id,roadmap_item_id:spec.roadmap_item_id,install_target:"agent_loop_worker",installer_profile:"agent_loop_v157_transaction",artifact_path:"scripts/agent_loop/local_worker/agent_worker.py",artifact_sha256:artifact,source_sha256:artifact,installed_sha256:artifact,config_sha256_before:config,config_sha256_after:config,task_state:"Disabled",transaction_marker:"V157_DEPLOY_RECOVERY_CONTRACT_PASS",status:"PASS"});
const lifecycle:LifecycleRecord={schema_version:1,front_id:spec.front_id!,roadmap_item_id:spec.roadmap_item_id,state:"REVIEWING",issue:63,pr:63,base_sha:base,head_sha:head,repair_cycles:0,deployment_mode:"NO_DEPLOY",completed_effects:[],updated_utc:new Date().toISOString()};
const expected=["issue_create","issue_modify","label_modify","comment_publish","branch_create","builder_execute","commit_create","push","pr_create","workflow_dispatch","reviewer_execute","decision_persist","findings_publish","repair_request","merge","installation_request","installation_receipt","pilot_request","pilot_receipt","closeout_create","next_item_activate"];

test("external effect registry is canonical and complete",()=>assert.deepEqual([...EXTERNAL_EFFECT_REGISTRY],expected));

test("pause introduced after planning blocks every external effect and resumes idempotently",()=>{
  const root=mkdtempSync(join(tmpdir(),"effect-boundary-"));mkdirSync(join(root,"state"));let paused=false,mutations=0;
  const bus:any={branchHead:()=>base,issuePaused:()=>paused,prIdentity:()=>({headRefOid:head})};
  const boundary=new ExternalEffectBoundary(root,bus,()=>true);boundary.bind(spec,lifecycle);
  for(const effect of EXTERNAL_EFFECT_REGISTRY){paused=true;assert.throws(()=>{boundary.assert(effect,{issue:63,pr:63,expected_head:head});mutations++;},/paused/);paused=false;boundary.assert(effect,{issue:63,pr:63,expected_head:head});mutations++;}
  assert.equal(mutations,EXTERNAL_EFFECT_REGISTRY.length);assert.deepEqual(lifecycle.completed_effects,[]);
  writeFileSync(join(root,"state","PAUSE"),"");assert.throws(()=>boundary.assert("comment_publish",{issue:63}),/paused locally/);rmSync(join(root,"state","PAUSE"));boundary.assert("comment_publish",{issue:63});
});

test("lost lease, changed base or head, and blocked lifecycle fail closed",()=>{
  const root=mkdtempSync(join(tmpdir(),"effect-boundary-"));mkdirSync(join(root,"state"));let lease=true,currentBase=base,currentHead=head;
  const bus:any={branchHead:()=>currentBase,issuePaused:()=>false,prIdentity:()=>({headRefOid:currentHead})};const boundary=new ExternalEffectBoundary(root,bus,()=>lease);boundary.bind(spec,lifecycle);
  lease=false;assert.throws(()=>boundary.assert("push",{issue:63,pr:63,expected_head:head}),/lease lost/);lease=true;currentBase="c".repeat(40);assert.throws(()=>boundary.assert("push",{issue:63}),/base changed/);currentBase=base;currentHead="d".repeat(40);assert.throws(()=>boundary.assert("merge",{issue:63,pr:63,expected_head:head}),/head changed/);currentHead=head;boundary.bind(spec,{...lifecycle,state:"BLOCKED"});assert.throws(()=>boundary.assert("comment_publish",{issue:63}),/lifecycle state/);
});

test("post-merge boundary distinguishes immediate merge effects from rebound closeout",()=>{
  const root=mkdtempSync(join(tmpdir(),"effect-postmerge-"));mkdirSync(join(root,"state"));const merge="c".repeat(40),tip="d".repeat(40);let currentBase=merge;
  const bus:any={branchHead:()=>currentBase,issuePaused:()=>false,prIdentity:()=>({headRefOid:head})};const boundary=new ExternalEffectBoundary(root,bus,()=>true);
  boundary.bind(spec,lifecycle);boundary.bindPostMerge(merge);boundary.assert("comment_publish",{issue:63});
  const reboundSpec={...spec,expected_base_sha:tip},rebound:LifecycleRecord={...lifecycle,state:"CLOSEOUT_PENDING",base_sha:tip,head_sha:merge,completed_effects:[`merge:${merge}`]};currentBase=tip;boundary.bind(reboundSpec,rebound);boundary.assert("closeout_create");
  boundary.bind(reboundSpec,{...rebound,base_sha:"e".repeat(40)});assert.throws(()=>boundary.assert("closeout_create"),/post-merge binding changed/);
  boundary.bind(reboundSpec,rebound);currentBase="e".repeat(40);assert.throws(()=>boundary.assert("closeout_create"),/base changed/);
});

test("blocked CI recovery permits only the exact push then Issue update",()=>{
  const root=mkdtempSync(join(tmpdir(),"effect-boundary-"));mkdirSync(join(root,"state"));const nextBase="c".repeat(40),nextHead="d".repeat(40);let currentBase=nextBase,currentHead=head,paused=false;
  const nextSpec={...spec,expected_base_sha:nextBase};const blocked:LifecycleRecord={...lifecycle,state:"BLOCKED",last_error:"CI_FAILED",base_sha:base,head_sha:head,builder_session:"builder-one",completed_effects:["issue:63",`build:${head}`]};
  const bus:any={branchHead:()=>currentBase,issuePaused:()=>paused,prIdentity:()=>({headRefOid:currentHead})};const boundary=new ExternalEffectBoundary(root,bus,()=>true);boundary.bind(nextSpec,blocked);
  assert.throws(()=>boundary.assert("push",{issue:63,pr:63,expected_head:nextHead}),/lifecycle state/);
  boundary.beginBlockedCiRecovery(nextSpec,blocked);boundary.assert("push",{issue:63,pr:63,expected_head:nextHead});
  for(const effect of EXTERNAL_EFFECT_REGISTRY.filter(x=>x!=="push"))assert.throws(()=>boundary.assert(effect,{issue:63,pr:63,expected_head:nextHead}),/lifecycle state/);
  currentHead=nextHead;boundary.bindBlockedCiRecoveryHead(nextHead);assert.throws(()=>boundary.assert("issue_modify",{issue:63,pr:63}),/lifecycle state/);assert.throws(()=>boundary.assert("issue_modify",{issue:63,pr:63,expected_head:"e".repeat(40)}),/lifecycle state/);boundary.assert("issue_modify",{issue:63,pr:63,expected_head:nextHead});
  assert.throws(()=>boundary.assert("push",{issue:63,pr:63,expected_head:nextHead}),/lifecycle state/);paused=true;assert.throws(()=>boundary.assert("issue_modify",{issue:63,pr:63,expected_head:nextHead}),/identity changed/);paused=false;currentBase="e".repeat(40);assert.throws(()=>boundary.assert("issue_modify",{issue:63,pr:63,expected_head:nextHead}),/base changed/);
  boundary.endBlockedCiRecovery();currentBase=nextBase;assert.throws(()=>boundary.assert("issue_modify",{issue:63,pr:63,expected_head:nextHead}),/lifecycle state/);
});

test("blocked Agent Loop recovery permits only an exact observed descendant chain head",()=>{
  const root=mkdtempSync(join(tmpdir(),"effect-chain-boundary-"));mkdirSync(join(root,"state"));const nextBase="c".repeat(40),observed="d".repeat(40),nextHead="e".repeat(40);let currentHead=observed,ancestor=true;
  const nextSpec={...spec,executor:"agent_loop" as const,expected_base_sha:nextBase};const blocked:LifecycleRecord={...lifecycle,state:"BLOCKED",last_error:"CI_FAILED",base_sha:base,head_sha:head,builder_session:"builder-one",completed_effects:["issue:63",`build:${head}`]};
  const bus:any={branchHead:()=>nextBase,issuePaused:()=>false,prIdentity:()=>({headRefOid:currentHead}),isAncestor:(older:string,newer:string)=>ancestor&&older===head&&newer===observed};const boundary=new ExternalEffectBoundary(root,bus,()=>true);boundary.beginBlockedCiRecovery(nextSpec,blocked);
  assert.throws(()=>boundary.assert("push",{issue:63,pr:63,expected_head:nextHead}),/lifecycle state/);
  assert.throws(()=>boundary.assert("push",{issue:63,pr:63,expected_head:nextHead,observed_head:"f".repeat(40)}),/lifecycle state/);
  ancestor=false;assert.throws(()=>boundary.assert("push",{issue:63,pr:63,expected_head:nextHead,observed_head:observed}),/lifecycle state/);ancestor=true;
  boundary.assert("push",{issue:63,pr:63,expected_head:nextHead,observed_head:observed});
  boundary.beginBlockedCiRecovery({...nextSpec,executor:"codex_control_plane"},blocked);assert.throws(()=>boundary.assert("push",{issue:63,pr:63,expected_head:nextHead,observed_head:observed}),/lifecycle state/);
});

test("negated-risk escalation recovery permits only exact branch sync and Issue update",()=>{
  const root=mkdtempSync(join(tmpdir(),"effect-negated-risk-"));mkdirSync(join(root,"state"));const nextBase="c".repeat(40),nextHead="d".repeat(40);let currentBase=nextBase,currentHead=head;
  const nextSpec={...spec,expected_base_sha:nextBase,risk:"MEDIUM" as const,acceptance:["Keep canonical local sync disabled"]};const escalated:LifecycleRecord={...lifecycle,state:"ESCALATED",last_error:"OWNER_AUTHORITY_REQUIRED",base_sha:base,head_sha:head,builder_session:"builder-one",reviewer_session:"reviewer-one",decision_id:"11111111-1111-4111-8111-111111111111",completed_effects:["issue:63",`build:${head}`]};
  const bus:any={branchHead:()=>currentBase,issuePaused:()=>false,prIdentity:()=>({headRefOid:currentHead})};const boundary=new ExternalEffectBoundary(root,bus,()=>true);boundary.bind(nextSpec,escalated);
  assert.throws(()=>boundary.assert("push",{issue:63,pr:63,expected_head:nextHead}),/lifecycle state/);boundary.beginNegatedRiskRecovery(nextSpec,escalated);boundary.assert("push",{issue:63,pr:63,expected_head:nextHead});
  currentHead=nextHead;boundary.bindBlockedCiRecoveryHead(nextHead);boundary.assert("issue_modify",{issue:63,pr:63,expected_head:nextHead});
  for(const effect of EXTERNAL_EFFECT_REGISTRY.filter(x=>x!=="issue_modify"))assert.throws(()=>boundary.assert(effect,{issue:63,pr:63,expected_head:nextHead}),/lifecycle state/);
  boundary.endBlockedCiRecovery();assert.throws(()=>boundary.assert("issue_modify",{issue:63,pr:63,expected_head:nextHead}),/lifecycle state/);
});

test("privileged install resume permits only the exact receipt under the persisted escalation",()=>{
  const root=mkdtempSync(join(tmpdir(),"effect-install-resume-"));mkdirSync(join(root,"state"));const merge="c".repeat(40);let currentBase=base,paused=false;
  const escalated:LifecycleRecord={...lifecycle,state:"ESCALATED",last_error:"LOCAL_PRIVILEGE_REQUIRED",deployment_mode:"INSTALL_ONLY",head_sha:merge,builder_session:"builder-one",reviewer_session:"reviewer-one",decision_id:"11111111-1111-4111-8111-111111111111",completed_effects:["issue:63",`build:${head}`,`merge:${merge}`]};
  const bus:any={branchHead:()=>currentBase,issuePaused:()=>paused,prIdentity:()=>({headRefOid:head})};const boundary=new ExternalEffectBoundary(root,bus,()=>true);
  assert.throws(()=>boundary.assert("installation_receipt"),/context missing/);boundary.beginPrivilegedInstallResume(installSpec,escalated);boundary.assert("installation_receipt");
  for(const effect of EXTERNAL_EFFECT_REGISTRY.filter(x=>x!=="installation_receipt"))assert.throws(()=>boundary.assert(effect),/lifecycle state/);
  paused=true;assert.throws(()=>boundary.assert("installation_receipt"),/paused by GitHub/);paused=false;currentBase="d".repeat(40);assert.throws(()=>boundary.assert("installation_receipt"),/base changed/);currentBase=base;
  boundary.endPrivilegedInstallResume();assert.throws(()=>boundary.assert("installation_receipt"),/lifecycle state/);
  for(const mutation of [{last_error:"OTHER"},{head_sha:undefined},{completed_effects:[]},{completed_effects:["issue:63",`merge:${merge}`]},{completed_effects:["issue:63",`build:${head}`,"base-sync:"+"d".repeat(40)]},{deployment_mode:"INSTALL_AND_RUNTIME_PILOT"},{issue:undefined},{pr:undefined},{builder_session:undefined},{reviewer_session:undefined},{decision_id:undefined}])assert.throws(()=>boundary.beginPrivilegedInstallResume(installSpec,{...escalated,...mutation} as LifecycleRecord),/boundary denied/);
});

test("GitHub mutation families invoke the central guard immediately before mutation",()=>{
  let mutations=0;const bus=new GitHubBus("gh");bus.setMutationGuard(()=>{throw new Error("external effect paused by GitHub label");});(bus as any).call=()=>{mutations++;return "https://github.test/1";};(bus as any).json=(args:string[])=>args[0]==="issue"?{body:"governed"}:args[0]==="run"?[]:{baseRefName:"codex/own-capital-sustainable-return",baseRefOid:base,headRefOid:head,isDraft:true,state:"OPEN",mergeable:"MERGEABLE"};
  const actions=[()=>bus.createGovernedIssue("t","b"),()=>bus.createDraftPr("control-plane/x","codex/own-capital-sustainable-return","t","b"),()=>bus.bindPrToIssue(63,63),()=>bus.comment(63,"x"),()=>bus.prComment(63,"x"),()=>bus.label("issue",63,"operator:building"),()=>bus.merge(63,head,base,"decision")];
  for(const action of actions)assert.throws(action,/paused/);assert.equal(mutations,0);
});

test("coordination requests and receipts remain resumable across pause",()=>{
  const root=mkdtempSync(join(tmpdir(),"effect-coordination-"));let paused=true;const coordinator=new RequestCoordinator(root,()=>{if(paused)throw new Error("paused");});
  const name=`install-${spec.front_id}-${base}.json`;assert.throws(()=>coordinator.install(installSpec,base,artifact),/paused/);assert.equal(existsSync(join(root,"requests",name)),false);
  paused=false;assert.equal(coordinator.install(installSpec,base,artifact),"LOCAL_PRIVILEGE_REQUIRED");paused=true;writeFileSync(join(root,"receipts",name),JSON.stringify(installReceipt()));assert.throws(()=>coordinator.install(installSpec,base,artifact),/paused/);paused=false;assert.equal(coordinator.install(installSpec,base,artifact),"PASS");
});
