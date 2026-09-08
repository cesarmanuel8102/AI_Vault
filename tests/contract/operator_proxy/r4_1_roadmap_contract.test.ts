import test from "node:test";
import assert from "node:assert/strict";
import {existsSync, readFileSync} from "node:fs";
import {resolve} from "node:path";

const ROOT=resolve(process.cwd(),"..","..");
const MANIFEST="docs/roadmap/BRAIN_101_MANIFEST.json";
const R34_CLOSEOUT="docs/roadmap/evidence/BRAIN_101_R3_4_AGENT_V2_COGNITIVE_PIPELINE_E2E_CLOSEOUT.json";
const R41_BASELINE="docs/roadmap/evidence/BRAIN_101_R4_1_MODULAR_MONOLITH_BASELINE.md";
const readJson=(path:string)=>JSON.parse(readFileSync(resolve(ROOT,path),"utf8"));
const activeItems=(manifest:any)=>Object.entries(manifest.roadmap_items).filter(([,item]:any)=>item.status==="AUTHORIZED_ACTIVE");
const readText=(path:string)=>readFileSync(resolve(ROOT,path),"utf8");
const recommendation=(text:string)=>{
  const matches=[...text.matchAll(/```json\r?\n([\s\S]*?)\r?\n```/g)];
  assert.equal(matches.length,1,"baseline must contain exactly one recommendation JSON object");
  const match=matches[0];
  assert.ok(match,"baseline must contain one recommendation JSON object");
  return JSON.parse(match[1]);
};

test("R3.4 controller closeout remains immutable after downstream roadmap transitions",()=>{
  const manifest=readJson(MANIFEST);
  assert.equal(manifest.roadmap_items["R3.4"].status,"CLOSED_RUNTIME_VERIFIED");
  assert.ok(existsSync(resolve(ROOT,R34_CLOSEOUT)));
});

test("R4.1 contract is no-deploy and protects prohibited boundaries",()=>{
  const item=readJson(MANIFEST).roadmap_items["R4.1"];
  assert.deepEqual(item.dependencies,["R3.4"]);
  assert.equal(item.automation.executor,"codex_control_plane");
  assert.equal(item.automation.deployment_mode,"NO_DEPLOY");
  assert.deepEqual(item.automation.allowed_paths,[R41_BASELINE,"tests/contract/operator_proxy/r4_1_roadmap_contract.test.ts"]);
  for(const path of [".env","tmp_agent/brain_v9/trading/","financial_autonomy/","scripts/"])
    assert.ok(item.automation.forbidden_paths.includes(path));
});

test("R4.1 baseline evidence selects one eligible no-deploy modular-monolith candidate",()=>{
  assert.ok(existsSync(resolve(ROOT,R41_BASELINE)),"baseline evidence must exist before R4.2 authorization");
  const text=readText(R41_BASELINE);
  assert.match(text,/`CANONICAL_BASE_SHA`: `f455904b98d9bc1ed690e7948f99d9200a13cce4`/);
  assert.match(text,/`INVENTORY_INPUT_SHA256`: `[a-f0-9]{64}`/);
  for(const heading of ["Entry Point Inventory","Module Ownership Map","Dependency Boundary Map","Shared-State Inventory","Side-Effect Inventory","Coupling and Hotspots","Extraction Candidates","R4.2 Recommendation","Rollback Strategy","Required Tests","Hard Limits"])
    assert.match(text,new RegExp(`^## ${heading}$`,"m"));
  const selected=recommendation(text);
  assert.equal(selected.roadmap_item_id,"R4.2");
  assert.equal(selected.candidate,"router response-governance helper extraction");
  assert.equal(selected.score,29);
  assert.equal(selected.deployment_mode,"NO_DEPLOY");
  assert.equal(selected.network_boundary,false);
  assert.equal(selected.public_interface_migration,false);
  assert.deepEqual(selected.allowed_paths,[
    "tmp_agent/brain_v9/core/router_entrypoint.py",
    "tmp_agent/brain_v9/core/router_response_governance.py",
    "tests/contract/test_r4_2_router_response_governance.py"
  ]);
});

