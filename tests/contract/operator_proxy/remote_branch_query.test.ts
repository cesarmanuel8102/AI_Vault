import test from "node:test";import assert from "node:assert/strict";
import {queryOptionalBranchRef} from "../../../scripts/operator_proxy/github_bus.js";

const repo="cesarmanuel8102/AI_Vault",branch="control-plane/verified-branch",sha="a".repeat(40);
const headers=(status:number,body:unknown,extra="")=>`HTTP/2.0 ${status} ${status===200?"OK":"Error"}\r\nContent-Type: application/json; charset=utf-8\r\nX-GitHub-Request-Id: TEST:123\r\n${extra}\r\n${typeof body==="string"?body:JSON.stringify(body)}`;
const result=(status:number,http:number,body:unknown,patch:Record<string,unknown>={})=>({status,signal:null,stdout:headers(http,body),stderr:"",...patch});
const run=(value:any)=>(file:string,args:readonly string[])=>{assert.equal(file,"gh");assert.deepEqual(args,["api","--include","repos/cesarmanuel8102/AI_Vault/git/ref/heads/control-plane/verified-branch"]);return value;};

test("verified HTTP 200 returns only the exact branch SHA",()=>assert.equal(queryOptionalBranchRef("gh",repo,branch,run(result(0,200,{ref:`refs/heads/${branch}`,object:{sha}}))),sha));
test("verified HTTP 404 with gh failure status is the only absence result",()=>assert.equal(queryOptionalBranchRef("gh",repo,branch,run(result(1,404,{message:"Not Found"}))),undefined));

for(const code of [401,403,429,500])test(`HTTP ${code} fails closed`,()=>assert.throws(()=>queryOptionalBranchRef("gh",repo,branch,run(result(1,code,{message:code===500?"Not Found":"failure"})))));
test("timeout fails closed",()=>assert.throws(()=>queryOptionalBranchRef("gh",repo,branch,run({status:null,signal:null,stdout:"",stderr:"",error:Object.assign(new Error("timeout"),{code:"ETIMEDOUT"})}))));
test("signal termination fails closed",()=>assert.throws(()=>queryOptionalBranchRef("gh",repo,branch,run({status:null,signal:"SIGTERM",stdout:"",stderr:""}))));
test("missing gh executable fails closed",()=>assert.throws(()=>queryOptionalBranchRef("gh",repo,branch,run({status:null,signal:null,stdout:"",stderr:"",error:Object.assign(new Error("missing"),{code:"ENOENT"})}))));
for(const label of ["auth","network"])test(`${label} process error fails closed`,()=>assert.throws(()=>queryOptionalBranchRef("gh",repo,branch,run({status:1,signal:null,stdout:"",stderr:`${label} failure`}))));
test("malformed headers fail closed",()=>assert.throws(()=>queryOptionalBranchRef("gh",repo,branch,run({status:0,signal:null,stdout:`HTTP 200\r\n\r\n{}`,stderr:""}))));
test("HTTP 200 without body fails closed",()=>assert.throws(()=>queryOptionalBranchRef("gh",repo,branch,run({status:0,signal:null,stdout:headers(200,""),stderr:""}))));
test("HTTP 200 with invalid JSON fails closed",()=>assert.throws(()=>queryOptionalBranchRef("gh",repo,branch,run(result(0,200,"{")))));
test("HTTP 200 with invalid SHA fails closed",()=>assert.throws(()=>queryOptionalBranchRef("gh",repo,branch,run(result(0,200,{ref:`refs/heads/${branch}`,object:{sha:"bad"}})))));
test("free-text 404 without included HTTP status fails closed",()=>assert.throws(()=>queryOptionalBranchRef("gh",repo,branch,run({status:1,signal:null,stdout:"",stderr:"gh: Not Found (HTTP 404)"}))));
test("HTTP 500 body saying Not Found fails closed",()=>assert.throws(()=>queryOptionalBranchRef("gh",repo,branch,run(result(1,500,{message:"Not Found"})))));
test("HTTP 404 printed by a successful process fails closed",()=>assert.throws(()=>queryOptionalBranchRef("gh",repo,branch,run(result(0,404,{message:"Not Found"})))));
test("nonzero process with empty stderr fails closed",()=>assert.throws(()=>queryOptionalBranchRef("gh",repo,branch,run({status:1,signal:null,stdout:"",stderr:""}))));
test("HTTP 404 carrying a SHA fails closed",()=>assert.throws(()=>queryOptionalBranchRef("gh",repo,branch,run(result(1,404,{object:{sha}})))));
for(const invalid of ["","lower space","control-plane/../x","control-plane//x","control-plane/x.lock","control-plane/x\narg","control-plane/x?arg"])test(`unsafe branch is rejected: ${JSON.stringify(invalid)}`,()=>assert.throws(()=>queryOptionalBranchRef("gh",repo,invalid,()=>{throw new Error("runner must not execute");})));
