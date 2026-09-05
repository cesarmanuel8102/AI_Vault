import test from "node:test";
import assert from "node:assert/strict";
import {execFileSync} from "node:child_process";
import {existsSync,mkdirSync,mkdtempSync,readFileSync,rmSync,writeFileSync} from "node:fs";
import {randomUUID} from "node:crypto";
import {tmpdir} from "node:os";
import {join,resolve} from "node:path";
import {BuilderAttemptProvenance,computeScopeFingerprint,readAttemptEvents,resolveCompletedBuilderSession,resolveCompletedBuilderSessionForSynchronizedLineage} from "../../../scripts/operator_proxy/builder_attempt_provenance.js";
import type {ProxySpec} from "../../../scripts/operator_proxy/types.js";

const spec:ProxySpec={
  schema_version:1,
  authorization_id:"CESAR-BRAIN-101-OPERATOR-PROXY-20260722-01",
  repository:"cesarmanuel8102/AI_Vault",
  roadmap_id:"BRAIN-101",
  roadmap_version:"1.0.0-reconstructed-glm-harmonized",
  roadmap_item_id:"R1.9",
  expected_base_sha:"a".repeat(40),
  executor:"codex_control_plane",
  risk:"LOW",
  allowed_paths:["docs/x.md"],
  forbidden_paths:["trading/"],
  acceptance:["pass"],
  test_commands:["git diff --check"],
  deployment_allowed:false,
  objective:"x",
  work_branch:"control-plane/synthetic-x",
  dependencies:["R0"],
  deployment_mode:"NO_DEPLOY",
  front_id:"BRAIN-101-R1-PROVENANCE-01",
};

function provenanceRepo(){
  const root=mkdtempSync(join(tmpdir(),"builder-provenance-")),source=join(root,"source"),remote=join(root,"remote.git"),worktrees=join(root,"worktrees");
  mkdirSync(source);
  execFileSync("git",["init","--bare",remote]);
  execFileSync("git",["init",source]);
  execFileSync("git",["-C",source,"config","user.email","builder@test.invalid"]);
  execFileSync("git",["-C",source,"config","user.name","Builder Test"]);
  writeFileSync(join(source,"README.md"),"base\n");
  execFileSync("git",["-C",source,"add","README.md"]);
  execFileSync("git",["-C",source,"commit","-m","base"]);
  execFileSync("git",["-C",source,"remote","add","origin",remote]);
  const base=execFileSync("git",["-C",source,"rev-parse","HEAD"],{encoding:"utf8"}).trim();
  mkdirSync(worktrees);
  const worktree=join(worktrees,spec.front_id!);
  execFileSync("git",["-C",source,"worktree","add","-b",spec.work_branch!,worktree,base]);
  execFileSync("git",["-C",worktree,"config","user.email","builder@test.invalid"]);
  execFileSync("git",["-C",worktree,"config","user.name","Builder Test"]);
  mkdirSync(join(worktree,"docs"),{recursive:true});
  return {root,source,remote,worktrees,worktree,base};
}

function makeInput(worktree:string,baseSha:string,frontId:string=spec.front_id!){
  return {
    repository:spec.repository,
    worktree,
    front_id:frontId,
    issue:90,
    base_sha:baseSha,
    work_branch:spec.work_branch!,
    allowed_paths:spec.allowed_paths,
    forbidden_paths:spec.forbidden_paths,
    acceptance:spec.acceptance,
    test_commands:spec.test_commands,
    repair_cycle:0,
    risk:spec.risk,
    deployment_mode:spec.deployment_mode!,
    prompt:"build it",
    session:"session-"+frontId.toLowerCase().replace(/[^a-z0-9]/g,"-"),
  };
}

function eventsPath(root:string,frontId:string=spec.front_id!){
  return join(root,"state","builder-attempts",frontId,"events.jsonl");
}

function activePath(root:string,frontId:string=spec.front_id!){
  return join(root,"state","builder-attempts",frontId,"active.json");
}

function providerCorr(backend:string="codex_cli_openai"){return `${backend}-${randomUUID()}`;}

test("completed durable provenance resolves exactly one builder session for a descendant candidate",()=>{
  const r=provenanceRepo();process.env.OPERATOR_PROXY_ROOT=r.root;
  try{
    const p=new BuilderAttemptProvenance(),input=makeInput(r.worktree,r.base),started=p.recordAttemptStart(input,{backend:"codex_cli_openai",model:"gpt-5.6-sol",attemptNumber:1,providerCorrelationId:providerCorr("codex_cli_openai")});
    writeFileSync(join(r.worktree,"docs","x.md"),"candidate\n");
    execFileSync("git",["-C",r.worktree,"add","docs/x.md"]);execFileSync("git",["-C",r.worktree,"commit","-m","candidate"]);
    const candidate=execFileSync("git",["-C",r.worktree,"rev-parse","HEAD"],{encoding:"utf8"}).trim();
    p.recordAttemptCompleted(started.receipt_id,spec.front_id!,candidate,["docs/x.md"],started.provider_correlation_id);
    writeFileSync(join(r.worktree,"docs","y.md"),"descendant\n");
    execFileSync("git",["-C",r.worktree,"add","docs/y.md"]);execFileSync("git",["-C",r.worktree,"commit","-m","descendant"]);
    const descendant=execFileSync("git",["-C",r.worktree,"rev-parse","HEAD"],{encoding:"utf8"}).trim();
    const isAncestor=(older:string,newer:string)=>{try{execFileSync("git",["-C",r.worktree,"merge-base","--is-ancestor",older,newer]);return true;}catch{return false;}};
    assert.equal(resolveCompletedBuilderSession({front_id:spec.front_id!,issue:90,base_sha:r.base,canonical_worktree:r.worktree,work_branch:spec.work_branch!,candidate_head_sha:descendant,isAncestor}),started.builder_session);
    assert.equal(resolveCompletedBuilderSession({front_id:spec.front_id!,issue:90,base_sha:r.base,canonical_worktree:r.worktree,work_branch:spec.work_branch!,candidate_head_sha:"f".repeat(40),isAncestor:()=>false}),undefined);
  }finally{delete process.env.OPERATOR_PROXY_ROOT;}
});

