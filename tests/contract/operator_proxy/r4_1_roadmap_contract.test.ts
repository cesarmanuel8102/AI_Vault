import test from "node:test";
import assert from "node:assert/strict";
import {existsSync, readFileSync} from "node:fs";
import {dirname, resolve} from "node:path";
import {fileURLToPath} from "node:url";

const ROOT=resolve(dirname(fileURLToPath(import.meta.url)),"..","..","..");
const MANIFEST="docs/roadmap/BRAIN_101_MANIFEST.json";
const R34_CLOSEOUT="docs/roadmap/evidence/BRAIN_101_R3_4_AGENT_V2_COGNITIVE_PIPELINE_E2E_CLOSEOUT.json";
const R41_BASELINE="docs/roadmap/evidence/BRAIN_101_R4_1_MODULAR_MONOLITH_BASELINE.md";
const readJson=(path:string)=>JSON.parse(readFileSync(resolve(ROOT,path),"utf8"));
const activeItems=(manifest:any)=>Object.entries(manifest.roadmap_items).filter(([,item]:any)=>item.status==="AUTHORIZED_ACTIVE");

test("R3.4 controller closeout makes R4.1 the only active item",()=>{
  const manifest=readJson(MANIFEST);
  assert.equal(manifest.roadmap_items["R3.4"].status,"CLOSED_RUNTIME_VERIFIED");
  assert.deepEqual(activeItems(manifest).map(([item])=>item),["R4.1"]);
  assert.ok(existsSync(resolve(ROOT,R34_CLOSEOUT)));
});

test("R4.1 contract is no-deploy and protects prohibited boundaries",()=>{
  const item=readJson(MANIFEST).roadmap_items["R4.1"];
  assert.deepEqual(item.dependencies,["R3.4"]);
  assert.equal(item.automation.executor,"codex_control_plane");
  assert.equal(item.automation.deployment_mode,"NO_DEPLOY");
  assert.deepEqual(item.automation.allowed_paths,[R41_BASELINE]);
  for(const path of [".env","tmp_agent/brain_v9/trading/","financial_autonomy/","scripts/"])
    assert.ok(item.automation.forbidden_paths.includes(path));
});

test("R4.1 baseline evidence is present before an R4.2 extraction can be authorized",()=>{
  assert.ok(existsSync(resolve(ROOT,R41_BASELINE)));
});
