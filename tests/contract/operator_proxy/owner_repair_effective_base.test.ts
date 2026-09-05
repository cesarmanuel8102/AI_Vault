import test from "node:test";
import assert from "node:assert/strict";
import {appendFileSync,mkdtempSync,readFileSync} from "node:fs";
import {spawnSync} from "node:child_process";
import {tmpdir} from "node:os";
import {join} from "node:path";
import {pathToFileURL} from "node:url";
import {OwnerRepairEffectiveBaseLedger} from "../../../scripts/operator_proxy/owner_repair_effective_base.js";
import {OwnerRepairReceiptLedger} from "../../../scripts/operator_proxy/owner_repair_receipt_ledger.js";
import type {OwnerAuthorizedPayloadRepairGrant} from "../../../scripts/operator_proxy/types.js";

const CANONICAL_BRANCH="codex/own-capital-sustainable-return";
const sha40=(character:string)=>character.repeat(40);
const sha64=(character:string)=>character.repeat(64);

function grant(front_id="BRAIN-101-R3-EFFECTIVE-BASE-01",grant_key=sha64("a")):OwnerAuthorizedPayloadRepairGrant {
  return {schema_version:1,authorization_id:"CESAR-BRAIN-101-OPERATOR-PROXY-20260722-01",grant_key,owner_principal:"cesarmanuel8102",repository:"cesarmanuel8102/AI_Vault",roadmap_id:"BRAIN-101",roadmap_item_id:"R3.4",front_id,issue:248,pr:249,work_branch:"control-plane/effective-base",canonical_base_sha:sha40("b"),failed_head_sha:sha40("c"),eligible_failure_class:"CI_FAILED",max_extra_builds:1,correction_payload:{schema_version:1,requirements:[{requirement_id:"repair",instruction:"Apply only the approved correction."}],preserved_invariants:["HUMAN_FINAL_AUTHORITY"]},correction_payload_sha256:sha64("d"),owner_comment_id:"5000000001",authorization_body_sha256:sha64("e")};
}

function setup(){
  const root=mkdtempSync(join(tmpdir(),"owner-effective-base-"));
  const receipts=new OwnerRepairReceiptLedger(join(root,"receipts"));
  const value=grant();
  receipts.appendVerified(value);const consumed=receipts.consume(value.grant_key),dispatched=receipts.markBuildDispatched(value.grant_key);
  return {root,receipts,grant:value,consumed,dispatched,ledger:new OwnerRepairEffectiveBaseLedger(join(root,"bindings"))};
}

function input(fixture:ReturnType<typeof setup>,effective_base_sha=sha40("d")){
  return {grant_key:fixture.grant.grant_key,front_id:fixture.grant.front_id,authorization_id:fixture.grant.authorization_id,build_attempt_id:fixture.consumed.build_attempt_id!,frozen_base_sha:fixture.grant.canonical_base_sha,effective_base_sha,failed_head_sha:fixture.grant.failed_head_sha,build_dispatched_event_sha256:fixture.dispatched.event_sha256,canonical_branch:CANONICAL_BRANCH,installed_runtime_sha:effective_base_sha,predecessor_event_sha256:fixture.dispatched.event_sha256};
}

function evidence(fixture:ReturnType<typeof setup>,currentTip=sha40("d"),doctorPassed=true){
  return {receipts:fixture.receipts,currentTip,installedRuntimeSha:currentTip,doctorPassed,isAncestor:(older:string,newer:string)=>older===newer||older===fixture.grant.canonical_base_sha&&[fixture.grant.canonical_base_sha,sha40("d"),sha40("e")].includes(newer)};
}

function appendLegacySecondConsumption(fixture:ReturnType<typeof setup>){
  const second=grant(fixture.grant.front_id,sha64("f")),legacy=new OwnerRepairReceiptLedger(join(fixture.root,"legacy-receipts"));
  legacy.appendVerified(second);const consumed=legacy.consume(second.grant_key),dispatched=legacy.markBuildDispatched(second.grant_key);
  appendFileSync(join(fixture.receipts.root,"owner-repair-receipts.jsonl"),readFileSync(join(legacy.root,"owner-repair-receipts.jsonl"),"utf8"));
  return {second,consumed,dispatched};
}

