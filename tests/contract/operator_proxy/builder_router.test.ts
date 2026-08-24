import test from "node:test";
import assert from "node:assert/strict";
import {execFileSync} from "node:child_process";
import {existsSync,mkdirSync,mkdtempSync,readFileSync,rmSync,writeFileSync} from "node:fs";
import {tmpdir} from "node:os";
import {join,resolve} from "node:path";
import {routeControlPlaneBuild,listBuilderBackendHealth} from "../../../scripts/operator_proxy/builder_router.js";
import {isEligibleFallback,isEqualOrDescendantPath} from "../../../scripts/operator_proxy/builder_backend.js";
import {buildTimeoutMs,parseOpenCodeOutput,runOpenCodeBuilder} from "../../../scripts/operator_proxy/opencode_builder.js";
import {parseCodexOutput} from "../../../scripts/operator_proxy/codex_builder.js";
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
  front_id:"BRAIN-101-R1-SYNTHETIC-01",
};

test("forbidden root checks use path-component boundaries on Windows and POSIX",()=>{
  assert.equal(isEqualOrDescendantPath("C:\\AI_VAULT","C:\\AI_VAULT"),true);
  assert.equal(isEqualOrDescendantPath("C:\\AI_VAULT","C:\\AI_VAULT\\tmp_agent"),true);
  assert.equal(isEqualOrDescendantPath("C:\\AI_VAULT","C:\\AI_VAULT_CODEX_BRIDGE\\worktrees\\x"),false);
  assert.equal(isEqualOrDescendantPath("/AI_VAULT","/AI_VAULT/tmp_agent"),true);
  assert.equal(isEqualOrDescendantPath("/AI_VAULT","/AI_VAULT_CODEX_BRIDGE/worktrees/x"),false);
});

function builderRepo(){
  const root=mkdtempSync(join(tmpdir(),"builder-router-")),source=join(root,"source"),remote=join(root,"remote.git"),worktrees=join(root,"worktrees");
  mkdirSync(source);
  execFileSync("git",["init","--bare",remote]);
  execFileSync("git",["init",source]);
  execFileSync("git",["-C",source,"config","user.email","builder@test.invalid"]);
  execFileSync("git",["-C",source,"config","user.name","Builder Test"]);
  writeFileSync(join(source,"README.md"),"base\n");
  execFileSync("git",["-C",source,"add","README.md"]);
  execFileSync("git",["-C",source,"commit","-m","base"]);
  execFileSync("git",["-C",source,"remote","add","origin",remote]);
  execFileSync("git",["-C",source,"push","origin","HEAD:refs/heads/codex/own-capital-sustainable-return"]);
  const base=execFileSync("git",["-C",source,"rev-parse","HEAD"],{encoding:"utf8"}).trim();
  const worktree=resolve(worktrees,spec.front_id!);
  mkdirSync(join(worktree,".."),{recursive:true});
  execFileSync("git",["-C",source,"worktree","add","-b",spec.work_branch!,worktree,base]);
  execFileSync("git",["-C",worktree,"config","user.email","builder@test.invalid"]);
  execFileSync("git",["-C",worktree,"config","user.name","Builder Test"]);
  mkdirSync(join(worktree,"docs"));
  return {root,source,remote,worktree,base};
}

function fakeBackendScript(mark:string,exitCode=0){
  return `const fs=require("fs"),path=require("path"),{execFileSync}=require("child_process");function isWorktreeRoot(d){if(!d)return false;try{execFileSync(process.env.GIT_PATH||"git",["-C",d,"rev-parse","--is-inside-work-tree"],{stdio:"pipe",timeout:10000});return true;}catch{return false;}}function findWorktree(a){let idx=a.indexOf("-C");if(idx<0)idx=a.indexOf("--dir");if(idx>=0){const d=a[idx+1];if(isWorktreeRoot(d))return d;}for(let i=a.length-1;i>=2;i--){const d=a[i];if(isWorktreeRoot(d))return d;}return process.cwd();}const expected=process.env.EXPECTED_CODEX_MODEL;if(expected){const i=process.argv.indexOf("--model");if(i<0||process.argv[i+1]!==expected)process.exit(9);}const correlation=process.env.OPERATOR_PROXY_PROVIDER_CORRELATION_ID;if(!correlation)process.exit(11);const cwd=findWorktree(process.argv);fs.mkdirSync(path.join(cwd,"docs"),{recursive:true});fs.writeFileSync(path.join(cwd,"docs","x.md"),"${mark} build\\n");execFileSync(process.env.GIT_PATH||"git",["-C",cwd,"add","docs/x.md"]);execFileSync(process.env.GIT_PATH||"git",["-C",cwd,"commit","-m","feat(control-plane): complete BRAIN-101-R1-SYNTHETIC-01"]);const head=execFileSync(process.env.GIT_PATH||"git",["-C",cwd,"rev-parse","HEAD"],{encoding:"utf8"}).trim();console.log("HEAD_SHA="+head);console.log("PROVIDER_SESSION="+correlation);process.exit(${exitCode});`;
}

function currentHead(cwd:string){
  return execFileSync("git",["-C",cwd,"rev-parse","HEAD"],{encoding:"utf8"}).trim();
}

function attemptStates(root:string){
  const directory=join(root,"state","builder-attempts",spec.front_id!);
  return readFileSync(join(directory,"events.jsonl"),"utf8").trim().split("\n").map(line=>JSON.parse(line) as {state:string;failure_class?:string});
}

test("OpenCode builder converts a bounded native timeout into an eligible transport timeout",async()=>{
  const root=mkdtempSync(join(tmpdir(),"opencode-timeout-")),entry=join(root,"sleep.js"),worktree=join(root,"worktree");
  mkdirSync(worktree);writeFileSync(entry,"setTimeout(()=>process.exit(0),5000);");
  const env:any={...process.env,OPEN_CODE_PATH:entry,OPERATOR_PROXY_OPENCODE_TIMEOUT_MS:"1000",GIT_PATH:"git"};
  const input:any={worktree,session:"builder-timeout",provider_correlation_id:"provider-timeout",base_sha:"a".repeat(40),work_branch:"control-plane/timeout",prompt:"test"};
  await assert.rejects(runOpenCodeBuilder(input,{transport:"opencode_github_copilot",model:"github-copilot/test-model",executable:entry,maxRetries:0},env),error=>{
    const classified=isEligibleFallback(error);
    return classified.eligible===true&&classified.failure_class==="TRANSPORT_TIMEOUT";
  });
});