test("completed durable provenance rejects two matching builder sessions",()=>{
  const r=provenanceRepo();process.env.OPERATOR_PROXY_ROOT=r.root;
  try{
    const p=new BuilderAttemptProvenance(),input=makeInput(r.worktree,r.base),first=p.recordAttemptStart(input,{backend:"codex_cli_openai",model:"gpt-5.6-sol",attemptNumber:1,providerCorrelationId:providerCorr("codex_cli_openai")});
    writeFileSync(join(r.worktree,"docs","x.md"),"candidate\n");execFileSync("git",["-C",r.worktree,"add","docs/x.md"]);execFileSync("git",["-C",r.worktree,"commit","-m","candidate"]);
    const head=execFileSync("git",["-C",r.worktree,"rev-parse","HEAD"],{encoding:"utf8"}).trim();p.recordAttemptCompleted(first.receipt_id,spec.front_id!,head,["docs/x.md"],first.provider_correlation_id);
    const second=p.recordAttemptStart({...input,session:"other-builder-session"},{backend:"opencode_ollama",model:"ollama-cloud/kimi-k2.7-code",attemptNumber:2,providerCorrelationId:providerCorr("opencode_ollama")});p.recordAttemptCompleted(second.receipt_id,spec.front_id!,head,["docs/x.md"],second.provider_correlation_id);
    assert.throws(()=>resolveCompletedBuilderSession({front_id:spec.front_id!,issue:90,base_sha:r.base,canonical_worktree:r.worktree,work_branch:spec.work_branch!,candidate_head_sha:head,isAncestor:(older,newer)=>older===newer}),/ambiguous completed builder provenance/);
  }finally{delete process.env.OPERATOR_PROXY_ROOT;}
});

test("validated synchronization lineage resolves only one durable builder session from the original candidate",()=>{
  const r=provenanceRepo();process.env.OPERATOR_PROXY_ROOT=r.root;
  try{
    const p=new BuilderAttemptProvenance(),input=makeInput(r.worktree,r.base),started=p.recordAttemptStart(input,{backend:"codex_cli_openai",model:"gpt-5.6-sol",attemptNumber:1,providerCorrelationId:providerCorr("codex_cli_openai")});
    writeFileSync(join(r.worktree,"docs","x.md"),"candidate\n");execFileSync("git",["-C",r.worktree,"add","docs/x.md"]);execFileSync("git",["-C",r.worktree,"commit","-m","candidate"]);
    const candidate=execFileSync("git",["-C",r.worktree,"rev-parse","HEAD"],{encoding:"utf8"}).trim();
    p.recordAttemptCompleted(started.receipt_id,spec.front_id!,candidate,["docs/x.md"],started.provider_correlation_id);
    execFileSync("git",["-C",r.worktree,"commit","--allow-empty","-m","builder receipt wrapper"]);
    const validatedBuilderReceipt=execFileSync("git",["-C",r.worktree,"rev-parse","HEAD"],{encoding:"utf8"}).trim();
    const isAncestor=(older:string,newer:string)=>{try{execFileSync("git",["-C",r.worktree,"merge-base","--is-ancestor",older,newer]);return true;}catch{return false;}};
    assert.equal(resolveCompletedBuilderSessionForSynchronizedLineage({front_id:spec.front_id!,issue:90,canonical_worktree:r.worktree,work_branch:spec.work_branch!,validated_builder_receipt_head_sha:validatedBuilderReceipt,isAncestor}),started.builder_session);
  }finally{delete process.env.OPERATOR_PROXY_ROOT;}
});

test("validated synchronization lineage rejects ambiguous durable builder sessions",()=>{
  const r=provenanceRepo();process.env.OPERATOR_PROXY_ROOT=r.root;
  try{
    const p=new BuilderAttemptProvenance(),input=makeInput(r.worktree,r.base),first=p.recordAttemptStart(input,{backend:"codex_cli_openai",model:"gpt-5.6-sol",attemptNumber:1,providerCorrelationId:providerCorr("codex_cli_openai")});
    writeFileSync(join(r.worktree,"docs","x.md"),"candidate\n");execFileSync("git",["-C",r.worktree,"add","docs/x.md"]);execFileSync("git",["-C",r.worktree,"commit","-m","candidate"]);
    const candidate=execFileSync("git",["-C",r.worktree,"rev-parse","HEAD"],{encoding:"utf8"}).trim();p.recordAttemptCompleted(first.receipt_id,spec.front_id!,candidate,["docs/x.md"],first.provider_correlation_id);
    const second=p.recordAttemptStart({...input,session:"other-builder-session"},{backend:"opencode_ollama",model:"ollama-cloud/kimi-k2.7-code",attemptNumber:2,providerCorrelationId:providerCorr("opencode_ollama")});p.recordAttemptCompleted(second.receipt_id,spec.front_id!,candidate,["docs/x.md"],second.provider_correlation_id);
    execFileSync("git",["-C",r.worktree,"commit","--allow-empty","-m","builder receipt wrapper"]);
    const validatedBuilderReceipt=execFileSync("git",["-C",r.worktree,"rev-parse","HEAD"],{encoding:"utf8"}).trim();
    assert.throws(()=>resolveCompletedBuilderSessionForSynchronizedLineage({front_id:spec.front_id!,issue:90,canonical_worktree:r.worktree,work_branch:spec.work_branch!,validated_builder_receipt_head_sha:validatedBuilderReceipt,isAncestor:(older,newer)=>{try{execFileSync("git",["-C",r.worktree,"merge-base","--is-ancestor",older,newer]);return true;}catch{return false;}}}),/ambiguous completed builder provenance/);
  }finally{delete process.env.OPERATOR_PROXY_ROOT;}
});

