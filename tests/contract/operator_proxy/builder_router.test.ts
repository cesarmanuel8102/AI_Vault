import test from "node:test";
import assert from "node:assert/strict";
import {execFileSync} from "node:child_process";
import {mkdirSync,mkdtempSync,writeFileSync} from "node:fs";
import {tmpdir} from "node:os";
import {join,resolve} from "node:path";
import {routeControlPlaneBuild,listBuilderBackendHealth} from "../../../scripts/operator_proxy/builder_router.js";
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
  return `const fs=require("fs"),path=require("path"),{execFileSync}=require("child_process");function isWorktreeRoot(d){if(!d)return false;try{execFileSync(process.env.GIT_PATH||"git",["-C",d,"rev-parse","--is-inside-work-tree"],{stdio:"pipe",timeout:10000});return true;}catch{return false;}}function findWorktree(a){let idx=a.indexOf("-C");if(idx<0)idx=a.indexOf("--dir");if(idx>=0){const d=a[idx+1];if(isWorktreeRoot(d))return d;}for(let i=a.length-1;i>=2;i--){const d=a[i];if(isWorktreeRoot(d))return d;}return process.cwd();}const cwd=findWorktree(process.argv);fs.mkdirSync(path.join(cwd,"docs"),{recursive:true});fs.writeFileSync(path.join(cwd,"docs","x.md"),"${mark} build\\n");execFileSync(process.env.GIT_PATH||"git",["-C",cwd,"add","docs/x.md"]);execFileSync(process.env.GIT_PATH||"git",["-C",cwd,"commit","-m","feat(control-plane): complete BRAIN-101-R1-SYNTHETIC-01"]);const head=execFileSync(process.env.GIT_PATH||"git",["-C",cwd,"rev-parse","HEAD"],{encoding:"utf8"}).trim();console.log("HEAD_SHA="+head);process.exit(${exitCode});`;
}

function currentHead(cwd:string){
  return execFileSync("git",["-C",cwd,"rev-parse","HEAD"],{encoding:"utf8"}).trim();
}

test("primary Codex backend succeeds and reports codex_cli_openai",async()=>{
  const r=builderRepo();
  const entry=join(r.source,"fake-codex.js");
  const priorEntry=process.env.CODEX_ENTRYPOINT;
  const priorPath=process.env.CODEX_PATH;
  const priorRoot=process.env.OPERATOR_PROXY_ROOT;
  writeFileSync(entry,fakeBackendScript("codex",0));
  process.env.CODEX_ENTRYPOINT=entry;
  process.env.CODEX_PATH=process.execPath;
  process.env.OPERATOR_PROXY_ROOT=mkdtempSync(join(tmpdir(),"builder-health-"));
  try{
    const result=await routeControlPlaneBuild({...spec,expected_base_sha:r.base},90,"x",0,{},r.worktree);
    assert.equal(result.builder_backend,"codex_cli_openai");
    assert.equal(result.head_sha,currentHead(r.worktree));
    assert.equal(execFileSync("git",["-C",r.worktree,"show",`${result.head_sha}:docs/x.md`],{encoding:"utf8"}),"codex build\n");
  }finally{
    if(priorEntry===undefined)delete process.env.CODEX_ENTRYPOINT;else process.env.CODEX_ENTRYPOINT=priorEntry;
    if(priorPath===undefined)delete process.env.CODEX_PATH;else process.env.CODEX_PATH=priorPath;
    if(priorRoot===undefined)delete process.env.OPERATOR_PROXY_ROOT;else process.env.OPERATOR_PROXY_ROOT=priorRoot;
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
  writeFileSync(entry,`const fs=require("fs"),path=require("path"),{execFileSync}=require("child_process");${isWorktree}${findWorktree}const cwd=findWorktree(process.argv);fs.mkdirSync(path.join(cwd,"docs"),{recursive:true});fs.writeFileSync(path.join(cwd,"docs","y.md"),"out of scope\\n");execFileSync(process.env.GIT_PATH||"git",["-C",cwd,"add","docs/y.md"]);execFileSync(process.env.GIT_PATH||"git",["-C",cwd,"commit","-m","feat(control-plane): complete BRAIN-101-R1-SYNTHETIC-01"]);const head=execFileSync(process.env.GIT_PATH||"git",["-C",cwd,"rev-parse","HEAD"],{encoding:"utf8"}).trim();console.log("HEAD_SHA="+head);`);
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
    await assert.rejects(routeControlPlaneBuild({...spec,expected_base_sha:r.base},90,"x",0,{},r.worktree),/OPERATOR_PROXY_ROOT is required/);
    process.env.OPERATOR_PROXY_ROOT="relative-root";
    await assert.rejects(routeControlPlaneBuild({...spec,expected_base_sha:r.base},90,"x",0,{},r.worktree),/OPERATOR_PROXY_ROOT must be absolute/);
  }finally{if(prior===undefined)delete process.env.OPERATOR_PROXY_ROOT;else process.env.OPERATOR_PROXY_ROOT=prior;}
});

test("health ledger failure does not block eligible fallback",async()=>{
  const r=builderRepo(),codexEntry=join(r.source,"fake-codex-credit.js"),opencodeEntry=join(r.source,"fake-opencode.js"),rootFile=join(r.root,"root-file");
  const priorCodexEntry=process.env.CODEX_ENTRYPOINT,priorCodexPath=process.env.CODEX_PATH,priorOpenCode=process.env.OPEN_CODE_PATH,priorRoot=process.env.OPERATOR_PROXY_ROOT;
  writeFileSync(codexEntry,`console.error("usage limit: credits exhausted");process.exit(1);`);
  writeFileSync(opencodeEntry,fakeBackendScript("health fallback",0));
  writeFileSync(rootFile,"not a directory\n");
  process.env.CODEX_ENTRYPOINT=codexEntry;process.env.CODEX_PATH=process.execPath;process.env.OPEN_CODE_PATH=opencodeEntry;process.env.OPERATOR_PROXY_ROOT=rootFile;
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
