import test from "node:test";
import assert from "node:assert/strict";
import {existsSync,mkdtempSync,mkdirSync,readdirSync,readFileSync,writeFileSync} from "node:fs";
import {tmpdir} from "node:os";
import {join} from "node:path";
import {pathToFileURL} from "node:url";
import {spawn} from "node:child_process";
import {Ledger} from "../../../scripts/operator_proxy/decision_ledger.js";
import {GitHubBus} from "../../../scripts/operator_proxy/github_bus.js";
import {execute,reconcileAuthorizationComment} from "../../../scripts/operator_proxy/action_executor.js";

const head="b".repeat(40),base="a".repeat(40),key="e".repeat(64),id="eeeeeeee-eeee-4eee-aeee-eeeeeeeeeeee";
const decision=(policy="APPROVE")=>({schema_version:2 as const,decision_key:key,decision_id:id,authorization_id:"CESAR-BRAIN-101-OPERATOR-PROXY-20260722-01",repository:"cesarmanuel8102/AI_Vault",issue:63,pr:63,base_sha:base,head_sha:head,roadmap_id:"BRAIN-101",roadmap_item_id:"R1.1",risk:"LOW" as const,deterministic_gate:"PASS" as const,codex_review:"PASS" as const,review_findings_count:0,review_consistent:true,policy_decision:policy as any,allowed_action:policy==="APPROVE"?"MERGE" as const:"NONE" as const,policy_sha256:"c".repeat(64),evidence_sha256:"d".repeat(64),created_utc:"2026-07-27T00:00:00.000Z"});
const lines=(path:string)=>readFileSync(path,"utf8").trim().split(/\r?\n/).filter(Boolean);

test("identical retries create one decision and one policy event for every outcome",()=>{
  for(const outcome of ["APPROVE","REPAIR","BLOCK","ESCALATE_TO_OWNER"]){const root=mkdtempSync(join(tmpdir(),"decision-retry-"));const ledger=new Ledger(root);const d={...decision(outcome),decision_key:key.slice(0,63)+String(outcome.length%10)};const first=ledger.recordOrLoad(d),second=ledger.recordOrLoad(d);assert.equal(first.created,true);assert.equal(second.created,false);assert.equal(first.decision.decision_id,second.decision.decision_id);assert.equal(readdirSync(root).filter(x=>x.startsWith("decision-")).length,1);assert.equal(lines(join(root,"events.jsonl")).filter(x=>x.includes("operator_policy_")).length,1);}
});

test("two processes claim one decision and execute the factory once",async()=>{
  const root=mkdtempSync(join(tmpdir(),"decision-concurrent-")),counter=join(root,"reviewer-count.txt"),moduleUrl=pathToFileURL(join(process.cwd(),"decision_ledger.ts")).href,d=decision();
  const source=`import {appendFileSync} from 'node:fs';import {Ledger} from ${JSON.stringify(moduleUrl)};const d=${JSON.stringify(d)};new Ledger(${JSON.stringify(root)}).loadOrCreate(d.decision_key,()=>{appendFileSync(${JSON.stringify(counter)},'review\\n');Atomics.wait(new Int32Array(new SharedArrayBuffer(4)),0,0,100);return d;});`;
  const run=()=>new Promise<number>((resolve,reject)=>{const child=spawn(process.execPath,["--import","tsx","--input-type=module","--eval",source],{cwd:process.cwd(),stdio:"pipe"});let stderr="";child.stderr.on("data",x=>stderr+=x);child.on("error",reject);child.on("exit",code=>code===0?resolve(0):reject(new Error(stderr)));});
  await Promise.all([run(),run()]);assert.equal(lines(counter).length,1);assert.equal(readdirSync(root).filter(x=>x.startsWith("decision-")).length,1);assert.equal(lines(join(root,"events.jsonl")).length,1);
});

test("crash after reviewer reuses the same review receipt",()=>{
  const root=mkdtempSync(join(tmpdir(),"review-retry-"));let reviews=0;const first=new Ledger(root).loadOrCreateReview(key,()=>{reviews++;return {issue:63,pr:63,base_sha:base,head_sha:head,verdict:"PASS"};});assert.equal(first.created,true);const resumed=new Ledger(root).loadOrCreateReview(key,()=>{reviews++;return {issue:63,pr:63,base_sha:base,head_sha:head,verdict:"BLOCKED"};});assert.equal(resumed.created,false);assert.equal(resumed.review.verdict,"PASS");assert.equal(reviews,1);
});

test("cached review receipt is validated before reuse",()=>{
  const root=mkdtempSync(join(tmpdir(),"review-validation-")),ledger=new Ledger(root);ledger.loadOrCreateReview(key,()=>({head_sha:head,verdict:"PASS"}));
  let factoryCalls=0;assert.throws(()=>ledger.loadOrCreateReview(key,()=>{factoryCalls++;return {head_sha:head,verdict:"PASS"};},value=>{if(value.head_sha!==base)throw new Error("cached review binding mismatch");}),/cached review binding mismatch/);assert.equal(factoryCalls,0);
});

