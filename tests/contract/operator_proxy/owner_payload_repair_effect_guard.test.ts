import test from "node:test";
import assert from "node:assert/strict";
import {mkdtempSync,mkdirSync} from "node:fs";
import {tmpdir} from "node:os";
import {join} from "node:path";
import {ExternalEffectBoundary} from "../../../scripts/operator_proxy/external_effect_guard.js";

const base="a".repeat(40),head="b".repeat(40),attempt="c".repeat(64),consumed="d".repeat(64),grantKey="e".repeat(64),dispatch="f".repeat(64);
const spec:any={authorization_id:"AUTH",repository:"cesarmanuel8102/AI_Vault",roadmap_id:"BRAIN-101",roadmap_item_id:"R3.5",expected_base_sha:base,front_id:"BRAIN-101-R3-OWNER-01",work_branch:"control-plane/owner",allowed_paths:["docs/"],forbidden_paths:["trading/"]};
const state:any={schema_version:1,front_id:spec.front_id,roadmap_item_id:spec.roadmap_item_id,state:"BUILDING",issue:1,pr:2,base_sha:base,head_sha:head,repair_cycles:2,deployment_mode:"NO_DEPLOY",completed_effects:["issue:1",`build:${head}`],owner_payload_repair:{grant_key:grantKey,build_attempt_id:attempt,consumed_event_sha256:consumed},updated_utc:new Date().toISOString()};
const grant:any={authorization_id:"AUTH",grant_key:grantKey,repository:spec.repository,roadmap_id:spec.roadmap_id,roadmap_item_id:spec.roadmap_item_id,front_id:spec.front_id,issue:1,pr:2,work_branch:spec.work_branch,canonical_base_sha:base,failed_head_sha:head,eligible_failure_class:"CI_FAILED",max_extra_builds:1};
const receipt=(phase="BUILD_DISPATCHED"):any=>({phase,grant_key:grantKey,front_id:spec.front_id,authorization_id:"AUTH",failed_head_sha:head,build_attempt_id:attempt,predecessor_event_sha256:consumed,event_sha256:dispatch});
function guard(){const root=mkdtempSync(join(tmpdir(),"owner-guard-"));mkdirSync(join(root,"state"));return new ExternalEffectBoundary(root,{branchHead:()=>base,issuePaused:()=>false,prIdentity:()=>({headRefOid:head})} as any,()=>true);}
test("owner transport capability requires the exact durable BUILD_DISPATCHED receipt and is not forgeable",()=>{
  const context={spec,state,grant,build_attempt_id:attempt,consumed_event_sha256:consumed,build_dispatched_event_sha256:dispatch};const boundary=guard(),cap=boundary.authorizeOwnerPayloadRepairTransport(context,receipt());
  assert.doesNotThrow(()=>boundary.assertOwnerPayloadRepairTransport(cap));
  for(const [name,mutate] of [["consumed",(x:any)=>x.phase="CONSUMED"],["head-bound",(x:any)=>x.phase="HEAD_BOUND"],["event",(x:any)=>x.event_sha256="0".repeat(64)],["predecessor",(x:any)=>x.predecessor_event_sha256="0".repeat(64)],["front",(x:any)=>x.front_id="OTHER"],["grant",(x:any)=>x.grant_key="0".repeat(64)],["authorization",(x:any)=>x.authorization_id="OTHER"],["attempt",(x:any)=>x.build_attempt_id="0".repeat(64)],["failed-head",(x:any)=>x.failed_head_sha="0".repeat(40)]] as const){const value=receipt();mutate(value);assert.throws(()=>guard().authorizeOwnerPayloadRepairTransport(context,value),/denied/,name);}
  assert.throws(()=>boundary.assertOwnerPayloadRepairTransport({...cap}),/denied/);
});