test("binds a frozen base to the current canonical tip without changing existing receipts",()=>{
  const fixture=setup(),before=readFileSync(join(fixture.receipts.root,"owner-repair-receipts.jsonl"),"utf8"),binding=fixture.ledger.bind(input(fixture),evidence(fixture));
  assert.equal(binding.schema_version,1);assert.equal(binding.frozen_base_sha,fixture.grant.canonical_base_sha);assert.equal(binding.effective_base_sha,sha40("d"));assert.equal(binding.build_dispatched_event_sha256,fixture.dispatched.event_sha256);assert.equal(binding.predecessor_event_sha256,fixture.dispatched.event_sha256);assert.match(binding.event_sha256,/^[0-9a-f]{64}$/);
  assert.deepEqual(fixture.ledger.load(fixture.grant.grant_key),binding);
  assert.equal(readFileSync(join(fixture.receipts.root,"owner-repair-receipts.jsonl"),"utf8"),before);
});

test("binds zero, one, or many legitimate canonical descendants",()=>{
  for(const tip of [sha40("b"),sha40("d"),sha40("e")]){const fixture=setup(),binding=fixture.ledger.bind(input(fixture,tip),evidence(fixture,tip));assert.equal(binding.effective_base_sha,tip);}
});

test("rejects unrelated bases, runtime drift, and a failed doctor before appending",()=>{
  const unrelated=setup();assert.throws(()=>unrelated.ledger.bind(input(unrelated,sha40("f")),evidence(unrelated,sha40("f"))),/effective base/i);assert.equal(unrelated.ledger.load(unrelated.grant.grant_key),undefined);
  const runtime=setup();const wrongRuntime={...evidence(runtime),installedRuntimeSha:sha40("e")};assert.throws(()=>runtime.ledger.bind(input(runtime),wrongRuntime),/runtime/i);
  const doctor=setup();assert.throws(()=>doctor.ledger.bind(input(doctor),evidence(doctor,sha40("d"),false)),/doctor/i);
});

test("retries the exact binding through HEAD_BOUND but rejects a moving canonical tip",()=>{
  const fixture=setup(),first=fixture.ledger.bind(input(fixture),evidence(fixture));
  fixture.receipts.bindHead(fixture.grant.grant_key,sha40("f"));
  assert.deepEqual(fixture.ledger.bind(input(fixture),evidence(fixture)),first);
  assert.throws(()=>fixture.ledger.bind(input(fixture),evidence(fixture,sha40("e"))),/effective base|binding/i);
  assert.throws(()=>fixture.ledger.bind(input(fixture,sha40("e")),evidence(fixture,sha40("e"))),/conflict/i);
});

test("rejects first binding after HEAD_BOUND while permitting only an existing binding replay",()=>{
  const fixture=setup();
  fixture.receipts.bindHead(fixture.grant.grant_key,sha40("f"));
  assert.throws(()=>fixture.ledger.bind(input(fixture),evidence(fixture)),/first binding.*dispatched/i);
  assert.equal(fixture.ledger.load(fixture.grant.grant_key),undefined);
});

test("rejects changed grant, attempt, and dispatch anchors after a crash retry",()=>{
  const fixture=setup();fixture.ledger.bind(input(fixture),evidence(fixture));
  assert.throws(()=>fixture.ledger.bind({...input(fixture),grant_key:sha64("f")},evidence(fixture)));
  assert.throws(()=>fixture.ledger.bind({...input(fixture),build_attempt_id:sha64("f")},evidence(fixture)));
  assert.throws(()=>fixture.ledger.bind({...input(fixture),build_dispatched_event_sha256:sha64("f"),predecessor_event_sha256:sha64("f")},evidence(fixture)),/dispatch|binding/i);
});

