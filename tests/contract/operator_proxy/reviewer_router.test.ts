import test from "node:test";
import assert from "node:assert/strict";
import {mkdtempSync,readFileSync,writeFileSync} from "node:fs";
import {tmpdir} from "node:os";
import {join} from "node:path";
import type {ReviewerBackend,ReviewerInput} from "../../../scripts/operator_proxy/reviewer_backend.js";
import {ReviewerBackendError} from "../../../scripts/operator_proxy/reviewer_backend.js";
import {inspectAgentLoopCommitModel,REVIEWER_MODELS,REVIEWER_QUALIFICATION,requiredBuilderModel,reviewerRoute,verifiedAgentLoopCommitModel,verifiedBuilderModel} from "../../../scripts/operator_proxy/reviewer_config.js";
import {ReviewerRouter,validateReviewerEnvelope} from "../../../scripts/operator_proxy/reviewer_router.js";

const head="b".repeat(40),base="a".repeat(40);
const input=(overrides:Partial<ReviewerInput>={}):ReviewerInput=>({repository:"cesarmanuel8102/AI_Vault",repositoryRoot:"C:\\repo",pr:99,baseSha:base,headSha:head,risk:"MEDIUM",changedFiles:["scripts/operator_proxy/operator_proxy.ts"],builderSession:"builder-1",...overrides});
const pass=(model:string):ReviewerBackend=>({model,review:(_input,session)=>({backend:"opencode_ollama",model,session,providerSession:`provider-${session}`,startedUtc:"2026-01-01T00:00:00Z",completedUtc:"2026-01-01T00:00:01Z",output:{verdict:"PASS",head_sha:head,summary:"pass",findings:[]}})});

test("routes by risk and agent-loop scope while excluding builder model",()=>{
  assert.deepEqual(reviewerRoute(input({risk:"LOW"})),[REVIEWER_MODELS.deepseekFlash,REVIEWER_MODELS.deepseekPro,REVIEWER_MODELS.nemotron]);
  assert.deepEqual(reviewerRoute(input({changedFiles:["scripts/agent_loop/local_worker/agent_worker.py"]})),[REVIEWER_MODELS.deepseekPro,REVIEWER_MODELS.deepseekFlash,REVIEWER_MODELS.nemotron]);
  assert.deepEqual(reviewerRoute(input({builderModel:REVIEWER_MODELS.deepseekPro})),[REVIEWER_MODELS.deepseekFlash,REVIEWER_MODELS.nemotron]);
  assert.deepEqual(reviewerRoute(input({builderModel:REVIEWER_MODELS.deepseekFlash})),[REVIEWER_MODELS.deepseekPro,REVIEWER_MODELS.nemotron]);
  assert.ok(!reviewerRoute(input()).includes(REVIEWER_MODELS.glm));
  assert.deepEqual(REVIEWER_QUALIFICATION[REVIEWER_MODELS.nemotron],{qualified:true,passed:5,total:5});
  assert.equal(requiredBuilderModel({OPERATOR_PROXY_BUILDER_MODEL:REVIEWER_MODELS.glm} as NodeJS.ProcessEnv),REVIEWER_MODELS.glm);
  assert.throws(()=>requiredBuilderModel({} as NodeJS.ProcessEnv),/builder model identity/);
  assert.equal(verifiedBuilderModel("agent_loop",{model:REVIEWER_MODELS.glm},{OPERATOR_PROXY_BUILDER_MODEL:REVIEWER_MODELS.glm} as NodeJS.ProcessEnv),REVIEWER_MODELS.glm);
  assert.throws(()=>verifiedBuilderModel("agent_loop",undefined,{OPERATOR_PROXY_BUILDER_MODEL:REVIEWER_MODELS.glm} as NodeJS.ProcessEnv),/report model identity/);
  assert.throws(()=>verifiedBuilderModel("agent_loop",{model:REVIEWER_MODELS.qwen},{OPERATOR_PROXY_BUILDER_MODEL:REVIEWER_MODELS.glm} as NodeJS.ProcessEnv),/report model identity/);
  assert.equal(verifiedBuilderModel("codex_control_plane"),"codex-local");
  const message=`test(agent-loop): complete FRONT-R1-TEST\n\nAGENT_LOOP_EXECUTOR_MODEL=${REVIEWER_MODELS.glm}`;
  assert.equal(verifiedAgentLoopCommitModel(message,"FRONT-R1-TEST",undefined,{OPERATOR_PROXY_BUILDER_MODEL:REVIEWER_MODELS.glm} as NodeJS.ProcessEnv),REVIEWER_MODELS.glm);
  assert.equal(verifiedAgentLoopCommitModel(message,"FRONT-R1-TEST",REVIEWER_MODELS.glm,{OPERATOR_PROXY_BUILDER_MODEL:REVIEWER_MODELS.glm} as NodeJS.ProcessEnv),REVIEWER_MODELS.glm);
  assert.throws(()=>verifiedAgentLoopCommitModel(message,"FRONT-R1-OTHER",undefined,{OPERATOR_PROXY_BUILDER_MODEL:REVIEWER_MODELS.glm} as NodeJS.ProcessEnv),/subject identity/);
  assert.throws(()=>verifiedAgentLoopCommitModel(message,"FRONT-R1-TEST",REVIEWER_MODELS.qwen,{OPERATOR_PROXY_BUILDER_MODEL:REVIEWER_MODELS.glm} as NodeJS.ProcessEnv),/receipt mismatch/);
  assert.throws(()=>verifiedAgentLoopCommitModel(`test(agent-loop): complete FRONT-R1-TEST`,"FRONT-R1-TEST",undefined,{OPERATOR_PROXY_BUILDER_MODEL:REVIEWER_MODELS.glm} as NodeJS.ProcessEnv),/receipt missing/);
  assert.deepEqual(inspectAgentLoopCommitModel(`test(agent-loop): complete FRONT-R1-TEST`,"FRONT-R1-TEST",undefined,{OPERATOR_PROXY_BUILDER_MODEL:REVIEWER_MODELS.glm} as NodeJS.ProcessEnv),{status:"MISSING",model:REVIEWER_MODELS.glm});
  assert.throws(()=>inspectAgentLoopCommitModel(`${message}\nAGENT_LOOP_EXECUTOR_MODEL=${REVIEWER_MODELS.glm}`,"FRONT-R1-TEST",undefined,{OPERATOR_PROXY_BUILDER_MODEL:REVIEWER_MODELS.glm} as NodeJS.ProcessEnv),/receipt ambiguous/);
  assert.throws(()=>inspectAgentLoopCommitModel(`test(agent-loop): complete FRONT-R1-TEST`,"FRONT-R1-TEST",REVIEWER_MODELS.qwen,{OPERATOR_PROXY_BUILDER_MODEL:REVIEWER_MODELS.glm} as NodeJS.ProcessEnv),/receipt mismatch/);
});