test("legacy empty and crashed review claims recover through append-only epochs",async()=>{
  const legacyRoot=mkdtempSync(join(tmpdir(),"review-legacy-"));mkdirSync(join(legacyRoot,`claim-review-${key}`));let legacyCalls=0;
  const legacy=new Ledger(legacyRoot).loadOrCreateReview(key,()=>{legacyCalls++;return {issue:63,pr:63,base_sha:base,head_sha:head,verdict:"PASS"};});
  assert.equal(legacy.created,true);assert.equal(legacyCalls,1);

  const root=mkdtempSync(join(tmpdir(),"review-crash-")),signal=join(root,"factory-entered"),moduleUrl=pathToFileURL(join(process.cwd(),"decision_ledger.ts")).href;
  const source=`import {writeFileSync} from 'node:fs';import {Ledger} from ${JSON.stringify(moduleUrl)};new Ledger(${JSON.stringify(root)}).loadOrCreateReview(${JSON.stringify(key)},()=>{writeFileSync(${JSON.stringify(signal)},'entered');Atomics.wait(new Int32Array(new SharedArrayBuffer(4)),0,0,60000);return {verdict:'PASS'};});`;
  const child=spawn(process.execPath,["--import","tsx","--input-type=module","--eval",source],{cwd:process.cwd(),stdio:"pipe"});
  for(let attempt=0;attempt<100&&!existsSync(signal);attempt++)await new Promise(resolve=>setTimeout(resolve,20));
  assert.equal(existsSync(signal),true);child.kill();await new Promise<void>((resolve,reject)=>{child.once("exit",()=>resolve());child.once("error",reject);});
  let resumedCalls=0;const resumed=new Ledger(root).loadOrCreateReview(key,()=>{resumedCalls++;return {issue:63,pr:63,base_sha:base,head_sha:head,verdict:"PASS"};});
  assert.equal(resumed.created,true);assert.equal(resumedCalls,1);assert.equal(resumed.review.verdict,"PASS");
  const entries=readdirSync(join(root,`claim-review-${key}`));assert.equal(entries.filter(name=>name.endsWith(".json")&&!name.includes("release")).length,2);assert.equal(entries.filter(name=>name.endsWith(".release.json")).length,1);
});

test("incompatible, corrupt, and duplicate historical decisions fail closed",()=>{
  const root=mkdtempSync(join(tmpdir(),"decision-conflict-")),ledger=new Ledger(root),d=decision();ledger.record(d);assert.throws(()=>ledger.recordOrLoad({...d,evidence_sha256:"f".repeat(64)}),/DECISION_IDENTITY_CONFLICT/);
  const corrupt=mkdtempSync(join(tmpdir(),"decision-corrupt-"));writeFileSync(join(corrupt,`decision-${key}.json`),"{");assert.throws(()=>new Ledger(corrupt).findByKey(key),/corrupt/);
  const duplicate=mkdtempSync(join(tmpdir(),"decision-duplicate-"));const a={...d,decision_key:"1".repeat(64)},b={...d,decision_key:"2".repeat(64),decision_id:"22222222-2222-4222-a222-222222222222"};writeFileSync(join(duplicate,`decision-${a.decision_key}.json`),JSON.stringify(a));writeFileSync(join(duplicate,`decision-${b.decision_key}.json`),JSON.stringify(b));assert.throws(()=>new Ledger(duplicate).findByHead(head),/duplicate decisions/);
});

test("decision comments and labels reconcile without duplicates",()=>{
  const bus=new GitHubBus("gh");let comments:string[]=[],labels=["operator:queued"],mutations=0;bus.setMutationGuard(()=>{});(bus as any).call=(args:string[])=>{mutations++;if(args.includes("--body"))comments.push(args[args.indexOf("--body")+1]);if(args.includes("--remove-label"))labels=labels.filter(x=>x!==args[args.indexOf("--remove-label")+1]);if(args.includes("--add-label"))labels.push(args[args.indexOf("--add-label")+1]);return "";};(bus as any).json=(args:string[])=>args.includes("comments")?{comments:comments.map(body=>({body}))}:{labels:labels.map(name=>({name}))};const marker=`decision_key=${key}`;bus.commentOnce("pr",63,marker,`${marker}\nbody`);bus.commentOnce("pr",63,marker,`${marker}\nbody`);bus.reconcileLabel("issue",63,"operator:completed",["operator:queued"]);bus.reconcileLabel("issue",63,"operator:completed",["operator:queued"]);assert.equal(comments.length,1);assert.deepEqual(labels,["operator:completed"]);assert.equal(mutations,3);
});

test("post-merge retry creates one receipt and one authorization comment",()=>{
  const root=mkdtempSync(join(tmpdir(),"decision-merge-")),ledger=new Ledger(root),d=decision();ledger.record(d);let comments=0,published=false;const bus:any={json:()=>({state:"MERGED"}),verifyMerged:()=>"f".repeat(40),commentOnce:()=>{if(published)return false;published=true;comments++;return true;}};execute(bus,ledger,d,false);reconcileAuthorizationComment(bus,d);execute(bus,ledger,d,false);reconcileAuthorizationComment(bus,d);assert.equal(lines(join(root,"events.jsonl")).filter(x=>x.includes("supervisor_authorization_consumed")).length,1);assert.equal(comments,1);assert.equal(readFileSync(join(root,`head-${head}.done`),"utf8"),id);
});

test("merge workflow dispatch is reused after a retry",()=>{
  const bus=new GitHubBus("gh");let dispatches=0;const run={databaseId:1,displayTitle:`operator-proxy-merge-${id}`,status:"completed",conclusion:"success"};bus.setMutationGuard(()=>{});(bus as any).json=(args:string[])=>args[0]==="run"?(dispatches?[run]:[]):{baseRefName:"codex/own-capital-sustainable-return",baseRefOid:base,headRefOid:head,isDraft:true,state:"OPEN",mergeable:"MERGEABLE"};(bus as any).call=(args:string[])=>{if(args[0]==="workflow")dispatches++;return "";};(bus as any).verifyMerged=()=>"f".repeat(40);bus.merge(63,head,base,id);bus.merge(63,head,base,id);assert.equal(dispatches,1);
});