test("requires the real dispatched receipt and preserves the one-consumption rule",()=>{
  const fixture=setup(),second=grant(fixture.grant.front_id,sha64("f"));
  fixture.receipts.appendVerified(second);assert.throws(()=>fixture.receipts.consume(second.grant_key),/owner exception.*consumed|receipt/i);
  const wrong={...input(fixture),predecessor_event_sha256:fixture.consumed.event_sha256};assert.throws(()=>fixture.ledger.bind(wrong,evidence(fixture)));
  const noDispatch=setup();const incomplete=new OwnerRepairEffectiveBaseLedger(join(noDispatch.root,"incomplete"));assert.throws(()=>incomplete.bind(input(noDispatch),{...evidence(noDispatch),receipts:{deriveReceiptView:()=>noDispatch.consumed} as any}),/dispatch/i);
});

test("rejects a legacy second consumed receipt for the same front",()=>{
  const fixture=setup();appendLegacySecondConsumption(fixture);
  assert.throws(()=>fixture.ledger.bind(input(fixture),evidence(fixture)),/consum/i);
});

test("rejects a second grant binding for an already-bound front",()=>{
  const fixture=setup(),first=fixture.ledger.bind(input(fixture),evidence(fixture)),{second,consumed,dispatched}=appendLegacySecondConsumption(fixture);
  const secondInput={...input(fixture),grant_key:second.grant_key,build_attempt_id:consumed.build_attempt_id!,build_dispatched_event_sha256:dispatched.event_sha256,predecessor_event_sha256:dispatched.event_sha256};
  assert.throws(()=>fixture.ledger.bind(secondInput,evidence(fixture)),/conflict|duplicate/i);
  assert.deepEqual(fixture.ledger.load(fixture.grant.grant_key),first);
});

test("child crash after durable append leaves an epoch lock that a later process recovers",()=>{
  const fixture=setup(),tsx=join(process.cwd(),"node_modules","tsx","dist","cli.mjs"),module=pathToFileURL(join(process.cwd(),"owner_repair_effective_base.ts")).href,receipts=pathToFileURL(join(process.cwd(),"owner_repair_receipt_ledger.ts")).href;
  const script=`(async()=>{const fs=(await import('node:fs')).default,original=fs.fsyncSync;fs.fsyncSync=(fd)=>{original(fd);process.exit(86);};(await import('node:module')).syncBuiltinESMExports();const {OwnerRepairEffectiveBaseLedger}=await import(${JSON.stringify(module)});const {OwnerRepairReceiptLedger}=await import(${JSON.stringify(receipts)});const input=JSON.parse(process.env.EFFECTIVE_INPUT);const root=process.env.EFFECTIVE_ROOT;new OwnerRepairEffectiveBaseLedger(root+'/bindings').bind(input,{receipts:new OwnerRepairReceiptLedger(root+'/receipts'),currentTip:input.effective_base_sha,installedRuntimeSha:input.effective_base_sha,doctorPassed:true,isAncestor:(a,b)=>a===b||a===input.frozen_base_sha&&b===input.effective_base_sha});})()`;
  const crashed=spawnSync(process.execPath,[tsx,"-e",script],{cwd:process.cwd(),env:{...process.env,EFFECTIVE_ROOT:fixture.root,EFFECTIVE_INPUT:JSON.stringify(input(fixture))},encoding:"utf8"});
  assert.equal(crashed.status,86,crashed.stderr);
  const recovered=fixture.ledger.bind(input(fixture),evidence(fixture));
  assert.deepEqual(fixture.ledger.load(fixture.grant.grant_key),recovered);
  assert.equal(readFileSync(join(fixture.ledger.root,"owner-repair-effective-bases.jsonl"),"utf8").trim().split("\n").length,1);
});

test("load rejects duplicate and corrupted append-only bindings",()=>{
  const fixture=setup(),binding=fixture.ledger.bind(input(fixture),evidence(fixture)),path=join(fixture.ledger.root,"owner-repair-effective-bases.jsonl");
  appendFileSync(path,`${JSON.stringify(binding)}\n`);assert.throws(()=>fixture.ledger.load(fixture.grant.grant_key),/binding/i);
  const corrupt=setup(),valid=corrupt.ledger.bind(input(corrupt),evidence(corrupt)),corruptPath=join(corrupt.ledger.root,"owner-repair-effective-bases.jsonl");
  appendFileSync(corruptPath,`${JSON.stringify({...valid,effective_base_sha:sha40("e")})}\n`);assert.throws(()=>corrupt.ledger.load(corrupt.grant.grant_key),/binding/i);
});