test("scope fingerprint includes base and sorted scopes",()=>{
  const a=computeScopeFingerprint(spec.expected_base_sha,["docs/b.md","docs/a.md"],["trading/"]);
  const b=computeScopeFingerprint(spec.expected_base_sha,["docs/a.md","docs/b.md"],["trading/"]);
  assert.equal(a,b);
  assert.equal(a.length,64);
  assert.throws(()=>computeScopeFingerprint("notsha",["docs/a.md"],[]),/base invalid/);
  assert.throws(()=>computeScopeFingerprint(spec.expected_base_sha,["../x.md"],[]),/path invalid/);
});

test("recordAttemptStart writes STARTED receipt and active atomically",()=>{
  const r=provenanceRepo();
  process.env.OPERATOR_PROXY_ROOT=r.root;
  try{
    const p=new BuilderAttemptProvenance();
    const input=makeInput(r.worktree,r.base);
    const corr=providerCorr("codex_cli_openai");
    const receipt=p.recordAttemptStart(input,{backend:"codex_cli_openai",model:"gpt-5.6-sol",attemptNumber:1,providerCorrelationId:corr,providerSession:"codex-provider"});
    assert.equal(receipt.state,"STARTED");
    assert.equal(receipt.front_id,spec.front_id);
    assert.equal(receipt.issue,90);
    assert.equal(receipt.backend,"codex_cli_openai");
    assert.equal(receipt.model,"gpt-5.6-sol");
    assert.equal(receipt.provider_correlation_id,corr);
    assert.equal(receipt.provider_session,"codex-provider");
    assert.equal(receipt.attempt_number,1);
    assert.equal(receipt.scope_fingerprint,computeScopeFingerprint(r.base,spec.allowed_paths,spec.forbidden_paths));
    assert.ok(existsSync(eventsPath(r.root)));
    const active=JSON.parse(readFileSync(activePath(r.root),"utf8"));
    assert.equal(active.receipt_id,receipt.receipt_id);
    assert.equal(active.state,"STARTED");
  }finally{
    delete process.env.OPERATOR_PROXY_ROOT;
  }
});

test("recordQuarantine writes a QUARANTINED event without fabricating backend or model",()=>{
  const r=provenanceRepo();
  process.env.OPERATOR_PROXY_ROOT=r.root;
  try{
    writeFileSync(join(r.worktree,"docs","x.md"),"unattested\n");
    const p=new BuilderAttemptProvenance();
    const input=makeInput(r.worktree,r.base);
    const observedHead=execFileSync("git",["-C",r.worktree,"rev-parse","HEAD"],{encoding:"utf8"}).trim();
    const event=p.recordQuarantine(input,observedHead,r.base,"BUILDER_PROVENANCE_RECOVERY_REQUIRED");
    assert.equal(event.state,"QUARANTINED");
    assert.equal(event.front_id,spec.front_id);
    assert.equal(event.issue,90);
    assert.equal(event.observed_head,observedHead);
    assert.equal(event.authorized_base_sha,r.base);
    assert.equal(event.reason,"BUILDER_PROVENANCE_RECOVERY_REQUIRED");
    assert.ok(event.changed_files.includes("docs/x.md"));
    assert.ok(event.changed_files_digest);
    assert.equal(event.canonical_worktree,resolve(r.worktree));
    const qPath=join(r.root,"state","builder-attempts",spec.front_id!,"quarantine.jsonl");
    const lines=readFileSync(qPath,"utf8").trim().split("\n");
    assert.equal(lines.length,1);
    const parsed=JSON.parse(lines[0]);
    assert.equal(parsed.state,"QUARANTINED");
    assert.equal(parsed.backend,undefined);
    assert.equal(parsed.model,undefined);
    assert.equal(parsed.provider_correlation_id,undefined);
    assert.equal(existsSync(eventsPath(r.root)),false);
  }finally{
    delete process.env.OPERATOR_PROXY_ROOT;
  }
});

test("recordAttemptCompleted appends COMPLETED with head and files",()=>{
  const r=provenanceRepo();
  process.env.OPERATOR_PROXY_ROOT=r.root;
  try{
    const p=new BuilderAttemptProvenance();
    const input=makeInput(r.worktree,r.base);
    const started=p.recordAttemptStart(input,{backend:"opencode_github_copilot",model:"github-copilot/gpt-5.6-luna",attemptNumber:1,providerCorrelationId:providerCorr("opencode_github_copilot")});
    writeFileSync(join(r.worktree,"docs","x.md"),"completed\n");
    execFileSync("git",["-C",r.worktree,"add","docs/x.md"]);
    execFileSync("git",["-C",r.worktree,"commit","-m","backend output"]);
    const head=execFileSync("git",["-C",r.worktree,"rev-parse","HEAD"],{encoding:"utf8"}).trim();
    p.recordAttemptCompleted(started.receipt_id,spec.front_id!,head,["docs/x.md"],started.provider_correlation_id,"copilot-native");
    const events=readAttemptEvents(spec.front_id!);
    assert.equal(events.length,2);
    assert.equal(events[0].state,"STARTED");
    assert.equal(events[1].state,"COMPLETED");
    const completed=events[1] as any;
    assert.equal(completed.head_sha,head);
    assert.equal(completed.provider_correlation_id,started.provider_correlation_id);
    assert.equal(completed.native_provider_session,"copilot-native");
    assert.deepEqual(completed.changed_files,["docs/x.md"]);
    const active=JSON.parse(readFileSync(activePath(r.root),"utf8"));
    assert.equal(active.state,"NONE");
  }finally{
    delete process.env.OPERATOR_PROXY_ROOT;
  }
});

