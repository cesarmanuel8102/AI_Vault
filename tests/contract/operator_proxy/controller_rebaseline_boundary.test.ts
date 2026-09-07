import test from "node:test";
import assert from "node:assert/strict";
import {projectHistoricalAttempt,verifyFunctionalEvidenceForRebaseline,planControllerRebaseline} from "../../../scripts/operator_proxy/controller_rebaseline.js";
import type {ControllerRebaselinePlanInputV1,ControllerSupersessionReceiptV1,LifecycleRecord} from "../../../scripts/operator_proxy/types.js";

const sha40=(char:string)=>char.repeat(40);
const sha64=(char:string)=>char.repeat(64);
const historical=()=>projectHistoricalAttempt({schema_version:1,front_id:"BRAIN-101-CONTROLLER-SYNTHETIC-01",roadmap_item_id:"R9.9",state:"BUILDING",issue:401,pr:402,base_sha:sha40("a"),head_sha:sha40("b"),builder_session:"historical",repair_cycles:2,deployment_mode:"NO_DEPLOY",completed_effects:[],owner_payload_repair:{grant_key:sha64("c"),consumed_event_sha256:sha64("d"),build_attempt_id:sha64("e")},updated_utc:"2026-09-07T00:00:00.000Z"} satisfies LifecycleRecord);
const evidence=()=>verifyFunctionalEvidenceForRebaseline({item_id:"R9.9",task_id:"BRAIN-101-SYNTHETIC-EVIDENCE-01",evidence_path:"docs/roadmap/evidence/SYNTHETIC.md",canonical_ref:sha40("a"),evidence_bytes:Buffer.from("Status: PASSED\nACK_TASK_ID=BRAIN-101-SYNTHETIC-EVIDENCE-01\n","utf8"),required_markers:["Status: PASSED","ACK_TASK_ID=BRAIN-101-SYNTHETIC-EVIDENCE-01"],hard_limits:{human_final_authority:true,auto_merge:false,canonical_local_sync:false,live_trading:false,real_money:false}});
const input=():ControllerRebaselinePlanInputV1=>({canonical:{repository:"cesarmanuel8102/AI_Vault",roadmap_item_id:"R9.9",canonical_base_sha:sha40("a"),manifest_sha256:sha64("f"),roadmap_sha256:sha64("0"),item_status:"AUTHORIZED_ACTIVE",hard_limits:{human_final_authority:true,auto_merge:false,canonical_local_sync:false,live_trading:false,real_money:false}},historical:historical(),evidence:evidence(),receipts:[]});
const receiptFor=(value:ControllerRebaselinePlanInputV1,plan:{supersession_key?:string}):ControllerSupersessionReceiptV1=>({schema_version:1,controller:"CODEX_GOVERNED_CONTROLLER",supersession_key:plan.supersession_key!,sequence:0,previous_event_sha256:null,repository:value.canonical.repository,roadmap_item_id:value.canonical.roadmap_item_id,canonical_base_sha:value.canonical.canonical_base_sha,manifest_sha256:value.canonical.manifest_sha256,roadmap_sha256:value.canonical.roadmap_sha256,historical_attempt_sha256:value.historical.historical_sha256,front_id:value.historical.front_id,failed_head_sha:value.historical.failed_head_sha,grant_key:value.historical.grant_key,consumed_event_sha256:value.historical.consumed_event_sha256,build_attempt_id:value.historical.build_attempt_id,functional_evidence_ref:value.evidence.canonical_ref,functional_evidence_path:value.evidence.evidence_path,functional_evidence_sha256:value.evidence.evidence_sha256,functional_evidence_assertion_sha256:value.evidence.assertion_sha256,hard_limits:value.canonical.hard_limits,persistent_agent_loop_enabled:false,created_utc:"2026-09-07T00:00:00.000Z",event_sha256:sha64("9")});

test("permits closeout only after an exact supersession receipt",()=>{
  const value=input(),required=planControllerRebaseline(value);
  assert.equal(required.status,"REBASELINE_REQUIRED");
  value.receipts=[receiptFor(value,required)];
  assert.equal(planControllerRebaseline(value).status,"CLOSEOUT_ALLOWED");
});

test("blocks base, manifest, roadmap, hard-limit, and duplicate-receipt drift",()=>{
  const value=input(),required=planControllerRebaseline(value);value.receipts=[receiptFor(value,required)];
  for(const patch of [{canonical:{...value.canonical,canonical_base_sha:sha40("1")}},{canonical:{...value.canonical,manifest_sha256:sha64("1")}},{canonical:{...value.canonical,roadmap_sha256:sha64("1")}},{canonical:{...value.canonical,hard_limits:{...value.canonical.hard_limits,live_trading:true}}},{receipts:[...value.receipts,...value.receipts]}])assert.equal(planControllerRebaseline({...value,...patch} as any).status,"BLOCKED");
});

test("planner has no production-effect surface",()=>{
  const value=input(),effects={calls:[] as string[]};
  planControllerRebaseline({...value,effects} as any);
  assert.deepEqual(effects.calls,[]);
});