test("falls back after transient backend failure and persists idempotent receipt",()=>{
  const root=mkdtempSync(join(tmpdir(),"router-")),calls:string[]=[];
  let first=true;const factory=(model:string):ReviewerBackend=>model===REVIEWER_MODELS.deepseekPro&&first?{model,review:()=>{first=false;calls.push(model);throw new ReviewerBackendError("quota","RATE_LIMIT",true);}}:{...pass(model),review:(value,session)=>{calls.push(model);return pass(model).review(value,session);}};
  const router=new ReviewerRouter(root,factory),firstRun=router.review(input()),second=router.review(input());
  assert.equal(firstRun.output.verdict,"PASS");assert.equal(firstRun.model,REVIEWER_MODELS.deepseekPro);assert.equal(firstRun.verifier.model,REVIEWER_MODELS.deepseekFlash);assert.equal(firstRun.attempts.length,3);
  assert.equal(second.receipt_key,firstRun.receipt_key);assert.equal(calls.length,3);
});

test("fails closed when every backend is unavailable",()=>{
  const factory=(model:string):ReviewerBackend=>({model,review:()=>{throw new ReviewerBackendError("offline","MODEL_UNAVAILABLE");}});
  assert.throws(()=>new ReviewerRouter(mkdtempSync(join(tmpdir(),"router-")),factory).review(input()),/independent reviewer quorum unavailable/);
});

test("uses the third qualified reviewer when one primary candidate returns invalid output",()=>{
  const calls:string[]=[];
  const factory=(model:string):ReviewerBackend=>model===REVIEWER_MODELS.deepseekFlash?{model,review:()=>{calls.push(model);throw new ReviewerBackendError("invalid","REVIEWER_INVALID_OUTPUT");}}:{...pass(model),review:(value,session)=>{calls.push(model);return pass(model).review(value,session);}};
  const run=new ReviewerRouter(mkdtempSync(join(tmpdir(),"router-failover-")),factory).review(input({risk:"LOW"}));
  assert.equal(run.output.verdict,"PASS");assert.equal(run.model,REVIEWER_MODELS.deepseekPro);assert.equal(run.verifier.model,REVIEWER_MODELS.nemotron);assert.deepEqual(calls,[REVIEWER_MODELS.deepseekFlash,REVIEWER_MODELS.deepseekPro,REVIEWER_MODELS.nemotron]);
  assert.deepEqual(run.attempts.map(a=>[a.model,a.status]),[[REVIEWER_MODELS.deepseekFlash,"FAILED"],[REVIEWER_MODELS.deepseekPro,"PASS"],[REVIEWER_MODELS.nemotron,"PASS"]]);
});

