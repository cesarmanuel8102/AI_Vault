import test from "node:test";
import assert from "node:assert/strict";
import {mkdtempSync} from "node:fs";
import {tmpdir} from "node:os";
import {join} from "node:path";
import type {ReviewerBackend,ReviewerInput} from "../../../scripts/operator_proxy/reviewer_backend.js";
import {ReviewerBackendError} from "../../../scripts/operator_proxy/reviewer_backend.js";
import {REVIEWER_MODELS,requiredBuilderModel,reviewerRoute,verifiedBuilderModel} from "../../../scripts/operator_proxy/reviewer_config.js";
import {ReviewerRouter} from "../../../scripts/operator_proxy/reviewer_router.js";

const head="b".repeat(40),base="a".repeat(40);
const input=(overrides:Partial<ReviewerInput>={}):ReviewerInput=>({repository:"cesarmanuel8102/AI_Vault",repositoryRoot:"C:\\repo",pr:99,baseSha:base,headSha:head,risk:"MEDIUM",changedFiles:["scripts/operator_proxy/operator_proxy.ts"],builderSession:"builder-1",...overrides});
const pass=(model:string):ReviewerBackend=>({model,review:(_input,session)=>({backend:"opencode_ollama",model,session,providerSession:`provider-${session}`,startedUtc:"2026-01-01T00:00:00Z",completedUtc:"2026-01-01T00:00:01Z",output:{verdict:"PASS",head_sha:head,summary:"pass",findings:[]}})});

test("routes by risk and agent-loop scope while excluding builder model",()=>{
  assert.deepEqual(reviewerRoute(input({risk:"LOW"})),[REVIEWER_MODELS.qwen,REVIEWER_MODELS.glm,REVIEWER_MODELS.nemotron]);
  assert.deepEqual(reviewerRoute(input({changedFiles:["scripts/agent_loop/local_worker/agent_worker.py"]})),[REVIEWER_MODELS.glm,REVIEWER_MODELS.nemotron,REVIEWER_MODELS.qwen]);
  assert.ok(!reviewerRoute(input({builderModel:REVIEWER_MODELS.glm})).includes(REVIEWER_MODELS.glm));
  assert.equal(requiredBuilderModel({OPERATOR_PROXY_BUILDER_MODEL:REVIEWER_MODELS.glm} as NodeJS.ProcessEnv),REVIEWER_MODELS.glm);
  assert.throws(()=>requiredBuilderModel({} as NodeJS.ProcessEnv),/builder model identity/);
  assert.equal(verifiedBuilderModel("agent_loop",{model:REVIEWER_MODELS.glm},{OPERATOR_PROXY_BUILDER_MODEL:REVIEWER_MODELS.glm} as NodeJS.ProcessEnv),REVIEWER_MODELS.glm);
  assert.throws(()=>verifiedBuilderModel("agent_loop",undefined,{OPERATOR_PROXY_BUILDER_MODEL:REVIEWER_MODELS.glm} as NodeJS.ProcessEnv),/report model identity/);
  assert.throws(()=>verifiedBuilderModel("agent_loop",{model:REVIEWER_MODELS.qwen},{OPERATOR_PROXY_BUILDER_MODEL:REVIEWER_MODELS.glm} as NodeJS.ProcessEnv),/report model identity/);
  assert.equal(verifiedBuilderModel("codex_control_plane"),"codex-local");
});

test("falls back after transient backend failure and persists idempotent receipt",()=>{
  const root=mkdtempSync(join(tmpdir(),"router-")),calls:string[]=[];
  const factory=(model:string):ReviewerBackend=>model===REVIEWER_MODELS.glm?{model,review:()=>{calls.push(model);throw new ReviewerBackendError("quota","RATE_LIMIT",true);}}:{...pass(model),review:(value,session)=>{calls.push(model);return pass(model).review(value,session);}};
  const router=new ReviewerRouter(root,factory),first=router.review(input()),second=router.review(input());
  assert.equal(first.output.verdict,"PASS");assert.equal(first.model,REVIEWER_MODELS.qwen);assert.equal(first.verifier.model,REVIEWER_MODELS.nemotron);assert.equal(first.attempts.length,4);
  assert.equal(second.receipt_key,first.receipt_key);assert.equal(calls.length,4);
});

test("fails closed when every backend is unavailable",()=>{
  const factory=(model:string):ReviewerBackend=>({model,review:()=>{throw new ReviewerBackendError("offline","MODEL_UNAVAILABLE");}});
  assert.throws(()=>new ReviewerRouter(mkdtempSync(join(tmpdir(),"router-")),factory).review(input()),/independent reviewer quorum unavailable/);
});

test("P0 invokes a third qualified independent arbiter and remains BLOCKED",()=>{
  let arbiterInput:ReviewerInput|undefined;
  const factory=(model:string):ReviewerBackend=>model===REVIEWER_MODELS.nemotron?{...pass(model),review:(value,session)=>{arbiterInput=value;return pass(model).review(value,session);}}:{model,review:(_value,session)=>({...pass(model).review(input(),session),output:{verdict:"BLOCKED",head_sha:head,summary:"p0",findings:[{severity:"P0",title:"authority",evidence:"unsafe",required_correction:"owner review"}]}})};
  const result=new ReviewerRouter(mkdtempSync(join(tmpdir(),"router-")),factory).review(input());
  assert.equal(result.output.verdict,"BLOCKED");assert.equal(result.arbiter?.model,REVIEWER_MODELS.nemotron);
  assert.deepEqual((arbiterInput?.panelEvidence as any).primary.output.findings[0].severity,"P0");
  assert.equal((arbiterInput?.panelEvidence as any).verifier.output.verdict,"BLOCKED");
});

test("verifier-only P0 is preserved for owner escalation",()=>{
  let calls=0;
  const p0={severity:"P0" as const,title:"authority",evidence:"verifier evidence",required_correction:"owner review"};
  const factory=(model:string):ReviewerBackend=>model===REVIEWER_MODELS.nemotron?pass(model):calls++===0?pass(model):{model,review:(_value,session)=>({...pass(model).review(input(),session),output:{verdict:"BLOCKED",head_sha:head,summary:"p0",findings:[p0]}})};
  const result=new ReviewerRouter(mkdtempSync(join(tmpdir(),"router-")),factory).review(input());
  assert.equal(result.output.verdict,"BLOCKED");assert.deepEqual(result.output.findings,[p0]);
});

test("material reviewer disagreement invokes arbiter and never auto-approves",()=>{
  let calls=0;const factory=(model:string):ReviewerBackend=>model===REVIEWER_MODELS.nemotron?pass(model):calls++===0?pass(model):{model,review:(_value,session)=>({...pass(model).review(input(),session),output:{verdict:"CHANGES_REQUESTED",head_sha:head,summary:"finding",findings:[{severity:"P2",title:"gap",evidence:"line",required_correction:"fix"}]}})};
  const result=new ReviewerRouter(mkdtempSync(join(tmpdir(),"router-")),factory).review(input());assert.equal(result.output.verdict,"BLOCKED");assert.equal(result.arbiter?.model,REVIEWER_MODELS.nemotron);
});