test("R5.2 closeout preserves R4 history and hands sole authority to JIT-bound R5.3",()=>{
  const manifest=readJson(MANIFEST);
  assert.equal(manifest.roadmap_items["R4.1"].status,"CLOSED_RUNTIME_VERIFIED");
  const r42=manifest.roadmap_items["R4.2"];
  assert.equal(r42.status,"CLOSED_RUNTIME_VERIFIED");
  assert.equal(r42.automation.front_id,"BRAIN-101-R4-2-ROUTER-RESPONSE-GOVERNANCE-01");
  assert.equal(r42.automation.deployment_mode,"NO_DEPLOY");
  assert.deepEqual(r42.automation.allowed_paths,[
    "tmp_agent/brain_v9/core/router_entrypoint.py",
    "tmp_agent/brain_v9/core/router_response_governance.py",
    "tests/contract/test_r4_2_router_response_governance.py"
  ]);
  assert.ok(existsSync(resolve(ROOT,"docs/roadmap/evidence/BRAIN_101_R4_1_MODULAR_MONOLITH_BASELINE_CLOSEOUT.json")));
  assert.ok(existsSync(resolve(ROOT,"docs/roadmap/evidence/BRAIN_101_R4_2_ROUTER_RESPONSE_GOVERNANCE_CLOSEOUT.json")));
  assert.ok(existsSync(resolve(ROOT,"docs/roadmap/evidence/BRAIN_101_R5_1_AGENT_V2_RUNTIME_BASELINE_CLOSEOUT.json")));
  assert.ok(existsSync(resolve(ROOT,"docs/roadmap/evidence/BRAIN_101_R5_2_AGENT_V2_LIFECYCLE_CHECKPOINTS_CLOSEOUT.json")));
  assert.deepEqual(activeItems(manifest).map(([item])=>item),["R5.3"]);
  const r43=manifest.roadmap_items["R4.3"];
  assert.deepEqual(r43.dependencies,["R4.2"]);
  assert.equal(r43.status,"CLOSED_RUNTIME_VERIFIED");
  assert.equal(r43.automation.front_id,"BRAIN-101-R4-3-CHAT-ENTRYPOINT-CONTRACTS-01");
  assert.equal(r43.automation.deployment_mode,"NO_DEPLOY");
  const r51=manifest.roadmap_items["R5.1"];
  assert.deepEqual(r51.dependencies,["R4.3"]);
  assert.equal(r51.automation.front_id,"BRAIN-101-R5-1-AGENT-V2-RUNTIME-BASELINE-01");
  assert.equal(r51.automation.jit_binding_completed,true);
  assert.equal(r51.automation.deployment_mode,"NO_DEPLOY");
  assert.equal(r51.status,"CLOSED_RUNTIME_VERIFIED");
  const r52=manifest.roadmap_items["R5.2"];
  assert.deepEqual(r52.dependencies,["R5.1"]);
  assert.equal(r52.automation.front_id,"BRAIN-101-R5-2-AGENT-V2-LIFECYCLE-CHECKPOINTS-01");
  assert.equal(r52.automation.jit_binding_completed,true);
  assert.equal(r52.automation.deployment_mode,"NO_DEPLOY");
  assert.equal(r52.status,"CLOSED_RUNTIME_VERIFIED");
  const r53=manifest.roadmap_items["R5.3"];
  assert.deepEqual(r53.dependencies,["R5.2"]);
  assert.equal(r53.status,"AUTHORIZED_ACTIVE");
  assert.equal(r53.automation.front_id,"BRAIN-101-R5-3-AGENT-V2-PLANNING-EVALUATION-PERSISTENCE-01");
  assert.equal(r53.automation.jit_binding_completed,true);
  assert.equal(r53.automation.deployment_mode,"NO_DEPLOY");
});