test("P0 is escalated through the independent third arbiter",()=>{
  const factory=(model:string):ReviewerBackend=>model===REVIEWER_MODELS.deepseekPro?{model,review:(_value,session)=>({...pass(model).review(input(),session),output:{verdict:"BLOCKED",head_sha:head,summary:"p0",findings:[{severity:"P0",title:"authority",evidence:"unsafe",required_correction:"owner review"}]}})}:pass(model);
  const run=new ReviewerRouter(mkdtempSync(join(tmpdir(),"router-")),factory).review(input());assert.equal(run.output.verdict,"BLOCKED");assert.equal(run.arbiter?.model,REVIEWER_MODELS.nemotron);
});

test("verifier P0 is escalated through the independent third arbiter",()=>{
  const p0={severity:"P0" as const,title:"authority",evidence:"verifier evidence",required_correction:"owner review"};
  const factory=(model:string):ReviewerBackend=>model===REVIEWER_MODELS.deepseekFlash?{model,review:(_value,session)=>({...pass(model).review(input(),session),output:{verdict:"BLOCKED",head_sha:head,summary:"p0",findings:[p0]}})}:pass(model);
  const run=new ReviewerRouter(mkdtempSync(join(tmpdir(),"router-")),factory).review(input());assert.equal(run.output.verdict,"BLOCKED");assert.equal(run.arbiter?.model,REVIEWER_MODELS.nemotron);
});

test("PASS versus bounded P2 repairs converges conservatively without an arbiter",()=>{
  const factory=(model:string):ReviewerBackend=>model===REVIEWER_MODELS.deepseekFlash?{model,review:(_value,session)=>({...pass(model).review(input(),session),output:{verdict:"CHANGES_REQUESTED",head_sha:head,summary:"finding",findings:[{severity:"P2",title:"gap",evidence:"line",required_correction:"fix"}]}})}:pass(model);
  const run=new ReviewerRouter(mkdtempSync(join(tmpdir(),"router-")),factory).review(input());assert.equal(run.output.verdict,"CHANGES_REQUESTED");assert.equal(run.output.findings.length,1);assert.equal(run.arbiter,undefined);
});

test("builder in reviewer pool still fails closed on BLOCKED disagreement without a fourth actor",()=>{
  const factory=(model:string):ReviewerBackend=>model===REVIEWER_MODELS.deepseekFlash?{model,review:(_value,session)=>({...pass(model).review(input(),session),output:{verdict:"BLOCKED",head_sha:head,summary:"uncertain",findings:[]}})}:pass(model);
  assert.throws(()=>new ReviewerRouter(mkdtempSync(join(tmpdir(),"router-")),factory).review(input({builderModel:REVIEWER_MODELS.deepseekPro})),(error:any)=>error instanceof ReviewerBackendError&&error.failureClass==="P0_ARBITER_UNAVAILABLE");
});

test("PASS versus BLOCKED still uses the independent arbiter",()=>{
  const factory=(model:string):ReviewerBackend=>model===REVIEWER_MODELS.deepseekFlash?{model,review:(_value,session)=>({...pass(model).review(input(),session),output:{verdict:"BLOCKED",head_sha:head,summary:"uncertain",findings:[]}})}:pass(model);
  const run=new ReviewerRouter(mkdtempSync(join(tmpdir(),"router-")),factory).review(input());assert.equal(run.output.verdict,"BLOCKED");assert.equal(run.arbiter?.model,REVIEWER_MODELS.nemotron);
});

test("cached escalated receipt cannot be downgraded to PASS",()=>{
  const root=mkdtempSync(join(tmpdir(),"router-downgrade-")),router=new ReviewerRouter(root,model=>pass(model)),request=input(),run=router.review(request),path=join(root,"reviews",`review-${run.receipt_key}.json`),value=JSON.parse(readFileSync(path,"utf8"));
  value.output={verdict:"BLOCKED",head_sha:head,summary:"tampered",findings:[]};writeFileSync(path,JSON.stringify(value));assert.throws(()=>router.review(request),/review receipt/);
});

