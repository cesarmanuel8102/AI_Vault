import test from "node:test";
import assert from "node:assert/strict";
import {resolveFrozenOwnerPayloadRepairSpec} from "../../../scripts/operator_proxy/production_effects.js";
import {issueBody} from "../../../scripts/operator_proxy/spec_contract.js";

test("dispatched Owner lifecycle keeps its frozen spec only with receipt-chain proof",()=>{
  const frozen="a".repeat(40),tip="b".repeat(40),failed="c".repeat(40);
  const spec:any={schema_version:1,authorization_id:"CESAR-BRAIN-101-OPERATOR-PROXY-20260722-01",repository:"cesarmanuel8102/AI_Vault",roadmap_id:"BRAIN-101",roadmap_version:"1.0.0",roadmap_item_id:"R9.1",expected_base_sha:frozen,executor:"codex_control_plane",risk:"LOW",allowed_paths:["docs/"],forbidden_paths:["financial_autonomy/"],acceptance:["pass"],test_commands:["git diff --check"],deployment_allowed:false,front_id:"OWNER-RESUME-SPEC-01",work_branch:"control-plane/owner-resume-spec",objective:"closeout",deployment_mode:"NO_DEPLOY",closeout_only:true};
  const state:any={schema_version:1,front_id:spec.front_id,roadmap_item_id:spec.roadmap_item_id,state:"BUILDING",issue:7,pr:8,base_sha:frozen,head_sha:failed,builder_session:"prior-builder",repair_cycles:2,completed_effects:["issue:7",`build:${failed}`],owner_payload_repair:{grant_key:"d".repeat(64),consumed_event_sha256:"e".repeat(64),build_attempt_id:"f".repeat(64)}};
  const body=issueBody(spec)+"\nOPERATOR_PROXY_PR: 8\n",current={...spec,expected_base_sha:tip};
  const resolve=resolveFrozenOwnerPayloadRepairSpec as any;
  assert.deepEqual(resolve(current,state,body,()=>true,()=>true),spec);
  assert.equal(resolve(current,state,body,()=>true),undefined);
  assert.equal(resolve(current,state,body,()=>true,()=>false),undefined);
  assert.equal(resolve(current,state,body,()=>false,()=>true),undefined);
  assert.equal(resolve(current,{...state,repair_cycles:1},body,()=>true,()=>true),undefined);
  assert.equal(resolve(current,{...state,state:"CI_PENDING"},body,()=>true,()=>true),undefined);
});