test("recordAttemptFailed appends FAILED and clears active",()=>{
  const r=provenanceRepo();
  process.env.OPERATOR_PROXY_ROOT=r.root;
  try{
    const p=new BuilderAttemptProvenance();
    const input=makeInput(r.worktree,r.base);
    const started=p.recordAttemptStart(input,{backend:"opencode_ollama",model:"ollama-cloud/deepseek-v4-pro",attemptNumber:1,providerCorrelationId:providerCorr("opencode_ollama")});
    p.recordAttemptFailed(started.receipt_id,spec.front_id!,"CODEX_CREDIT_LIMIT");
    const events=readAttemptEvents(spec.front_id!);
    assert.equal(events.length,2);
    assert.equal(events[1].state,"FAILED");
    assert.equal((events[1] as any).failure_class,"CODEX_CREDIT_LIMIT");
    const active=JSON.parse(readFileSync(activePath(r.root),"utf8"));
    assert.equal(active.state,"NONE");
  }finally{
    delete process.env.OPERATOR_PROXY_ROOT;
  }
});

test("failed record requires classified failure class",()=>{
  const r=provenanceRepo();
  process.env.OPERATOR_PROXY_ROOT=r.root;
  try{
    const p=new BuilderAttemptProvenance();
    const input=makeInput(r.worktree,r.base);
    const started=p.recordAttemptStart(input,{backend:"codex_cli_openai",model:"gpt-5.6-sol",attemptNumber:1,providerCorrelationId:providerCorr("codex_cli_openai")});
    assert.throws(()=>p.recordAttemptFailed(started.receipt_id,spec.front_id!,"UNCLASSIFIED"),/failure class/);
    assert.throws(()=>p.recordAttemptFailed(started.receipt_id,spec.front_id!,"test"),/failure class/);
  }finally{
    delete process.env.OPERATOR_PROXY_ROOT;
  }
});

test("findRecoverableStartedAttempt recovers exactly one matching STARTED after interruption",()=>{
  const r=provenanceRepo();
  process.env.OPERATOR_PROXY_ROOT=r.root;
  try{
    const p=new BuilderAttemptProvenance();
    const input=makeInput(r.worktree,r.base);
    const corr=providerCorr("codex_cli_openai");
    const started=p.recordAttemptStart(input,{backend:"codex_cli_openai",model:"gpt-5.6-sol",attemptNumber:1,providerCorrelationId:corr,providerSession:"codex-interrupted"});
    writeFileSync(join(r.worktree,"docs","x.md"),"recovered\n");
    const recoverable=p.findRecoverableStartedAttempt(input);
    assert.ok(recoverable);
    assert.equal(recoverable!.receipt.receipt_id,started.receipt_id);
    assert.equal(recoverable!.receipt.model,"gpt-5.6-sol");
    assert.equal(recoverable!.receipt.provider_correlation_id,corr);
    assert.equal(recoverable!.receipt.provider_session,"codex-interrupted");
  }finally{
    delete process.env.OPERATOR_PROXY_ROOT;
  }
});

test("recovery is rejected when worktree files violate scope",()=>{
  const r=provenanceRepo();
  process.env.OPERATOR_PROXY_ROOT=r.root;
  try{
    const p=new BuilderAttemptProvenance();
    const input=makeInput(r.worktree,r.base);
    p.recordAttemptStart(input,{backend:"codex_cli_openai",model:"gpt-5.6-sol",attemptNumber:1,providerCorrelationId:providerCorr("codex_cli_openai")});
    mkdirSync(join(r.worktree,"trading"),{recursive:true});
    writeFileSync(join(r.worktree,"trading","evil.md"),"bad\n");
    assert.throws(()=>p.findRecoverableStartedAttempt(input),/scope/);
  }finally{
    delete process.env.OPERATOR_PROXY_ROOT;
  }
});

test("recovery requires exactly one matching STARTED receipt",()=>{
  const r=provenanceRepo();
  process.env.OPERATOR_PROXY_ROOT=r.root;
  try{
    const p=new BuilderAttemptProvenance();
    const input=makeInput(r.worktree,r.base);
    p.recordAttemptStart(input,{backend:"codex_cli_openai",model:"gpt-5.6-sol",attemptNumber:1,providerCorrelationId:providerCorr("codex_cli_openai")});
    p.recordAttemptStart(input,{backend:"opencode_github_copilot",model:"github-copilot/gpt-5.6-luna",attemptNumber:1,providerCorrelationId:providerCorr("opencode_github_copilot")});
    assert.throws(()=>p.findRecoverableStartedAttempt(input),/ambiguous/);
  }finally{
    delete process.env.OPERATOR_PROXY_ROOT;
  }
});

test("recovery is rejected when the only STARTED is already completed",()=>{
  const r=provenanceRepo();
  process.env.OPERATOR_PROXY_ROOT=r.root;
  try{
    const p=new BuilderAttemptProvenance();
    const input=makeInput(r.worktree,r.base);
    const started=p.recordAttemptStart(input,{backend:"codex_cli_openai",model:"gpt-5.6-sol",attemptNumber:1,providerCorrelationId:providerCorr("codex_cli_openai")});
    writeFileSync(join(r.worktree,"docs","x.md"),"done\n");
    execFileSync("git",["-C",r.worktree,"add","docs/x.md"]);
    execFileSync("git",["-C",r.worktree,"commit","-m","done"]);
    const head=execFileSync("git",["-C",r.worktree,"rev-parse","HEAD"],{encoding:"utf8"}).trim();
    p.recordAttemptCompleted(started.receipt_id,spec.front_id!,head,["docs/x.md"],started.provider_correlation_id);
    assert.equal(p.findRecoverableStartedAttempt(input),undefined);
  }finally{
    delete process.env.OPERATOR_PROXY_ROOT;
  }
});