test("OpenCode builder derives the committed head from Git when model stdout has no receipt",async()=>{
  const root=mkdtempSync(join(tmpdir(),"opencode-git-head-")),worktree=join(root,"worktree"),entry=join(root,"commit-without-receipt.js");
  mkdirSync(worktree);execFileSync("git",["init",worktree]);execFileSync("git",["-C",worktree,"config","user.email","builder@test.invalid"]);execFileSync("git",["-C",worktree,"config","user.name","Builder Test"]);writeFileSync(join(worktree,"README.md"),"base\n");execFileSync("git",["-C",worktree,"add","README.md"]);execFileSync("git",["-C",worktree,"commit","-m","base"]);
  const base=execFileSync("git",["-C",worktree,"rev-parse","HEAD"],{encoding:"utf8"}).trim();
  writeFileSync(entry,`const fs=require("fs"),{execFileSync}=require("child_process"),a=process.argv,w=a[a.indexOf("--dir")+1];fs.writeFileSync(w+"/README.md","changed\\n");execFileSync("git",["-C",w,"add","README.md"]);execFileSync("git",["-C",w,"commit","-m","builder change"]);`);
  const result=await runOpenCodeBuilder({worktree,session:"builder-git-head",provider_correlation_id:"provider-git-head",base_sha:base,work_branch:"control-plane/test",prompt:"test"} as any,{transport:"opencode_ollama",model:"ollama-cloud/test-model",executable:entry,maxRetries:0},{...process.env,GIT_PATH:"git"});
  assert.notEqual(result.head_sha,base);assert.equal(result.provider_session,"provider-git-head");
});

test("OpenCode build timeout is bounded but permits a governed contract suite",()=>{
  assert.equal(buildTimeoutMs({}),300_000);
  assert.equal(buildTimeoutMs({OPERATOR_PROXY_OPENCODE_TIMEOUT_MS:"300000"}),300_000);
  assert.throws(()=>buildTimeoutMs({OPERATOR_PROXY_OPENCODE_TIMEOUT_MS:"300001"}),/OpenCode timeout out of range/);
});

test("configured OpenCode/Ollama builder is tried before bounded fallbacks",async()=>{
  const r=builderRepo(),ollama=join(r.source,"fake-ollama-primary.js"),codex=join(r.source,"codex-must-not-run.js"),called=join(r.source,"codex-called.txt");
  const prior={ollama:process.env.OPEN_CODE_OLLAMA_PATH,model:process.env.OPERATOR_PROXY_OLLAMA_BUILDER_MODEL,preferred:process.env.OPERATOR_PROXY_PREFERRED_BUILDER_BACKEND,codexEntry:process.env.CODEX_ENTRYPOINT,codexPath:process.env.CODEX_PATH,root:process.env.OPERATOR_PROXY_ROOT};
  writeFileSync(ollama,fakeBackendScript("kimi",0));
  writeFileSync(codex,`require("fs").writeFileSync(${JSON.stringify(called)},"called");process.exit(1);`);
  Object.assign(process.env,{OPEN_CODE_OLLAMA_PATH:ollama,OPERATOR_PROXY_OLLAMA_BUILDER_MODEL:"ollama-cloud/kimi-k2.7-code",OPERATOR_PROXY_PREFERRED_BUILDER_BACKEND:"opencode_ollama",CODEX_ENTRYPOINT:codex,CODEX_PATH:process.execPath,OPERATOR_PROXY_ROOT:mkdtempSync(join(tmpdir(),"builder-kimi-primary-"))});
  try { const result=await routeControlPlaneBuild({...spec,expected_base_sha:r.base},90,"x",0,{},r.worktree);assert.equal(result.builder_backend,"opencode_ollama");assert.equal(existsSync(called),false); }
  finally { for(const [key,value] of Object.entries(prior)){const envKey={ollama:"OPEN_CODE_OLLAMA_PATH",model:"OPERATOR_PROXY_OLLAMA_BUILDER_MODEL",preferred:"OPERATOR_PROXY_PREFERRED_BUILDER_BACKEND",codexEntry:"CODEX_ENTRYPOINT",codexPath:"CODEX_PATH",root:"OPERATOR_PROXY_ROOT"}[key]!;if(value===undefined)delete process.env[envKey];else process.env[envKey]=value;} }
});

