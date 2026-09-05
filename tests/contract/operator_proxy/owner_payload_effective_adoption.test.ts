import test from "node:test";
import assert from "node:assert/strict";
import {mkdtempSync} from "node:fs";
import {tmpdir} from "node:os";
import {join} from "node:path";
import {LifecycleStore} from "../../../scripts/operator_proxy/lifecycle_store.js";
import {verifyOwnerPayloadRepairAdoption} from "../../../scripts/operator_proxy/lineage.js";
import {OwnerRepairReceiptLedger} from "../../../scripts/operator_proxy/owner_repair_receipt_ledger.js";
import {OwnerRepairEffectiveBaseLedger} from "../../../scripts/operator_proxy/owner_repair_effective_base.js";
import type {LifecycleRecord, OwnerAuthorizedPayloadRepairGrant, ProxySpec} from "../../../scripts/operator_proxy/types.js";

const sha40=(character:string)=>character.repeat(40);
const sha64=(character:string)=>character.repeat(64);
const frozen=sha40("a"),failed=sha40("b"),effective=sha40("c"),synchronized=sha40("d"),next=sha40("e");
const grantKey=sha64("f"),attempt=sha64("1");

const spec:ProxySpec={schema_version:1,authorization_id:"CESAR-BRAIN-101-OPERATOR-PROXY-20260722-01",repository:"cesarmanuel8102/AI_Vault",roadmap_id:"BRAIN-101",roadmap_version:"1",roadmap_item_id:"R3.4",expected_base_sha:frozen,executor:"codex_control_plane",risk:"MEDIUM",allowed_paths:["docs/"],forbidden_paths:["trading/"],acceptance:["pass"],test_commands:[],deployment_allowed:false,front_id:"BRAIN-101-R3-EFFECTIVE-ADOPTION-01",work_branch:"control-plane/effective-adoption",deployment_mode:"NO_DEPLOY"};
const grant:OwnerAuthorizedPayloadRepairGrant={schema_version:1,authorization_id:spec.authorization_id,grant_key:grantKey,owner_principal:"cesarmanuel8102",repository:spec.repository,roadmap_id:spec.roadmap_id,roadmap_item_id:spec.roadmap_item_id,front_id:spec.front_id!,issue:101,pr:102,work_branch:spec.work_branch!,canonical_base_sha:frozen,failed_head_sha:failed,eligible_failure_class:"CI_FAILED",max_extra_builds:1,correction_payload:{schema_version:1,requirements:[{requirement_id:"repair",instruction:"repair"}],preserved_invariants:["HUMAN_FINAL_AUTHORITY"]},correction_payload_sha256:sha64("2"),owner_comment_id:"5000000001",authorization_body_sha256:sha64("3")};

function observed(baseRefOid:string){
  return {head:next,identity:{headRefOid:next,baseRefOid,baseRefName:"codex/own-capital-sustainable-return",headRefName:grant.work_branch,headRepository:{nameWithOwner:grant.repository},author:{login:grant.owner_principal},isCrossRepository:false,isDraft:true,state:"OPEN",files:[{path:"docs/repair.md"}]}} as any;
}

function baseSync(bindingEvent:string){
  return {frozen_base_sha:frozen,effective_base_sha:effective,binding_event_sha256:bindingEvent,synchronized_head_sha:synchronized};
}

test("effective-base owner adoption keeps the frozen grant/spec anchor while requiring exact sync provenance",()=>{
  const binding:any={schema_version:1,grant_key:grant.grant_key,front_id:grant.front_id,authorization_id:grant.authorization_id,build_attempt_id:attempt,frozen_base_sha:frozen,effective_base_sha:effective,failed_head_sha:failed,build_dispatched_event_sha256:sha64("4"),predecessor_event_sha256:sha64("4"),canonical_branch:"codex/own-capital-sustainable-return",installed_runtime_sha:effective,event_sha256:sha64("5"),created_at:"2026-09-04T00:00:00.000Z"};
  const ancestors=new Set([`${frozen}:${effective}`,`${failed}:${synchronized}`,`${effective}:${synchronized}`,`${synchronized}:${next}`,`${frozen}:${next}`,`${failed}:${next}`,`${effective}:${next}`]);
  const context:any={spec,grant,new_head_sha:next,remote_branch_head:next,pr:observed(effective),provenance:{authorization_id:grant.authorization_id,grant_key:grant.grant_key,build_attempt_id:attempt,consumed_event_sha256:sha64("6")},build_attempt_id:attempt,consumed_event_sha256:sha64("6"),effective_base_binding:binding,effective_base_provenance:baseSync(binding.event_sha256),isAncestor:(older:string,newer:string)=>older===newer||ancestors.has(`${older}:${newer}`)};
  assert.equal(verifyOwnerPayloadRepairAdoption(context),true);
  assert.equal(verifyOwnerPayloadRepairAdoption({...context,pr:observed(frozen)}),false,"bound PR must target the durable effective base");
  assert.equal(verifyOwnerPayloadRepairAdoption({...context,effective_base_provenance:{...context.effective_base_provenance,synchronized_head_sha:next}}),false,"sync provenance must be exact");
  assert.equal(verifyOwnerPayloadRepairAdoption({...context,isAncestor:(older:string,newer:string)=>older===newer||older!==effective&&ancestors.has(`${older}:${newer}`)}),false,"effective base must be an ancestor of the synchronized head");
});