test("recovery rejects invalid front id",()=>{
  const r=provenanceRepo();
  process.env.OPERATOR_PROXY_ROOT=r.root;
  try{
    const p=new BuilderAttemptProvenance();
    const input=makeInput(r.worktree,r.base);
    p.recordAttemptStart(input,{backend:"codex_cli_openai",model:"gpt-5.6-sol",attemptNumber:1,providerCorrelationId:providerCorr("codex_cli_openai")});
    assert.throws(()=>p.findRecoverableStartedAttempt({...input,front_id:"not-valid"}),/front id invalid/);
  }finally{
    delete process.env.OPERATOR_PROXY_ROOT;
  }
});

test("recovery rejects mismatched issue, base, worktree, branch or scope",()=>{
  const r=provenanceRepo();
  process.env.OPERATOR_PROXY_ROOT=r.root;
  try{
    const p=new BuilderAttemptProvenance();
    const input=makeInput(r.worktree,r.base);
    p.recordAttemptStart(input,{backend:"codex_cli_openai",model:"gpt-5.6-sol",attemptNumber:1,providerCorrelationId:providerCorr("codex_cli_openai")});
    assert.equal(p.findRecoverableStartedAttempt({...input,front_id:"BRAIN-999-OTHER-01"}),undefined);
    assert.equal(p.findRecoverableStartedAttempt({...input,issue:91}),undefined);
    const otherBase="b".repeat(40);
    assert.equal(p.findRecoverableStartedAttempt({...input,base_sha:otherBase}),undefined);
    const otherWorktree=resolve(r.worktrees,"other");
    mkdirSync(otherWorktree,{recursive:true});
    execFileSync("git",["-C",r.source,"worktree","add","-b","control-plane/other",otherWorktree,r.base]);
    assert.equal(p.findRecoverableStartedAttempt({...input,worktree:otherWorktree}),undefined);
    assert.equal(p.findRecoverableStartedAttempt({...input,work_branch:"control-plane/other"}),undefined);
    assert.equal(p.findRecoverableStartedAttempt({...input,allowed_paths:["docs/y.md"]}),undefined);
  }finally{
    delete process.env.OPERATOR_PROXY_ROOT;
  }
});

test("active.json is created and cleared per receipt lifecycle",()=>{
  const r=provenanceRepo();
  process.env.OPERATOR_PROXY_ROOT=r.root;
  try{
    const p=new BuilderAttemptProvenance();
    const input=makeInput(r.worktree,r.base);
    const a=p.recordAttemptStart(input,{backend:"codex_cli_openai",model:"gpt-5.6-sol",attemptNumber:1,providerCorrelationId:providerCorr("codex_cli_openai")});
    assert.equal(JSON.parse(readFileSync(activePath(r.root),"utf8")).receipt_id,a.receipt_id);
    p.recordAttemptFailed(a.receipt_id,spec.front_id!,"MODEL_UNAVAILABLE");
    assert.equal(JSON.parse(readFileSync(activePath(r.root),"utf8")).state,"NONE");
    const b=p.recordAttemptStart(input,{backend:"opencode_github_copilot",model:"github-copilot/gpt-5.6-luna",attemptNumber:1,providerCorrelationId:providerCorr("opencode_github_copilot")});
    assert.equal(JSON.parse(readFileSync(activePath(r.root),"utf8")).receipt_id,b.receipt_id);
  }finally{
    delete process.env.OPERATOR_PROXY_ROOT;
  }
});

test("receipt events survive independent base sync in source repository",()=>{
  const r=provenanceRepo();
  process.env.OPERATOR_PROXY_ROOT=r.root;
  try{
    const p=new BuilderAttemptProvenance();
    const input=makeInput(r.worktree,r.base);
    const started=p.recordAttemptStart(input,{backend:"codex_cli_openai",model:"gpt-5.6-sol",attemptNumber:1,providerCorrelationId:providerCorr("codex_cli_openai")});
    writeFileSync(join(r.source,"BASE2.md"),"base2\n");
    execFileSync("git",["-C",r.source,"add","BASE2.md"]);
    execFileSync("git",["-C",r.source,"commit","-m","base 2"]);
    execFileSync("git",["-C",r.source,"push","origin","HEAD:refs/heads/codex/own-capital-sustainable-return"]);
    const events=readAttemptEvents(spec.front_id!);
    assert.equal(events.length,1);
    assert.equal(events[0].receipt_id,started.receipt_id);
  }finally{
    delete process.env.OPERATOR_PROXY_ROOT;
  }
});

test("receipt validation rejects invalid inputs",()=>{
  const r=provenanceRepo();
  process.env.OPERATOR_PROXY_ROOT=r.root;
  try{
    const p=new BuilderAttemptProvenance();
    const input=makeInput(r.worktree,r.base);
    assert.throws(()=>p.recordAttemptStart({...input,front_id:"bad"},{backend:"codex_cli_openai",model:"gpt-5.6-sol",attemptNumber:1,providerCorrelationId:providerCorr("codex_cli_openai")}),/front invalid/);
    assert.throws(()=>p.recordAttemptStart({...input,base_sha:"bad"},{backend:"codex_cli_openai",model:"gpt-5.6-sol",attemptNumber:1,providerCorrelationId:providerCorr("codex_cli_openai")}),/base invalid/);
    assert.throws(()=>p.recordAttemptStart(input,{backend:"unknown" as any,model:"gpt-5.6-sol",attemptNumber:1,providerCorrelationId:providerCorr("codex_cli_openai")}),/backend invalid/);
    assert.throws(()=>p.recordAttemptStart(input,{backend:"codex_cli_openai",model:"bad model!",attemptNumber:1,providerCorrelationId:providerCorr("codex_cli_openai")}),/model invalid/);
    assert.throws(()=>p.recordAttemptStart({...input,issue:0},{backend:"codex_cli_openai",model:"gpt-5.6-sol",attemptNumber:1,providerCorrelationId:providerCorr("codex_cli_openai")}),/issue invalid/);
    assert.throws(()=>p.recordAttemptStart(input,{backend:"codex_cli_openai",model:"gpt-5.6-sol",attemptNumber:0,providerCorrelationId:providerCorr("codex_cli_openai")}),/attempt number invalid/);
    assert.throws(()=>p.recordAttemptStart(input,{backend:"codex_cli_openai",model:"gpt-5.6-sol",attemptNumber:1,providerCorrelationId:"not valid!"}),/provider correlation id invalid/);
  }finally{
    delete process.env.OPERATOR_PROXY_ROOT;
  }
});