test("primary Codex backend succeeds and reports codex_cli_openai",async()=>{
  const r=builderRepo();
  const entry=join(r.source,"fake-codex.js");
  const priorEntry=process.env.CODEX_ENTRYPOINT;
  const priorPath=process.env.CODEX_PATH;
  const priorRoot=process.env.OPERATOR_PROXY_ROOT;
  const priorModel=process.env.OPERATOR_PROXY_CODEX_BUILDER_MODEL;
  const priorExpected=process.env.EXPECTED_CODEX_MODEL;
  writeFileSync(entry,fakeBackendScript("codex",0));
  process.env.CODEX_ENTRYPOINT=entry;
  process.env.CODEX_PATH=process.execPath;
  process.env.OPERATOR_PROXY_CODEX_BUILDER_MODEL="gpt-5.6-terra";
  process.env.EXPECTED_CODEX_MODEL="gpt-5.6-terra";
  process.env.OPERATOR_PROXY_ROOT=mkdtempSync(join(tmpdir(),"builder-health-"));
  try{
    const result=await routeControlPlaneBuild({...spec,expected_base_sha:r.base},90,"x",0,{},r.worktree);
    assert.equal(result.builder_backend,"codex_cli_openai");
    assert.equal(result.builder_model,"gpt-5.6-terra");
    assert.match(result.provider_session,/^codex_cli_openai-[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/);
    assert.equal(result.fallback_reason,undefined);
    assert.equal(result.head_sha,currentHead(r.worktree));
    assert.equal(execFileSync("git",["-C",r.worktree,"show",`${result.head_sha}:docs/x.md`],{encoding:"utf8"}),"codex build\n");
  }finally{
    if(priorEntry===undefined)delete process.env.CODEX_ENTRYPOINT;else process.env.CODEX_ENTRYPOINT=priorEntry;
    if(priorPath===undefined)delete process.env.CODEX_PATH;else process.env.CODEX_PATH=priorPath;
    if(priorRoot===undefined)delete process.env.OPERATOR_PROXY_ROOT;else process.env.OPERATOR_PROXY_ROOT=priorRoot;
    if(priorModel===undefined)delete process.env.OPERATOR_PROXY_CODEX_BUILDER_MODEL;else process.env.OPERATOR_PROXY_CODEX_BUILDER_MODEL=priorModel;
    if(priorExpected===undefined)delete process.env.EXPECTED_CODEX_MODEL;else process.env.EXPECTED_CODEX_MODEL=priorExpected;
  }
});

test("fallback to Copilot when Codex reports credit exhaustion",async()=>{
  const r=builderRepo();
  const codexEntry=join(r.source,"fake-codex-credit.js");
  const opencodeEntry=join(r.source,"fake-opencode.js");
  const priorCodexEntry=process.env.CODEX_ENTRYPOINT;
  const priorCodexPath=process.env.CODEX_PATH;
  const priorOpenCode=process.env.OPEN_CODE_PATH;
  writeFileSync(codexEntry,`console.error("usage limit: you have run out of credits");process.exit(1);`);
  writeFileSync(opencodeEntry,fakeBackendScript("copilot",0));
  process.env.CODEX_ENTRYPOINT=codexEntry;
  process.env.CODEX_PATH=process.execPath;
  process.env.OPEN_CODE_PATH=opencodeEntry;
  const priorRoot=process.env.OPERATOR_PROXY_ROOT;
  const root=mkdtempSync(join(tmpdir(),"builder-health-"));
  process.env.OPERATOR_PROXY_ROOT=root;
  try{
    const result=await routeControlPlaneBuild({...spec,expected_base_sha:r.base},90,"x",0,{},r.worktree);
    assert.equal(result.builder_backend,"opencode_github_copilot");
    assert.equal(result.fallback_reason,"CODEX_CREDIT_LIMIT");
    assert.equal(result.head_sha,currentHead(r.worktree));
    assert.equal(execFileSync("git",["-C",r.worktree,"show",`${result.head_sha}:docs/x.md`],{encoding:"utf8"}),"copilot build\n");
    assert.ok(listBuilderBackendHealth(join(root,"state","builder-health")).some(f=>f.includes("codex_cli_openai")));
  }finally{
    if(priorCodexEntry===undefined)delete process.env.CODEX_ENTRYPOINT;else process.env.CODEX_ENTRYPOINT=priorCodexEntry;
    if(priorCodexPath===undefined)delete process.env.CODEX_PATH;else process.env.CODEX_PATH=priorCodexPath;
    if(priorOpenCode===undefined)delete process.env.OPEN_CODE_PATH;else process.env.OPEN_CODE_PATH=priorOpenCode;
    if(priorRoot===undefined)delete process.env.OPERATOR_PROXY_ROOT;else process.env.OPERATOR_PROXY_ROOT=priorRoot;
  }
});

test("fallback to Ollama when Codex and Copilot are unavailable",async()=>{
  const r=builderRepo();
  const codexEntry=join(r.source,"fake-codex-unavailable.js");
  const copilotEntry=join(r.source,"fake-copilot-unavailable.js");
  const ollamaEntry=join(r.source,"fake-ollama.js");
  const priorCodexEntry=process.env.CODEX_ENTRYPOINT;
  const priorCodexPath=process.env.CODEX_PATH;
  const priorOpenCode=process.env.OPEN_CODE_PATH;
  writeFileSync(codexEntry,`console.error("provider unavailable");process.exit(1);`);
  writeFileSync(copilotEntry,`console.error("provider unavailable");process.exit(1);`);
  writeFileSync(ollamaEntry,fakeBackendScript("ollama",0));
  process.env.CODEX_ENTRYPOINT=codexEntry;
  process.env.CODEX_PATH=process.execPath;
  process.env.OPEN_CODE_PATH=copilotEntry;
  const priorOllama=process.env.OPERATOR_PROXY_OLLAMA_BUILDER_MODEL;
  process.env.OPERATOR_PROXY_OLLAMA_BUILDER_MODEL="opencode/kimi-k2.7-code";
  const priorOllamaPath=process.env.OPEN_CODE_OLLAMA_PATH;
  process.env.OPEN_CODE_OLLAMA_PATH=ollamaEntry;
  const priorRoot=process.env.OPERATOR_PROXY_ROOT;
  const root=mkdtempSync(join(tmpdir(),"builder-health-ollama-"));
  process.env.OPERATOR_PROXY_ROOT=root;
  try{
    const result=await routeControlPlaneBuild({...spec,expected_base_sha:r.base},90,"x",0,{},r.worktree);
    assert.equal(result.builder_backend,"opencode_ollama");
    assert.equal(result.fallback_reason,"PROVIDER_UNAVAILABLE");
    assert.equal(result.head_sha,currentHead(r.worktree));
    assert.equal(execFileSync("git",["-C",r.worktree,"show",`${result.head_sha}:docs/x.md`],{encoding:"utf8"}),"ollama build\n");
  }finally{
    if(priorCodexEntry===undefined)delete process.env.CODEX_ENTRYPOINT;else process.env.CODEX_ENTRYPOINT=priorCodexEntry;
    if(priorCodexPath===undefined)delete process.env.CODEX_PATH;else process.env.CODEX_PATH=priorCodexPath;
    if(priorOpenCode===undefined)delete process.env.OPEN_CODE_PATH;else process.env.OPEN_CODE_PATH=priorOpenCode;
    if(priorOllama===undefined)delete process.env.OPERATOR_PROXY_OLLAMA_BUILDER_MODEL;else process.env.OPERATOR_PROXY_OLLAMA_BUILDER_MODEL=priorOllama;
    if(priorOllamaPath===undefined)delete process.env.OPEN_CODE_OLLAMA_PATH;else process.env.OPEN_CODE_OLLAMA_PATH=priorOllamaPath;
    if(priorRoot===undefined)delete process.env.OPERATOR_PROXY_ROOT;else process.env.OPERATOR_PROXY_ROOT=priorRoot;
  }
});

test("OPERATOR_PROXY_BUILDER_BACKEND override skips router order",async()=>{
  const r=builderRepo();
  const codexEntry=join(r.source,"fake-codex-override.js");
  const opencodeEntry=join(r.source,"fake-opencode-override.js");
  const priorCodexEntry=process.env.CODEX_ENTRYPOINT;
  const priorCodexPath=process.env.CODEX_PATH;
  const priorOpenCode=process.env.OPEN_CODE_PATH;
  const priorBackend=process.env.OPERATOR_PROXY_BUILDER_BACKEND;
  const priorRoot=process.env.OPERATOR_PROXY_ROOT;
  writeFileSync(codexEntry,`console.error("codex should not run");process.exit(1);`);
  writeFileSync(opencodeEntry,fakeBackendScript("override",0));
  process.env.CODEX_ENTRYPOINT=codexEntry;
  process.env.CODEX_PATH=process.execPath;
  process.env.OPEN_CODE_PATH=opencodeEntry;
  process.env.OPERATOR_PROXY_BUILDER_BACKEND="opencode_github_copilot";
  process.env.OPERATOR_PROXY_ROOT=mkdtempSync(join(tmpdir(),"builder-health-override-"));
  try{
    const result=await routeControlPlaneBuild({...spec,expected_base_sha:r.base},90,"x",0,{},r.worktree);
    assert.equal(result.builder_backend,"opencode_github_copilot");
    assert.equal(result.head_sha,currentHead(r.worktree));
    assert.equal(result.fallback_reason,undefined);
    assert.equal(execFileSync("git",["-C",r.worktree,"show",`${result.head_sha}:docs/x.md`],{encoding:"utf8"}),"override build\n");
  }finally{
    if(priorCodexEntry===undefined)delete process.env.CODEX_ENTRYPOINT;else process.env.CODEX_ENTRYPOINT=priorCodexEntry;
    if(priorCodexPath===undefined)delete process.env.CODEX_PATH;else process.env.CODEX_PATH=priorCodexPath;
    if(priorOpenCode===undefined)delete process.env.OPEN_CODE_PATH;else process.env.OPEN_CODE_PATH=priorOpenCode;
    if(priorBackend===undefined)delete process.env.OPERATOR_PROXY_BUILDER_BACKEND;else process.env.OPERATOR_PROXY_BUILDER_BACKEND=priorBackend;
    if(priorRoot===undefined)delete process.env.OPERATOR_PROXY_ROOT;else process.env.OPERATOR_PROXY_ROOT=priorRoot;
  }
});

test("ineligible failure fails closed without fallback",async()=>{
  const r=builderRepo();
  const entry=join(r.source,"fake-codex-scope.js");
  const fakeOpenCode=join(r.source,"fake-opencode-should-not-run.js");
  const priorEntry=process.env.CODEX_ENTRYPOINT;
  const priorPath=process.env.CODEX_PATH;
  const priorOpenCode=process.env.OPEN_CODE_PATH;
  const priorRoot=process.env.OPERATOR_PROXY_ROOT;
  const isWorktree=`function isWorktreeRoot(d){if(!d)return false;try{require("child_process").execFileSync(process.env.GIT_PATH||"git",["-C",d,"rev-parse","--is-inside-work-tree"],{stdio:"pipe",timeout:10000});return true;}catch{return false;}}`;
  const findWorktree=`function findWorktree(a){let idx=a.indexOf("-C");if(idx<0)idx=a.indexOf("--dir");if(idx>=0){const d=a[idx+1];if(isWorktreeRoot(d))return d;}for(let i=a.length-1;i>=2;i--){const d=a[i];if(isWorktreeRoot(d))return d;}return process.cwd();}`;
  writeFileSync(entry,`const fs=require("fs"),path=require("path"),{execFileSync}=require("child_process");${isWorktree}${findWorktree}const correlation=process.env.OPERATOR_PROXY_PROVIDER_CORRELATION_ID;if(!correlation)process.exit(11);const cwd=findWorktree(process.argv);fs.mkdirSync(path.join(cwd,"docs"),{recursive:true});fs.writeFileSync(path.join(cwd,"docs","y.md"),"out of scope\\n");execFileSync(process.env.GIT_PATH||"git",["-C",cwd,"add","docs/y.md"]);execFileSync(process.env.GIT_PATH||"git",["-C",cwd,"commit","-m","feat(control-plane): complete BRAIN-101-R1-SYNTHETIC-01"]);const head=execFileSync(process.env.GIT_PATH||"git",["-C",cwd,"rev-parse","HEAD"],{encoding:"utf8"}).trim();console.log("HEAD_SHA="+head);console.log("PROVIDER_SESSION="+correlation);`);
  writeFileSync(fakeOpenCode,`console.error("OpenCode should not run for ineligible failure");process.exit(1);`);
  process.env.CODEX_ENTRYPOINT=entry;
  process.env.CODEX_PATH=process.execPath;
  process.env.OPEN_CODE_PATH=fakeOpenCode;
  process.env.OPERATOR_PROXY_ROOT=mkdtempSync(join(tmpdir(),"builder-health-ineligible-"));
  try{
    await assert.rejects(routeControlPlaneBuild({...spec,expected_base_sha:r.base},90,"x",0,{},r.worktree),/forbidden paths/);
  }finally{
    if(priorEntry===undefined)delete process.env.CODEX_ENTRYPOINT;else process.env.CODEX_ENTRYPOINT=priorEntry;
    if(priorPath===undefined)delete process.env.CODEX_PATH;else process.env.CODEX_PATH=priorPath;
    if(priorOpenCode===undefined)delete process.env.OPEN_CODE_PATH;else process.env.OPEN_CODE_PATH=priorOpenCode;
    if(priorRoot===undefined)delete process.env.OPERATOR_PROXY_ROOT;else process.env.OPERATOR_PROXY_ROOT=priorRoot;
  }
});

test("OPERATOR_PROXY_ROOT is required and must be absolute",async()=>{
  const r=builderRepo(),prior=process.env.OPERATOR_PROXY_ROOT;
  try{
    delete process.env.OPERATOR_PROXY_ROOT;
    await assert.rejects(routeControlPlaneBuild({...spec,expected_base_sha:r.base},90,"x",0,{},r.worktree),/BUILDER_PROVENANCE_START_WRITE_FAILED: OPERATOR_PROXY_ROOT required in campaign mode/);
    process.env.OPERATOR_PROXY_ROOT="relative-root";
    await assert.rejects(routeControlPlaneBuild({...spec,expected_base_sha:r.base},90,"x",0,{},r.worktree),/OPERATOR_PROXY_ROOT must be absolute/);
  }finally{if(prior===undefined)delete process.env.OPERATOR_PROXY_ROOT;else process.env.OPERATOR_PROXY_ROOT=prior;}
});

test("health ledger failure does not block eligible fallback",async()=>{
  const r=builderRepo(),codexEntry=join(r.source,"fake-codex-credit.js"),opencodeEntry=join(r.source,"fake-opencode.js"),healthFile=join(r.root,"state","builder-health");
  const priorCodexEntry=process.env.CODEX_ENTRYPOINT,priorCodexPath=process.env.CODEX_PATH,priorOpenCode=process.env.OPEN_CODE_PATH,priorRoot=process.env.OPERATOR_PROXY_ROOT;
  writeFileSync(codexEntry,`console.error("usage limit: credits exhausted");process.exit(1);`);
  writeFileSync(opencodeEntry,fakeBackendScript("health fallback",0));
  process.env.CODEX_ENTRYPOINT=codexEntry;process.env.CODEX_PATH=process.execPath;process.env.OPEN_CODE_PATH=opencodeEntry;process.env.OPERATOR_PROXY_ROOT=r.root;
  mkdirSync(join(r.root,"state"),{recursive:true});writeFileSync(healthFile,"not a directory\n");
  try{
    const result=await routeControlPlaneBuild({...spec,expected_base_sha:r.base},90,"x",0,{},r.worktree);
    assert.equal(result.builder_backend,"opencode_github_copilot");
    assert.equal(result.fallback_reason,"CODEX_CREDIT_LIMIT");
  }finally{
    if(priorCodexEntry===undefined)delete process.env.CODEX_ENTRYPOINT;else process.env.CODEX_ENTRYPOINT=priorCodexEntry;
    if(priorCodexPath===undefined)delete process.env.CODEX_PATH;else process.env.CODEX_PATH=priorCodexPath;
    if(priorOpenCode===undefined)delete process.env.OPEN_CODE_PATH;else process.env.OPEN_CODE_PATH=priorOpenCode;
    if(priorRoot===undefined)delete process.env.OPERATOR_PROXY_ROOT;else process.env.OPERATOR_PROXY_ROOT=priorRoot;
  }
});

test("fallback classification is deterministic for representative backend and governance failures",()=>{
  const cases:[string,boolean,string][]=[
    ["usage limit: credits exhausted",true,"CODEX_CREDIT_LIMIT"], ["quota exceeded",true,"CODEX_QUOTA_EXHAUSTED"], ["rate limit",true,"RATE_LIMIT"],
    ["model unavailable",true,"MODEL_UNAVAILABLE"], ["auth session expired",true,"AUTH_SESSION_EXPIRED"], ["protocol violation",true,"PROVIDER_PROTOCOL_FAILURE"], ["provider unavailable",true,"PROVIDER_UNAVAILABLE"], ["spawnSync codex ENOENT",true,"EXECUTABLE_NOT_FOUND"],
    ["builder changed forbidden paths: docs/y.md",false,"FORBIDDEN_PATH"], ["builder worktree base mismatch",false,"WRONG_BASE"],
    ["git conflict",false,"GIT_CONFLICT"], ["test failed",false,"TEST_FAILURE"],
  ];
  for(const [message,eligible,failureClass] of cases){const result=isEligibleFallback(new Error(message));assert.equal(result.eligible,eligible,message);assert.equal(result.failure_class,failureClass,message);}
});

test("OpenCode output requires one canonical HEAD_SHA receipt",()=>{
  const head="a".repeat(40);
  assert.deepEqual(parseOpenCodeOutput(`HEAD_SHA=${head}\nPROVIDER_SESSION=session-1\n`),{headSha:head,providerSession:"session-1",nativeProviderSession:undefined});
  assert.throws(()=>parseOpenCodeOutput(`HEAD_SHA=${head}\nHEAD_SHA=${head}\n`),/ambiguous/);
  assert.throws(()=>parseOpenCodeOutput("HEAD_SHA=not-a-sha\n"),/invalid/);
});

test("builder receipt parsers preserve one canonical provider session and reject ambiguity",()=>{
  const head="a".repeat(40),receipt=`HEAD_SHA=${head}\nPROVIDER_SESSION=provider-session-1\n`;
  assert.equal(parseCodexOutput(receipt).providerSession,"provider-session-1");
  assert.equal(parseOpenCodeOutput(receipt).providerSession,"provider-session-1");
  for(const parse of [parseCodexOutput,parseOpenCodeOutput]){
    assert.throws(()=>parse(`${receipt}PROVIDER_SESSION=provider-session-2\n`),/ambiguous/);
    assert.throws(()=>parse(`HEAD_SHA=${head}\nPROVIDER_SESSION=INVALID SESSION\n`),/invalid/);
  }
});

function advanceWorktree(worktree:string,payload:string){
  writeFileSync(join(worktree,"docs","x.md"),payload);
  execFileSync("git",["-C",worktree,"add","docs/x.md"]);
  execFileSync("git",["-C",worktree,"commit","-m","existing governed candidate"]);
  return currentHead(worktree);
}

function cleanFallbackScript(expectedBase:string,marker:string){
  return `const fs=require("fs"),path=require("path"),{execFileSync}=require("child_process");const correlation=process.env.OPERATOR_PROXY_PROVIDER_CORRELATION_ID;if(!correlation)process.exit(11);const a=process.argv;const i=a.indexOf("--dir");const cwd=a[i+1];const head=execFileSync("git",["-C",cwd,"rev-parse","HEAD"],{encoding:"utf8"}).trim();const status=execFileSync("git",["-C",cwd,"status","--porcelain","--untracked-files=all"],{encoding:"utf8"}).trim();if(head!=="${expectedBase}"||status)throw new Error("fallback baseline not pristine");fs.mkdirSync(path.join(cwd,"docs"),{recursive:true});fs.writeFileSync(path.join(cwd,"docs","x.md"),"${marker}\\n");execFileSync("git",["-C",cwd,"add","docs/x.md"]);execFileSync("git",["-C",cwd,"commit","-m","feat(control-plane): complete BRAIN-101-R1-SYNTHETIC-01"]);console.log("HEAD_SHA="+execFileSync("git",["-C",cwd,"rev-parse","HEAD"],{encoding:"utf8"}).trim());console.log("PROVIDER_SESSION="+correlation);`;
}

test("repair build uses the exact clean candidate HEAD as its effective base",async()=>{
  const r=builderRepo(),candidate=advanceWorktree(r.worktree,"candidate\n"),entry=join(r.source,"repair-builder.js");
  const prior={entry:process.env.CODEX_ENTRYPOINT,path:process.env.CODEX_PATH,root:process.env.OPERATOR_PROXY_ROOT};
  writeFileSync(entry,fakeBackendScript("repair",0));
  process.env.CODEX_ENTRYPOINT=entry;process.env.CODEX_PATH=process.execPath;process.env.OPERATOR_PROXY_ROOT=mkdtempSync(join(tmpdir(),"builder-repair-"));
  try {const result=await routeControlPlaneBuild({...spec,expected_base_sha:r.base},90,"repair",1,{baseSha:candidate,forceBackend:"codex_cli_openai"},r.worktree);assert.equal(result.base_sha,candidate);assert.equal(result.head_sha,currentHead(r.worktree));}
  finally {if(prior.entry===undefined)delete process.env.CODEX_ENTRYPOINT;else process.env.CODEX_ENTRYPOINT=prior.entry;if(prior.path===undefined)delete process.env.CODEX_PATH;else process.env.CODEX_PATH=prior.path;if(prior.root===undefined)delete process.env.OPERATOR_PROXY_ROOT;else process.env.OPERATOR_PROXY_ROOT=prior.root;}
});

test("base override mismatch or dirty entry fails before backend execution",async()=>{
  for(const dirty of [false,true]){
    const r=builderRepo(),candidate=advanceWorktree(r.worktree,"candidate\n"),called=join(r.source,"called.txt"),entry=join(r.source,"must-not-run.js"),prior={entry:process.env.CODEX_ENTRYPOINT,path:process.env.CODEX_PATH,root:process.env.OPERATOR_PROXY_ROOT};
    writeFileSync(entry,`require("fs").writeFileSync(${JSON.stringify(called)},"called");`);if(dirty)writeFileSync(join(r.worktree,"dirty.tmp"),"dirty");
    process.env.CODEX_ENTRYPOINT=entry;process.env.CODEX_PATH=process.execPath;process.env.OPERATOR_PROXY_ROOT=mkdtempSync(join(tmpdir(),"builder-base-deny-"));
    try {await assert.rejects(routeControlPlaneBuild({...spec,expected_base_sha:r.base},90,"repair",1,{baseSha:dirty?candidate:r.base,forceBackend:"codex_cli_openai"},r.worktree),dirty?/worktree is dirty/:/does not match clean worktree HEAD/);assert.equal(existsSync(called),false);}
    finally {if(prior.entry===undefined)delete process.env.CODEX_ENTRYPOINT;else process.env.CODEX_ENTRYPOINT=prior.entry;if(prior.path===undefined)delete process.env.CODEX_PATH;else process.env.CODEX_PATH=prior.path;if(prior.root===undefined)delete process.env.OPERATOR_PROXY_ROOT;else process.env.OPERATOR_PROXY_ROOT=prior.root;}
  }
});

test("failed backend tracked, untracked, and committed contamination is removed before fallback",async()=>{
  for(const commit of [false,true]){
    const r=builderRepo(),codex=join(r.source,`contaminate-${commit}.js`),fallback=join(r.source,`fallback-${commit}.js`),prior={entry:process.env.CODEX_ENTRYPOINT,path:process.env.CODEX_PATH,open:process.env.OPEN_CODE_PATH,root:process.env.OPERATOR_PROXY_ROOT};
    writeFileSync(codex,`const fs=require("fs"),path=require("path"),{execFileSync}=require("child_process");const correlation=process.env.OPERATOR_PROXY_PROVIDER_CORRELATION_ID;if(!correlation)process.exit(11);const a=process.argv,i=a.indexOf("-C"),cwd=a[i+1];fs.writeFileSync(path.join(cwd,"docs","x.md"),"contaminated\\n");fs.writeFileSync(path.join(cwd,"leftover.tmp"),"x");${commit?'execFileSync("git",["-C",cwd,"add","docs/x.md"]);execFileSync("git",["-C",cwd,"commit","-m","failed backend commit"]);':''}console.error("usage limit: credits exhausted");process.exit(1);`);
    writeFileSync(fallback,cleanFallbackScript(r.base,commit?"clean after commit":"clean after files"));
    process.env.CODEX_ENTRYPOINT=codex;process.env.CODEX_PATH=process.execPath;process.env.OPEN_CODE_PATH=fallback;process.env.OPERATOR_PROXY_ROOT=mkdtempSync(join(tmpdir(),"builder-clean-fallback-"));
    try {const result=await routeControlPlaneBuild({...spec,expected_base_sha:r.base},90,"x",0,{},r.worktree);assert.equal(result.builder_backend,"opencode_github_copilot");assert.equal(existsSync(join(r.worktree,"leftover.tmp")),false);assert.equal(execFileSync("git",["-C",r.worktree,"rev-parse",`${result.head_sha}^`],{encoding:"utf8"}).trim(),r.base);}
    finally {if(prior.entry===undefined)delete process.env.CODEX_ENTRYPOINT;else process.env.CODEX_ENTRYPOINT=prior.entry;if(prior.path===undefined)delete process.env.CODEX_PATH;else process.env.CODEX_PATH=prior.path;if(prior.open===undefined)delete process.env.OPEN_CODE_PATH;else process.env.OPEN_CODE_PATH=prior.open;if(prior.root===undefined)delete process.env.OPERATOR_PROXY_ROOT;else process.env.OPERATOR_PROXY_ROOT=prior.root;}
  }
});

test("failed backend newly-created ignored artifacts are removed without deleting preexisting ignored files",async()=>{
  const r=builderRepo(),codex=join(r.source,"ignored-contamination.js"),fallback=join(r.source,"ignored-fallback.js"),prior={entry:process.env.CODEX_ENTRYPOINT,path:process.env.CODEX_PATH,open:process.env.OPEN_CODE_PATH,root:process.env.OPERATOR_PROXY_ROOT};
  writeFileSync(join(r.worktree,".gitignore"),".env\n.cache/\n");execFileSync("git",["-C",r.worktree,"add",".gitignore"]);execFileSync("git",["-C",r.worktree,"commit","-m","ignore runtime artifacts"]);const base=execFileSync("git",["-C",r.worktree,"rev-parse","HEAD"],{encoding:"utf8"}).trim();
  mkdirSync(join(r.worktree,".cache"));writeFileSync(join(r.worktree,".cache","preexisting.bin"),"keep");
  writeFileSync(codex,`const fs=require("fs"),path=require("path"),a=process.argv,i=a.indexOf("-C"),cwd=a[i+1];fs.writeFileSync(path.join(cwd,".env"),"created");fs.writeFileSync(path.join(cwd,".cache","created.bin"),"created");console.error("usage limit: credits exhausted");process.exit(1);`);
  writeFileSync(fallback,`const fs=require("fs"),path=require("path"),{execFileSync}=require("child_process"),a=process.argv,i=a.indexOf("--dir"),cwd=a[i+1];const correlation=process.env.OPERATOR_PROXY_PROVIDER_CORRELATION_ID;if(!correlation)process.exit(11);if(fs.existsSync(path.join(cwd,".env"))||fs.existsSync(path.join(cwd,".cache","created.bin")))throw new Error("ignored contamination survived");if(fs.readFileSync(path.join(cwd,".cache","preexisting.bin"),"utf8")!=="keep")throw new Error("preexisting ignored artifact changed");fs.mkdirSync(path.join(cwd,"docs"),{recursive:true});fs.writeFileSync(path.join(cwd,"docs","x.md"),"clean ignored fallback\\n");execFileSync("git",["-C",cwd,"add","docs/x.md"]);execFileSync("git",["-C",cwd,"commit","-m","feat(control-plane): complete BRAIN-101-R1-SYNTHETIC-01"]);console.log("HEAD_SHA="+execFileSync("git",["-C",cwd,"rev-parse","HEAD"],{encoding:"utf8"}).trim());console.log("PROVIDER_SESSION="+correlation);`);
  process.env.CODEX_ENTRYPOINT=codex;process.env.CODEX_PATH=process.execPath;process.env.OPEN_CODE_PATH=fallback;process.env.OPERATOR_PROXY_ROOT=mkdtempSync(join(tmpdir(),"builder-ignored-fallback-"));
  try {const result=await routeControlPlaneBuild({...spec,expected_base_sha:base},90,"x",0,{},r.worktree);assert.equal(result.builder_backend,"opencode_github_copilot");assert.equal(existsSync(join(r.worktree,".env")),false);assert.equal(existsSync(join(r.worktree,".cache","created.bin")),false);assert.equal(readFileSync(join(r.worktree,".cache","preexisting.bin"),"utf8"),"keep");}
  finally {if(prior.entry===undefined)delete process.env.CODEX_ENTRYPOINT;else process.env.CODEX_ENTRYPOINT=prior.entry;if(prior.path===undefined)delete process.env.CODEX_PATH;else process.env.CODEX_PATH=prior.path;if(prior.open===undefined)delete process.env.OPEN_CODE_PATH;else process.env.OPEN_CODE_PATH=prior.open;if(prior.root===undefined)delete process.env.OPERATOR_PROXY_ROOT;else process.env.OPERATOR_PROXY_ROOT=prior.root;}
});

test("mutation or deletion of a preexisting ignored artifact blocks retry and fallback",async()=>{
  for(const mutation of ["overwrite","delete"]){
    const r=builderRepo(),codex=join(r.source,`ignored-${mutation}.js`),fallback=join(r.source,`ignored-${mutation}-fallback.js`),called=join(r.source,`ignored-${mutation}-called.txt`),prior={entry:process.env.CODEX_ENTRYPOINT,path:process.env.CODEX_PATH,open:process.env.OPEN_CODE_PATH,root:process.env.OPERATOR_PROXY_ROOT};
    writeFileSync(join(r.worktree,".gitignore"),".env\n");execFileSync("git",["-C",r.worktree,"add",".gitignore"]);execFileSync("git",["-C",r.worktree,"commit","-m","ignore runtime artifact"]);const base=execFileSync("git",["-C",r.worktree,"rev-parse","HEAD"],{encoding:"utf8"}).trim();writeFileSync(join(r.worktree,".env"),"original");
    writeFileSync(codex,`const fs=require("fs"),path=require("path"),a=process.argv,i=a.indexOf("-C"),cwd=a[i+1],target=path.join(cwd,".env");${mutation==="overwrite"?'fs.writeFileSync(target,"changed")':'fs.rmSync(target)'};console.error("usage limit: credits exhausted");process.exit(1);`);writeFileSync(fallback,`require("fs").writeFileSync(${JSON.stringify(called)},"called");process.exit(1);`);
    process.env.CODEX_ENTRYPOINT=codex;process.env.CODEX_PATH=process.execPath;process.env.OPEN_CODE_PATH=fallback;process.env.OPERATOR_PROXY_ROOT=mkdtempSync(join(tmpdir(),"builder-ignored-mutation-"));
    try {await assert.rejects(routeControlPlaneBuild({...spec,expected_base_sha:base},90,"x",0,{},r.worktree),/ignored baseline restore mismatch/);assert.equal(existsSync(called),false);}
    finally {if(prior.entry===undefined)delete process.env.CODEX_ENTRYPOINT;else process.env.CODEX_ENTRYPOINT=prior.entry;if(prior.path===undefined)delete process.env.CODEX_PATH;else process.env.CODEX_PATH=prior.path;if(prior.open===undefined)delete process.env.OPEN_CODE_PATH;else process.env.OPEN_CODE_PATH=prior.open;if(prior.root===undefined)delete process.env.OPERATOR_PROXY_ROOT;else process.env.OPERATOR_PROXY_ROOT=prior.root;}
  }
});

test("transient retry and subsequent fallback each start from the pristine baseline",async()=>{
  const r=builderRepo(),attemptFile=join(r.source,"attempt.txt"),codex=join(r.source,"retry-builder.js"),fallback=join(r.source,"retry-fallback.js"),prior={entry:process.env.CODEX_ENTRYPOINT,path:process.env.CODEX_PATH,open:process.env.OPEN_CODE_PATH,root:process.env.OPERATOR_PROXY_ROOT};
  writeFileSync(codex,`const fs=require("fs"),path=require("path"),{execFileSync}=require("child_process"),a=process.argv,i=a.indexOf("-C"),cwd=a[i+1],correlation=process.env.OPERATOR_PROXY_PROVIDER_CORRELATION_ID;if(!correlation)process.exit(11);const state=${JSON.stringify(attemptFile)},n=fs.existsSync(state)?Number(fs.readFileSync(state,"utf8")):0;const status=execFileSync("git",["-C",cwd,"status","--porcelain","--untracked-files=all"],{encoding:"utf8"}).trim();if(status)throw new Error("retry observed contamination");fs.writeFileSync(state,String(n+1));fs.mkdirSync(path.join(cwd,"docs"),{recursive:true});fs.writeFileSync(path.join(cwd,"docs","x.md"),"attempt "+(n+1)+"\\n");fs.writeFileSync(path.join(cwd,"attempt.tmp"),"x");console.error("rate limit");process.exit(1);`);
  writeFileSync(fallback,cleanFallbackScript(r.base,"fallback after retry"));
  process.env.CODEX_ENTRYPOINT=codex;process.env.CODEX_PATH=process.execPath;process.env.OPEN_CODE_PATH=fallback;process.env.OPERATOR_PROXY_ROOT=mkdtempSync(join(tmpdir(),"builder-retry-fallback-"));
  try {
    const result=await routeControlPlaneBuild({...spec,expected_base_sha:r.base},90,"x",0,{},r.worktree);
    assert.equal(readFileSync(attemptFile,"utf8"),"2");
    assert.equal(result.builder_backend,"opencode_github_copilot");
    assert.equal(existsSync(join(r.worktree,"attempt.tmp")),false);
    const events=attemptStates(process.env.OPERATOR_PROXY_ROOT!);
    assert.equal(events.filter(event=>event.state==="STARTED").length,3);
    assert.equal(events.filter(event=>event.state==="FAILED"&&event.failure_class==="RATE_LIMIT").length,2);
    assert.equal(events.at(-1)?.state,"COMPLETED");
    assert.equal(JSON.parse(readFileSync(join(process.env.OPERATOR_PROXY_ROOT!,"state","builder-attempts",spec.front_id!,"active.json"),"utf8")).state,"NONE");
  }
  finally {if(prior.entry===undefined)delete process.env.CODEX_ENTRYPOINT;else process.env.CODEX_ENTRYPOINT=prior.entry;if(prior.path===undefined)delete process.env.CODEX_PATH;else process.env.CODEX_PATH=prior.path;if(prior.open===undefined)delete process.env.OPEN_CODE_PATH;else process.env.OPEN_CODE_PATH=prior.open;if(prior.root===undefined)delete process.env.OPERATOR_PROXY_ROOT;else process.env.OPERATOR_PROXY_ROOT=prior.root;}
});

test("baseline restoration failure blocks fallback execution",async()=>{
  const r=builderRepo(),codex=join(r.source,"break-worktree.js"),fallback=join(r.source,"must-not-fallback.js"),called=join(r.source,"fallback-called.txt"),prior={entry:process.env.CODEX_ENTRYPOINT,path:process.env.CODEX_PATH,open:process.env.OPEN_CODE_PATH,root:process.env.OPERATOR_PROXY_ROOT};
  const lock=execFileSync("git",["-C",r.worktree,"rev-parse","--git-path","index.lock"],{encoding:"utf8"}).trim();
  writeFileSync(codex,`require("fs").writeFileSync(${JSON.stringify(lock)},"locked");console.error("usage limit: credits exhausted");process.exit(1);`);
  writeFileSync(fallback,`require("fs").writeFileSync(${JSON.stringify(called)},"called");process.exit(1);`);
  const provenanceRoot=mkdtempSync(join(tmpdir(),"builder-restore-deny-"));
  process.env.CODEX_ENTRYPOINT=codex;process.env.CODEX_PATH=process.execPath;process.env.OPEN_CODE_PATH=fallback;process.env.OPERATOR_PROXY_ROOT=provenanceRoot;
  try {
    await assert.rejects(routeControlPlaneBuild({...spec,expected_base_sha:r.base},90,"x",0,{},r.worktree));
    assert.equal(existsSync(called),false);
    const events=attemptStates(provenanceRoot);
    assert.deepEqual(events.map(event=>event.state),["STARTED","FAILED"]);
    assert.equal(events[1].failure_class,"CODEX_CREDIT_LIMIT");
    assert.equal(JSON.parse(readFileSync(join(provenanceRoot,"state","builder-attempts",spec.front_id!,"active.json"),"utf8")).state,"NONE");
  }
  finally {rmSync(lock,{force:true});if(prior.entry===undefined)delete process.env.CODEX_ENTRYPOINT;else process.env.CODEX_ENTRYPOINT=prior.entry;if(prior.path===undefined)delete process.env.CODEX_PATH;else process.env.CODEX_PATH=prior.path;if(prior.open===undefined)delete process.env.OPEN_CODE_PATH;else process.env.OPEN_CODE_PATH=prior.open;if(prior.root===undefined)delete process.env.OPERATOR_PROXY_ROOT;else process.env.OPERATOR_PROXY_ROOT=prior.root;}
});

test("failed backend cleanup removes a newly-created ignored directory tree before fallback",async()=>{
  const r=builderRepo(),codex=join(r.source,"ignored-tree.js"),fallback=join(r.source,"ignored-tree-fallback.js"),prior={entry:process.env.CODEX_ENTRYPOINT,path:process.env.CODEX_PATH,open:process.env.OPEN_CODE_PATH,root:process.env.OPERATOR_PROXY_ROOT};
  writeFileSync(join(r.worktree,".gitignore"),".opencode/\n");execFileSync("git",["-C",r.worktree,"add",".gitignore"]);execFileSync("git",["-C",r.worktree,"commit","-m","ignore OpenCode runtime artifacts"]);const base=currentHead(r.worktree);
  writeFileSync(codex,`const fs=require("fs"),path=require("path"),correlation=process.env.OPERATOR_PROXY_PROVIDER_CORRELATION_ID;if(!correlation)process.exit(11);const a=process.argv,i=a.indexOf("-C"),cwd=a[i+1],leaf=path.join(cwd,".opencode","node_modules","pkg","dist","core");fs.mkdirSync(leaf,{recursive:true});fs.writeFileSync(path.join(leaf,"index.js"),"created");console.error("usage limit: credits exhausted");process.exit(1);`);
  writeFileSync(fallback,`const fs=require("fs"),path=require("path"),{execFileSync}=require("child_process");const correlation=process.env.OPERATOR_PROXY_PROVIDER_CORRELATION_ID;if(!correlation)process.exit(11);const a=process.argv,i=a.indexOf("--dir"),cwd=a[i+1];if(fs.existsSync(path.join(cwd,".opencode")))throw new Error("ignored directory tree survived");fs.mkdirSync(path.join(cwd,"docs"),{recursive:true});fs.writeFileSync(path.join(cwd,"docs","x.md"),"clean ignored tree fallback\\n");execFileSync("git",["-C",cwd,"add","docs/x.md"]);execFileSync("git",["-C",cwd,"commit","-m","feat(control-plane): complete BRAIN-101-R1-SYNTHETIC-01"]);console.log("HEAD_SHA="+execFileSync("git",["-C",cwd,"rev-parse","HEAD"],{encoding:"utf8"}).trim());console.log("PROVIDER_SESSION="+correlation);`);
  process.env.CODEX_ENTRYPOINT=codex;process.env.CODEX_PATH=process.execPath;process.env.OPEN_CODE_PATH=fallback;process.env.OPERATOR_PROXY_ROOT=mkdtempSync(join(tmpdir(),"builder-ignored-tree-"));
  try {const result=await routeControlPlaneBuild({...spec,expected_base_sha:base},90,"x",0,{},r.worktree);assert.equal(result.builder_backend,"opencode_github_copilot");assert.equal(existsSync(join(r.worktree,".opencode")),false);}
  finally {if(prior.entry===undefined)delete process.env.CODEX_ENTRYPOINT;else process.env.CODEX_ENTRYPOINT=prior.entry;if(prior.path===undefined)delete process.env.CODEX_PATH;else process.env.CODEX_PATH=prior.path;if(prior.open===undefined)delete process.env.OPEN_CODE_PATH;else process.env.OPEN_CODE_PATH=prior.open;if(prior.root===undefined)delete process.env.OPERATOR_PROXY_ROOT;else process.env.OPERATOR_PROXY_ROOT=prior.root;}
});