function lifecycle(build_attempt_id:string,consumed_event_sha256:string):LifecycleRecord {
  return {schema_version:1,front_id:grant.front_id,roadmap_item_id:grant.roadmap_item_id,state:"BUILDING",issue:grant.issue,pr:grant.pr,base_sha:frozen,head_sha:failed,builder_session:"builder:owner",repair_cycles:2,deployment_mode:"NO_DEPLOY",completed_effects:[`issue:${grant.issue}`,`build:${failed}`],owner_payload_repair:{grant_key:grant.grant_key,consumed_event_sha256,build_attempt_id},updated_utc:new Date().toISOString()};
}

function boundFixture(headBound:boolean){
  const root=mkdtempSync(join(tmpdir(),"owner-effective-adoption-"));
  const receipts=new OwnerRepairReceiptLedger(join(root,"receipts"));
  receipts.appendVerified(grant);const consumed=receipts.consume(grant.grant_key),dispatched=receipts.markBuildDispatched(grant.grant_key);
  const effectiveBases=new OwnerRepairEffectiveBaseLedger(join(root,"effective-bases"));
  const binding=effectiveBases.bind({grant_key:grant.grant_key,front_id:grant.front_id,authorization_id:grant.authorization_id,build_attempt_id:consumed.build_attempt_id!,frozen_base_sha:frozen,effective_base_sha:effective,failed_head_sha:failed,build_dispatched_event_sha256:dispatched.event_sha256,predecessor_event_sha256:dispatched.event_sha256,canonical_branch:"codex/own-capital-sustainable-return",installed_runtime_sha:effective},{receipts,currentTip:effective,installedRuntimeSha:effective,doctorPassed:true,isAncestor:(older:string,newer:string)=>older===newer||older===frozen&&newer===effective});
  if(headBound)receipts.bindHead(grant.grant_key,next);
  const store=new LifecycleStore(join(root,"state")),record=lifecycle(consumed.build_attempt_id!,consumed.event_sha256);
  store.save(record);
  return {store,record,receipts,effectiveBases,binding};
}

test("lifecycle advances the base only after exact binding and HEAD_BOUND receipt validation",()=>{
  const fixture=boundFixture(true);
  const adopted=(fixture.store as any).adoptOwnerPayloadRepairCandidate(fixture.record,{pr:grant.pr,head_sha:next,builder_session:"builder:owner:next",grant_key:grant.grant_key,build_attempt_id:fixture.record.owner_payload_repair!.build_attempt_id,consumed_event_sha256:fixture.record.owner_payload_repair!.consumed_event_sha256,effective_base_binding:fixture.binding,synchronized_head_sha:synchronized},{effectiveBases:fixture.effectiveBases,receipts:fixture.receipts});
  assert.equal(adopted.state,"CI_PENDING");assert.equal(adopted.base_sha,effective);assert.equal(adopted.repair_cycles,2);
  assert.deepEqual(adopted.owner_payload_repair,{grant_key:grant.grant_key,consumed_event_sha256:fixture.record.owner_payload_repair!.consumed_event_sha256,build_attempt_id:fixture.record.owner_payload_repair!.build_attempt_id,frozen_base_sha:frozen,failed_head_sha:failed,effective_base_sha:effective,effective_base_binding_sha256:fixture.binding.event_sha256,synchronized_head_sha:synchronized});
  assert.equal(fixture.store.load(grant.front_id)!.base_sha,effective);
});

test("lifecycle refuses unbound pre-HEAD_BOUND base adoption without persisting a base override",()=>{
  const fixture=boundFixture(false);
  assert.throws(()=> (fixture.store as any).adoptOwnerPayloadRepairCandidate(fixture.record,{pr:grant.pr,head_sha:next,builder_session:"builder:owner:next",grant_key:grant.grant_key,build_attempt_id:fixture.record.owner_payload_repair!.build_attempt_id,consumed_event_sha256:fixture.record.owner_payload_repair!.consumed_event_sha256,effective_base_binding:fixture.binding,synchronized_head_sha:synchronized},{effectiveBases:fixture.effectiveBases,receipts:fixture.receipts}),/owner payload repair candidate adoption denied/);
  const persisted=fixture.store.load(grant.front_id)!;
  assert.equal(persisted.base_sha,frozen);assert.equal(persisted.head_sha,failed);assert.equal(persisted.owner_payload_repair!.effective_base_sha,undefined);
});

test("adopted Owner anchors cannot re-enter an ordinary repair or lower the repair budget",()=>{
  const fixture=boundFixture(true);
  const adopted=(fixture.store as any).adoptOwnerPayloadRepairCandidate(fixture.record,{pr:grant.pr,head_sha:next,builder_session:"builder:owner:next",grant_key:grant.grant_key,build_attempt_id:fixture.record.owner_payload_repair!.build_attempt_id,consumed_event_sha256:fixture.record.owner_payload_repair!.consumed_event_sha256,effective_base_binding:fixture.binding,synchronized_head_sha:synchronized},{effectiveBases:fixture.effectiveBases,receipts:fixture.receipts});
  const policyBlocked={...adopted,state:"BLOCKED" as const,last_error:"POLICY_BLOCK",reviewer_session:"reviewer:owner",decision_id:"11111111-1111-4111-8111-111111111111"};
  assert.throws(()=>fixture.store.resumeUnconsummatedRepair(policyBlocked,0),/denied/);
  const reviewing={...adopted,state:"REVIEWING" as const};
  assert.throws(()=>fixture.store.advance(reviewing,"REPAIRING",{repair_cycles:3}),/owner payload repair effective base/);
  assert.throws(()=>fixture.store.advance({...adopted,state:"REPAIRING" as const},"BUILDING"),/owner payload repair effective base/);
});