test("STARTED receipt builder_session matches actual BuilderInput.session used by backend",()=>{
  const r=provenanceRepo();process.env.OPERATOR_PROXY_ROOT=r.root;
  try{
    const p=new BuilderAttemptProvenance();
    const input=makeInput(r.worktree,r.base);
    const backendSession=input.session+"-codex_cli_openai";
    const corr=providerCorr("codex_cli_openai");
    const started=p.recordAttemptStart({...input,session:backendSession,provider_correlation_id:corr},{backend:"codex_cli_openai",model:"gpt-5.6-sol",attemptNumber:1,providerCorrelationId:corr});
    assert.equal(started.builder_session,backendSession);
  }finally{delete process.env.OPERATOR_PROXY_ROOT;}
});

test("STARTED provider correlation exists before backend invocation",()=>{
  const r=provenanceRepo();process.env.OPERATOR_PROXY_ROOT=r.root;
  try{
    const p=new BuilderAttemptProvenance();
    const input=makeInput(r.worktree,r.base);
    const corr=providerCorr("codex_cli_openai");
    const started=p.recordAttemptStart(input,{backend:"codex_cli_openai",model:"gpt-5.6-sol",attemptNumber:1,providerCorrelationId:corr});
    assert.ok(started.provider_correlation_id);
    assert.equal(started.provider_correlation_id,corr);
    assert.equal(started.state,"STARTED");
  }finally{delete process.env.OPERATOR_PROXY_ROOT;}
});

test("successful COMPLETED persists the same durable provider identity",()=>{
  const r=provenanceRepo();process.env.OPERATOR_PROXY_ROOT=r.root;
  try{
    const p=new BuilderAttemptProvenance();
    const input=makeInput(r.worktree,r.base);
    const corr=providerCorr("opencode_github_copilot");
    const started=p.recordAttemptStart({...input,provider_correlation_id:corr},{backend:"opencode_github_copilot",model:"github-copilot/gpt-5.6-luna",attemptNumber:1,providerCorrelationId:corr});
    writeFileSync(join(r.worktree,"docs","x.md"),"completed\n");
    execFileSync("git",["-C",r.worktree,"add","docs/x.md"]);
    execFileSync("git",["-C",r.worktree,"commit","-m","backend output"]);
    const head=execFileSync("git",["-C",r.worktree,"rev-parse","HEAD"],{encoding:"utf8"}).trim();
    p.recordAttemptCompleted(started.receipt_id,spec.front_id!,head,["docs/x.md"],corr,"copilot-native");
    const events=readAttemptEvents(spec.front_id!);
    const completed=events[1] as any;
    assert.equal(completed.provider_correlation_id,corr);
    assert.equal(completed.native_provider_session,"copilot-native");
  }finally{delete process.env.OPERATOR_PROXY_ROOT;}
});

test("dirty recovery uses exactly the durable provider correlation identity",()=>{
  const r=provenanceRepo();process.env.OPERATOR_PROXY_ROOT=r.root;
  try{
    const p=new BuilderAttemptProvenance();
    const input=makeInput(r.worktree,r.base);
    const corr=providerCorr("codex_cli_openai");
    const started=p.recordAttemptStart({...input,provider_correlation_id:corr},{backend:"codex_cli_openai",model:"gpt-5.6-sol",attemptNumber:1,providerCorrelationId:corr,providerSession:"codex-native"});
    writeFileSync(join(r.worktree,"docs","x.md"),"recovered\n");
    const recoverable=p.findRecoverableStartedAttempt({...input,provider_correlation_id:corr});
    assert.ok(recoverable);
    assert.equal(recoverable!.receipt.receipt_id,started.receipt_id);
    assert.equal(recoverable!.receipt.provider_correlation_id,corr);
    assert.equal(recoverable!.receipt.provider_session,"codex-native");
  }finally{delete process.env.OPERATOR_PROXY_ROOT;}
});

test("recovered commit never contains PROVIDER_SESSION=recovered",()=>{
  const r=provenanceRepo();process.env.OPERATOR_PROXY_ROOT=r.root;
  try{
    const p=new BuilderAttemptProvenance();
    const input=makeInput(r.worktree,r.base);
    const corr=providerCorr("codex_cli_openai");
    p.recordAttemptStart({...input,provider_correlation_id:corr},{backend:"codex_cli_openai",model:"gpt-5.6-sol",attemptNumber:1,providerCorrelationId:corr});
    writeFileSync(join(r.worktree,"docs","x.md"),"recovered\n");
    execFileSync("git",["-C",r.worktree,"add","docs/x.md"]);
    execFileSync("git",["-C",r.worktree,"commit","-m",`feat(control-plane): complete ${spec.front_id}\n\nBUILDER_BACKEND=codex_cli_openai\nBUILDER_MODEL=gpt-5.6-sol\nPROVIDER_SESSION=${corr}\n`]);
    const message=execFileSync("git",["-C",r.worktree,"show","-s","--format=%B"],{encoding:"utf8"});
    assert.doesNotMatch(message,/PROVIDER_SESSION=recovered/);
    assert.match(message,new RegExp(`PROVIDER_SESSION=${corr.replace(/[-[\]{}()*+?.,\\^$|#\s]/g,"\\$\u0026")}`));
  }finally{delete process.env.OPERATOR_PROXY_ROOT;}
});

