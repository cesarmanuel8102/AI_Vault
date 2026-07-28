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

test("GitHub mutation families invoke the central guard immediately before mutation",()=>{
  let mutations=0;const bus=new GitHubBus("gh");bus.setMutationGuard(()=>{throw new Error("external effect paused by GitHub label");});(bus as any).call=()=>{mutations++;return "https://github.test/1";};(bus as any).json=(args:string[])=>args[0]==="issue"?{body:"governed"}:args[0]==="run"?[]:{baseRefName:"codex/own-capital-sustainable-return",baseRefOid:base,headRefOid:head,isDraft:true,state:"OPEN",mergeable:"MERGEABLE"};
  const actions=[()=>bus.createGovernedIssue("t","b"),()=>bus.createDraftPr("control-plane/x","codex/own-capital-sustainable-return","t","b"),()=>bus.bindPrToIssue(63,63),()=>bus.comment(63,"x"),()=>bus.prComment(63,"x"),()=>bus.label("issue",63,"operator:building"),()=>bus.merge(63,head,base,"decision")];
  for(const action of actions)assert.throws(action,/paused/);assert.equal(mutations,0);
});

test("coordination requests and receipts remain resumable across pause",()=>{
  const root=mkdtempSync(join(tmpdir(),"effect-coordination-"));let paused=true;const coordinator=new RequestCoordinator(root,()=>{if(paused)throw new Error("paused");});
  assert.throws(()=>coordinator.install(base),/paused/);assert.equal(existsSync(join(root,"requests",`install-${base}.json`)),false);
  paused=false;assert.equal(coordinator.install(base),"LOCAL_PRIVILEGE_REQUIRED");paused=true;writeFileSync(join(root,"receipts",`install-${base}.json`),JSON.stringify({schema_version:1,kind:"install",sha:base,status:"PASS"}));assert.throws(()=>coordinator.install(base),/paused/);paused=false;assert.equal(coordinator.install(base),"PASS");
});
