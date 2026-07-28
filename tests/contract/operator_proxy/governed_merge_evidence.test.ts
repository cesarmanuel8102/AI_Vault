import test from "node:test";
import assert from "node:assert/strict";
import {execFileSync} from "node:child_process";
import {mkdtempSync, writeFileSync} from "node:fs";
import {tmpdir} from "node:os";
import {join, resolve} from "node:path";

const base="a".repeat(40), head="b".repeat(40);
const required=["Phase 1 baseline (Windows)","Security Smoke Tests","Dashboard / Trace Tests","Memory / Retrieval Regression","Roadmap / Policy Regression","Agent V2 Boundary Contracts","Financial Autonomy Dry-Run Contract","Hygiene Guard"];
const python=process.platform==="win32"?"python":"python3";
const verifier=resolve("verify_governed_merge_evidence.py");
const goodPr=()=>({baseRefOid:base,headRefOid:head,headRefName:"control-plane/e2e",state:"OPEN",isDraft:true,mergeable:"MERGEABLE",statusCheckRollup:[...required.map(name=>({name,status:"COMPLETED",conclusion:"SUCCESS"})),...['deterministic','codex','publish'].map(name=>({name,status:"COMPLETED",conclusion:"SKIPPED"}))]});
const goodRun=()=>({headSha:head,workflowName:"Brain Agent V2 Hygiene",event:"workflow_dispatch",status:"completed",conclusion:"success",createdAt:"2026-07-28T18:10:04Z"});

function invoke(pr:any,runs:any[]){const root=mkdtempSync(join(tmpdir(),"merge-evidence-")),prPath=join(root,"pr.json"),runsPath=join(root,"runs.json");writeFileSync(prPath,JSON.stringify(pr));writeFileSync(runsPath,JSON.stringify(runs));return execFileSync(python,[verifier,"--pr-json",prPath,"--hygiene-runs-json",runsPath,"--expected-base",base,"--expected-head",head],{encoding:"utf8"});}

test("accepts latest successful workflow-dispatch hygiene evidence bound to exact head",()=>assert.equal(invoke(goodPr(),[goodRun()]),""));
test("fails closed without exact-head hygiene evidence",()=>assert.throws(()=>invoke(goodPr(),[{...goodRun(),headSha:"c".repeat(40)}]),/exact-head hygiene evidence missing/));
test("fails closed when latest exact-head hygiene run is not successful",()=>assert.throws(()=>invoke(goodPr(),[{...goodRun(),conclusion:"failure"},goodRun()]),/latest exact-head hygiene run not successful/));
test("fails closed for non-dispatch hygiene evidence",()=>assert.throws(()=>invoke(goodPr(),[{...goodRun(),event:"pull_request"}]),/latest exact-head hygiene run not successful/));
test("accepts attached successful hygiene check without external run",()=>{const pr=goodPr();pr.statusCheckRollup.push({name:"Brain Agent V2 Hygiene Baseline",status:"COMPLETED",conclusion:"SUCCESS"});assert.equal(invoke(pr,[]),"");});
test("accepts skipped attached hygiene only after exact-head fallback succeeds",()=>{const pr=goodPr();pr.statusCheckRollup.push({name:"Brain Agent V2 Hygiene Baseline",status:"COMPLETED",conclusion:"SKIPPED"});assert.equal(invoke(pr,[goodRun()]),"");});
test("does not override failed attached hygiene with fallback evidence",()=>{const pr=goodPr();pr.statusCheckRollup.push({name:"Brain Agent V2 Hygiene Baseline",status:"COMPLETED",conclusion:"FAILURE"});assert.throws(()=>invoke(pr,[goodRun()]),/attached hygiene check not successful/);});
test("preserves exact PR identity and required check gates",()=>{for(const pr of [{...goodPr(),headRefOid:"c".repeat(40)},{...goodPr(),isDraft:false},{...goodPr(),mergeable:"CONFLICTING"},(()=>{const p=goodPr();p.statusCheckRollup=p.statusCheckRollup.filter((x:any)=>x.name!==required[0]);return p;})()])assert.throws(()=>invoke(pr,[goodRun()]));});