test("missing provider identity fails closed",()=>{
  const r=provenanceRepo();process.env.OPERATOR_PROXY_ROOT=r.root;
  try{
    const p=new BuilderAttemptProvenance();
    const input=makeInput(r.worktree,r.base);
    p.recordAttemptStart(input,{backend:"codex_cli_openai",model:"gpt-5.6-sol",attemptNumber:1,providerCorrelationId:providerCorr("codex_cli_openai"),providerSession:"codex-native"});
    writeFileSync(join(r.worktree,"docs","x.md"),"recovered\n");
    assert.throws(()=>p.findRecoverableStartedAttempt({...input,provider_correlation_id:undefined as any}),/durable provider correlation missing/);
  }finally{delete process.env.OPERATOR_PROXY_ROOT;}
});

test("mismatched provider identity fails closed",()=>{
  const r=provenanceRepo();process.env.OPERATOR_PROXY_ROOT=r.root;
  try{
    const p=new BuilderAttemptProvenance();
    const input=makeInput(r.worktree,r.base);
    const corr=providerCorr("codex_cli_openai");
    p.recordAttemptStart({...input,provider_correlation_id:corr},{backend:"codex_cli_openai",model:"gpt-5.6-sol",attemptNumber:1,providerCorrelationId:corr});
    writeFileSync(join(r.worktree,"docs","x.md"),"recovered\n");
    assert.equal(p.findRecoverableStartedAttempt({...input,provider_correlation_id:providerCorr("opencode_github_copilot")}),undefined);
  }finally{delete process.env.OPERATOR_PROXY_ROOT;}
});

test("fallback attempt gets a distinct provider correlation",()=>{
  const r=provenanceRepo();process.env.OPERATOR_PROXY_ROOT=r.root;
  try{
    const p=new BuilderAttemptProvenance();
    const input=makeInput(r.worktree,r.base);
    const first=providerCorr("codex_cli_openai"),second=providerCorr("opencode_github_copilot");
    p.recordAttemptStart({...input,provider_correlation_id:first},{backend:"codex_cli_openai",model:"gpt-5.6-sol",attemptNumber:1,providerCorrelationId:first});
    p.recordAttemptFailed((readAttemptEvents(spec.front_id!)[0] as any).receipt_id,spec.front_id!,"CODEX_CREDIT_LIMIT");
    const fallback=p.recordAttemptStart({...input,provider_correlation_id:second},{backend:"opencode_github_copilot",model:"github-copilot/gpt-5.6-luna",attemptNumber:1,providerCorrelationId:second});
    assert.notEqual(first,second);
    assert.equal(fallback.provider_correlation_id,second);
  }finally{delete process.env.OPERATOR_PROXY_ROOT;}
});

test("failed attempt's provider identity cannot authorize later fallback files",()=>{
  const r=provenanceRepo();process.env.OPERATOR_PROXY_ROOT=r.root;
  try{
    const p=new BuilderAttemptProvenance();
    const input=makeInput(r.worktree,r.base);
    const failedCorr=providerCorr("codex_cli_openai");
    const fallbackCorr=providerCorr("opencode_github_copilot");
    const started=p.recordAttemptStart({...input,provider_correlation_id:failedCorr},{backend:"codex_cli_openai",model:"gpt-5.6-sol",attemptNumber:1,providerCorrelationId:failedCorr});
    writeFileSync(join(r.worktree,"docs","x.md"),"fallback content\n");
    execFileSync("git",["-C",r.worktree,"add","docs/x.md"]);
    execFileSync("git",["-C",r.worktree,"commit","-m","fallback commit"]);
    const head=execFileSync("git",["-C",r.worktree,"rev-parse","HEAD"],{encoding:"utf8"}).trim();
    assert.throws(()=>p.recordAttemptCompleted(started.receipt_id,spec.front_id!,head,["docs/x.md"],fallbackCorr),/provider correlation mismatch/);
  }finally{delete process.env.OPERATOR_PROXY_ROOT;}
});

