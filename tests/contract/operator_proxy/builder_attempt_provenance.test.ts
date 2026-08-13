import test from "node:test";
import assert from "node:assert/strict";
import {execFileSync} from "node:child_process";
import {existsSync,mkdirSync,mkdtempSync,readFileSync,rmSync,writeFileSync} from "node:fs";
import {tmpdir} from "node:os";
import {join,resolve} from "node:path";
import {BuilderAttemptProvenance,computeScopeFingerprint,readAttemptEvents} from "../../../scripts/operator_proxy/builder_attempt_provenance.js";
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
    const receipt=p.recordAttemptStart(input,{backend:"codex_cli_openai",model:"gpt-5.6-sol",attemptNumber:1,providerSession:"codex-provider"});
    assert.equal(receipt.state,"STARTED");
    assert.equal(receipt.front_id,spec.front_id);
    assert.equal(receipt.issue,90);
    assert.equal(receipt.backend,"codex_cli_openai");
    assert.equal(receipt.model,"gpt-5.6-sol");
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

test("recordAttemptCompleted appends COMPLETED with head and files",()=>{
  const r=provenanceRepo();
  process.env.OPERATOR_PROXY_ROOT=r.root;
  try{
    const p=new BuilderAttemptProvenance();
    const input=makeInput(r.worktree,r.base);
    const started=p.recordAttemptStart(input,{backend:"opencode_github_copilot",model:"github-copilot/gpt-5.6-luna",attemptNumber:1});
    writeFileSync(join(r.worktree,"docs","x.md"),"completed\n");
    execFileSync("git",["-C",r.worktree,"add","docs/x.md"]);
    execFileSync("git",["-C",r.worktree,"commit","-m","backend output"]);
    const head=execFileSync("git",["-C",r.worktree,"rev-parse","HEAD"],{encoding:"utf8"}).trim();
    p.recordAttemptCompleted(started.receipt_id,spec.front_id!,head,["docs/x.md"],"copilot-session");
    const events=readAttemptEvents(spec.front_id!);
    assert.equal(events.length,2);
    assert.equal(events[0].state,"STARTED");
    assert.equal(events[1].state,"COMPLETED");
    const completed=events[1] as any;
    assert.equal(completed.head_sha,head);
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
    const started=p.recordAttemptStart(input,{backend:"opencode_ollama",model:"ollama-cloud/deepseek-v4-pro",attemptNumber:1});
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
    const started=p.recordAttemptStart(input,{backend:"codex_cli_openai",model:"gpt-5.6-sol",attemptNumber:1});
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
    const started=p.recordAttemptStart(input,{backend:"codex_cli_openai",model:"gpt-5.6-sol",attemptNumber:1,providerSession:"codex-interrupted"});
    writeFileSync(join(r.worktree,"docs","x.md"),"recovered\n");
    const recoverable=p.findRecoverableStartedAttempt(input);
    assert.ok(recoverable);
    assert.equal(recoverable!.receipt.receipt_id,started.receipt_id);
    assert.equal(recoverable!.receipt.model,"gpt-5.6-sol");
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
    p.recordAttemptStart(input,{backend:"codex_cli_openai",model:"gpt-5.6-sol",attemptNumber:1});
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
    p.recordAttemptStart(input,{backend:"codex_cli_openai",model:"gpt-5.6-sol",attemptNumber:1});
    p.recordAttemptStart(input,{backend:"opencode_github_copilot",model:"github-copilot/gpt-5.6-luna",attemptNumber:1});
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
    const started=p.recordAttemptStart(input,{backend:"codex_cli_openai",model:"gpt-5.6-sol",attemptNumber:1});
    writeFileSync(join(r.worktree,"docs","x.md"),"done\n");
    execFileSync("git",["-C",r.worktree,"add","docs/x.md"]);
    execFileSync("git",["-C",r.worktree,"commit","-m","done"]);
    const head=execFileSync("git",["-C",r.worktree,"rev-parse","HEAD"],{encoding:"utf8"}).trim();
    p.recordAttemptCompleted(started.receipt_id,spec.front_id!,head,["docs/x.md"],"codex-done");
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
    p.recordAttemptStart(input,{backend:"codex_cli_openai",model:"gpt-5.6-sol",attemptNumber:1});
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
    p.recordAttemptStart(input,{backend:"codex_cli_openai",model:"gpt-5.6-sol",attemptNumber:1});
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
    const a=p.recordAttemptStart(input,{backend:"codex_cli_openai",model:"gpt-5.6-sol",attemptNumber:1});
    assert.equal(JSON.parse(readFileSync(activePath(r.root),"utf8")).receipt_id,a.receipt_id);
    p.recordAttemptFailed(a.receipt_id,spec.front_id!,"MODEL_UNAVAILABLE");
    assert.equal(JSON.parse(readFileSync(activePath(r.root),"utf8")).state,"NONE");
    const b=p.recordAttemptStart(input,{backend:"opencode_github_copilot",model:"github-copilot/gpt-5.6-luna",attemptNumber:1});
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
    const started=p.recordAttemptStart(input,{backend:"codex_cli_openai",model:"gpt-5.6-sol",attemptNumber:1});
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
    assert.throws(()=>p.recordAttemptStart({...input,front_id:"bad"},{backend:"codex_cli_openai",model:"gpt-5.6-sol",attemptNumber:1}),/front invalid/);
    assert.throws(()=>p.recordAttemptStart({...input,base_sha:"bad"},{backend:"codex_cli_openai",model:"gpt-5.6-sol",attemptNumber:1}),/base invalid/);
    assert.throws(()=>p.recordAttemptStart(input,{backend:"unknown" as any,model:"gpt-5.6-sol",attemptNumber:1}),/backend invalid/);
    assert.throws(()=>p.recordAttemptStart(input,{backend:"codex_cli_openai",model:"bad model!",attemptNumber:1}),/model invalid/);
    assert.throws(()=>p.recordAttemptStart({...input,issue:0},{backend:"codex_cli_openai",model:"gpt-5.6-sol",attemptNumber:1}),/issue invalid/);
    assert.throws(()=>p.recordAttemptStart(input,{backend:"codex_cli_openai",model:"gpt-5.6-sol",attemptNumber:0}),/attempt number invalid/);
  }finally{
    delete process.env.OPERATOR_PROXY_ROOT;
  }
});

test("legacy unattested PR identity is detected and blocked before reviewer execution",()=>{
  const body=`FRONT_ID: ${spec.front_id}\n\nRoadmap item: ${spec.roadmap_item_id}\n\nOPERATOR_PROXY_SPEC\n${JSON.stringify(spec)}`;
  assert.match(body,new RegExp(`FRONT_ID: ${spec.front_id}`));
});