test("cached router receipt cannot bypass route, qualification, or builder exclusion",()=>{
  for(const mutate of [
    (value:any)=>{value.model=REVIEWER_MODELS.deepseekFlash;},
    (value:any)=>{value.model=REVIEWER_MODELS.glm;value.identity.builderModel=REVIEWER_MODELS.glm;},
    (value:any)=>{value.verifier.model=value.model;},
  ]){
    const root=mkdtempSync(join(tmpdir(),"router-cache-")),router=new ReviewerRouter(root,model=>pass(model)),request=input(),run=router.review(request),path=join(root,"reviews",`review-${run.receipt_key}.json`),value=JSON.parse(readFileSync(path,"utf8")),before=JSON.stringify(value);mutate(value);assert.notEqual(JSON.stringify(value),before,"tampering mutation must modify the persisted envelope");writeFileSync(path,JSON.stringify(value));assert.throws(()=>router.review(request),/review receipt/);
  }
});

test("outer ledger receipt is bound to complete validated router evidence",()=>{
  const request=input({builderModel:"codex-local"}),run=new ReviewerRouter(mkdtempSync(join(tmpdir(),"router-envelope-")),model=>pass(model)).review(request),expected={issue:65,pr:99,base_sha:base,head_sha:head,front_id:"FRONT-R1-TEST",builder_session:request.builderSession,builder_model:"codex-local"},envelope={schema_version:1,...expected,session:run.session,router_run:run,result:run.output},persisted=()=>JSON.parse(JSON.stringify(envelope));
  assert.equal(validateReviewerEnvelope(persisted(),expected,request).session,run.session);
  for(const mutate of [(value:any)=>{delete value.router_run;},(value:any)=>{value.builder_model=REVIEWER_MODELS.glm;},(value:any)=>{value.router_run.primary_output.summary="tampered-primary-output";},(value:any)=>{value.result.summary="tampered";}]){const value=persisted(),before=JSON.stringify(value);mutate(value);assert.notEqual(JSON.stringify(value),before,"tampering mutation must modify the persisted envelope");assert.throws(()=>validateReviewerEnvelope(value,expected,request),/review receipt/);}
});

test("transient truncation retried once then PASS",()=>{
  let truncated=false;
  const factory=(model:string):ReviewerBackend=>model===REVIEWER_MODELS.deepseekFlash?{model,review:(value,session)=>{if(!truncated){truncated=true;throw new ReviewerBackendError("truncated","REVIEWER_OUTPUT_TRUNCATED",true);}return pass(model).review(value,session);}}:pass(model);
  const run=new ReviewerRouter(mkdtempSync(join(tmpdir(),"router-truncation-")),factory).review(input({risk:"LOW"}));
  assert.equal(run.output.verdict,"PASS");assert.equal(run.attempts.length,3);
  const failed=run.attempts.filter(a=>a.status==="FAILED");assert.equal(failed.length,1);assert.equal(failed[0].failure_class,"REVIEWER_OUTPUT_TRUNCATED");assert.equal(failed[0].model,REVIEWER_MODELS.deepseekFlash);
  const passed=run.attempts.filter(a=>a.status==="PASS");assert.equal(passed.length,2);
  assert.notEqual(passed[0].session,passed[1].session);assert.equal(passed.find(a=>a.model===REVIEWER_MODELS.deepseekFlash)?.session,run.session);assert.equal(run.model,REVIEWER_MODELS.deepseekFlash);
  assert.equal(run.verifier.model,REVIEWER_MODELS.deepseekPro);assert.ok(!run.arbiter);
});

test("transient truncation twice on one model falls through to the third qualified reviewer",()=>{
  const factory=(model:string):ReviewerBackend=>model===REVIEWER_MODELS.deepseekPro?{model,review:()=>{throw new ReviewerBackendError("truncated","REVIEWER_OUTPUT_TRUNCATED",true);}}:pass(model);
  const run=new ReviewerRouter(mkdtempSync(join(tmpdir(),"router-truncation-twice-")),factory).review(input());assert.equal(run.output.verdict,"PASS");assert.equal(run.model,REVIEWER_MODELS.deepseekFlash);assert.equal(run.verifier.model,REVIEWER_MODELS.nemotron);assert.equal(run.attempts.filter(a=>a.model===REVIEWER_MODELS.deepseekPro&&a.status==="FAILED").length,2);
});