test("no CommonJS require remains in builder_attempt_provenance.ts",()=>{
  const source=readFileSync(join(__dirname,"../../../scripts/operator_proxy/builder_attempt_provenance.ts"),"utf8");
  assert.doesNotMatch(source,/\brequire\s*\(/);
});

test("recovery commit trailers contain exactly one BUILDER_BACKEND, BUILDER_MODEL, and PROVIDER_SESSION",()=>{
  const r=provenanceRepo();process.env.OPERATOR_PROXY_ROOT=r.root;
  try{
    const p=new BuilderAttemptProvenance();
    const input=makeInput(r.worktree,r.base);
    const corr=providerCorr("codex_cli_openai");
    p.recordAttemptStart({...input,provider_correlation_id:corr},{backend:"codex_cli_openai",model:"gpt-5.6-sol",attemptNumber:1,providerCorrelationId:corr});
    writeFileSync(join(r.worktree,"docs","x.md"),"recovered\n");
    execFileSync("git",["-C",r.worktree,"add","docs/x.md"]);
    execFileSync("git",["-C",r.worktree,"commit","-m",`feat(control-plane): complete ${spec.front_id}\n\nBUILDER_BACKEND=codex_cli_openai\nBUILDER_MODEL=gpt-5.6-sol\nPROVIDER_SESSION=${corr}\n`]);
    const message=execFileSync("git",["-C",r.worktree,"show","-s","--format=%B"],{encoding:"utf8"}).trimEnd().split("\n");
    const backend=message.filter(l=>l.startsWith("BUILDER_BACKEND="));
    const model=message.filter(l=>l.startsWith("BUILDER_MODEL="));
    const session=message.filter(l=>l.startsWith("PROVIDER_SESSION="));
    assert.equal(backend.length,1);
    assert.equal(model.length,1);
    assert.equal(session.length,1);
  }finally{delete process.env.OPERATOR_PROXY_ROOT;}
});

test("durable STARTED recovery binds exact builder_session",()=>{
  const r=provenanceRepo();process.env.OPERATOR_PROXY_ROOT=r.root;
  try{
    const p=new BuilderAttemptProvenance();
    const input=makeInput(r.worktree,r.base);
    const corr=providerCorr("codex_cli_openai");
    p.recordAttemptStart({...input,session:"wanted-session"},{backend:"codex_cli_openai",model:"gpt-5.6-sol",attemptNumber:1,providerCorrelationId:corr});
    writeFileSync(join(r.worktree,"docs","x.md"),"wanted\n");
    assert.equal(p.findRecoverableStartedAttempt({...input,session:"other-session"}),undefined);
    const ok=p.findRecoverableStartedAttempt({...input,session:"wanted-session"});
    assert.ok(ok);
  }finally{delete process.env.OPERATOR_PROXY_ROOT;}
});

test("durable STARTED recovery binds exact repair_cycle",()=>{
  const r=provenanceRepo();process.env.OPERATOR_PROXY_ROOT=r.root;
  try{
    const p=new BuilderAttemptProvenance();
    const input=makeInput(r.worktree,r.base);
    const corr=providerCorr("codex_cli_openai");
    p.recordAttemptStart({...input,repair_cycle:2},{backend:"codex_cli_openai",model:"gpt-5.6-sol",attemptNumber:1,providerCorrelationId:corr});
    writeFileSync(join(r.worktree,"docs","x.md"),"cycle2\n");
    assert.equal(p.findRecoverableStartedAttempt({...input,repair_cycle:0}),undefined);
    assert.equal(p.findRecoverableStartedAttempt({...input,repair_cycle:1}),undefined);
    const ok=p.findRecoverableStartedAttempt({...input,repair_cycle:2});
    assert.ok(ok);
  }finally{delete process.env.OPERATOR_PROXY_ROOT;}
});

test("quarantine digest binds committed, staged, unstaged content and untracked bytes",()=>{
  const r=provenanceRepo();process.env.OPERATOR_PROXY_ROOT=r.root;
  try{
    const p=new BuilderAttemptProvenance();
    const input=makeInput(r.worktree,r.base);
    writeFileSync(join(r.worktree,"docs","x.md"),"uncommitted\n");
    const observed=execFileSync("git",["-C",r.worktree,"rev-parse","HEAD"],{encoding:"utf8"}).trim();
    const first=p.computeQuarantineDigest(r.worktree,r.base,observed);
    writeFileSync(join(r.worktree,"docs","x.md"),"different\n");
    const second=p.computeQuarantineDigest(r.worktree,r.base,observed);
    assert.notEqual(first,second);
    execFileSync("git",["-C",r.worktree,"add","docs/x.md"]);
    const staged=p.computeQuarantineDigest(r.worktree,r.base,observed);
    assert.notEqual(second,staged);
    execFileSync("git",["-C",r.worktree,"commit","-m","staged now committed"]);
    const committedHead=execFileSync("git",["-C",r.worktree,"rev-parse","HEAD"],{encoding:"utf8"}).trim();
    const committed=p.computeQuarantineDigest(r.worktree,r.base,committedHead);
    assert.notEqual(staged,committed);
    writeFileSync(join(r.worktree,"docs","y.md"),"untracked\n");
    const untracked=p.computeQuarantineDigest(r.worktree,r.base,committedHead);
    assert.notEqual(committed,untracked);
  }finally{delete process.env.OPERATOR_PROXY_ROOT;}
});

test("quarantine event lives in quarantine.jsonl separate from events.jsonl",()=>{
  const r=provenanceRepo();process.env.OPERATOR_PROXY_ROOT=r.root;
  try{
    const p=new BuilderAttemptProvenance();
    const input=makeInput(r.worktree,r.base);
    const observed=execFileSync("git",["-C",r.worktree,"rev-parse","HEAD"],{encoding:"utf8"}).trim();
    p.recordQuarantine(input,observed,r.base,"BUILDER_PROVENANCE_RECOVERY_REQUIRED");
    const qLines=readFileSync(join(r.root,"state","builder-attempts",spec.front_id!,"quarantine.jsonl"),"utf8").trim().split("\n");
    assert.equal(qLines.length,1);
    assert.equal(JSON.parse(qLines[0]).state,"QUARANTINED");
    assert.equal(existsSync(join(r.root,"state","builder-attempts",spec.front_id!,"events.jsonl")),false);
  }finally{delete process.env.OPERATOR_PROXY_ROOT;}
});

test("quarantined untracked path outside allowed scope blocks governed cleanup",()=>{
  const r=provenanceRepo();process.env.OPERATOR_PROXY_ROOT=r.root;
  try{
    const p=new BuilderAttemptProvenance();
    const input=makeInput(r.worktree,r.base);
    const paths=p.quarantinedPaths(r.worktree,r.base);
    assert.deepEqual(paths.untracked,[]);
    mkdirSync(join(r.worktree,"trading"),{recursive:true});
    writeFileSync(join(r.worktree,"trading","evil.md"),"bad\n");
    const withUntracked=p.quarantinedPaths(r.worktree,r.base);
    assert.deepEqual(withUntracked.untracked,["trading/evil.md"]);
    const inScope=(path:string)=>input.allowed_paths.some(p=>p.endsWith("/")?path.startsWith(p):path===p)&&!input.forbidden_paths.some(p=>path===p||path.startsWith(p.endsWith("/")?p:`${p}/`));
    for(const path of withUntracked.untracked)assert.equal(inScope(path),false);
  }finally{delete process.env.OPERATOR_PROXY_ROOT;}
});
