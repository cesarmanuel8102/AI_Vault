import test from "node:test";
import assert from "node:assert/strict";
import {mkdtempSync,readFileSync,writeFileSync} from "node:fs";
import {tmpdir} from "node:os";
import {join} from "node:path";
import {redactedError,redactSensitiveData,redactString} from "../../../scripts/operator_proxy/redaction.js";
import {LifecycleStore} from "../../../scripts/operator_proxy/lifecycle_store.js";
import {Ledger} from "../../../scripts/operator_proxy/decision_ledger.js";
import {GitHubBus} from "../../../scripts/operator_proxy/github_bus.js";
import {RequestCoordinator} from "../../../scripts/operator_proxy/request_coordinator.js";

const secrets=["Bearer abc.DEF_123456789","ghp_123456789012345678901234567890","github_pat_123456789012345678901234567890","sk-12345678901234567890","api_key=synthetic-key","password=hunter2","client_secret=synthetic-client","access_token=synthetic-access","refresh_token=synthetic-refresh","postgres://user:secret@host/db","-----BEGIN PRIVATE KEY-----\nsynthetic\n-----END PRIVATE KEY-----"];
test("synthetic secrets are deterministically removed from multiline and structured values",()=>{
  const raw=secrets.join("\n");const clean=redactString(raw);for(const secret of ["abc.DEF_123456789","ghp_123456789012345678901234567890","secret@host","synthetic-client","hunter2"])assert.equal(clean.includes(secret),false);
  const split=redactSensitiveData({authorization:"part-one",password:"part-two",nested:{access_token:"part-three"}});assert.deepEqual(split,{authorization:"[REDACTED:TOKEN]",password:"[REDACTED:PASSWORD]",nested:{access_token:"[REDACTED:TOKEN]"}});
});

test("subprocess stdout and stderr errors are redacted before propagation",()=>{const message=redactedError({message:"process failed",stdout:"api_key=synthetic-key",stderr:"Authorization: Basic synthetic-credential"});assert.equal(message.includes("synthetic-key"),false);assert.equal(message.includes("synthetic-credential"),false);assert.match(message,/REDACTED/);});

test("state and ledger persist only redacted data",()=>{
  const root=mkdtempSync(join(tmpdir(),"redaction-"));const store=new LifecycleStore(join(root,"state"));const record:any={schema_version:1,front_id:"BRAIN-101-REDACTION-01",roadmap_item_id:"R1.1",state:"BLOCKED",base_sha:"a".repeat(40),repair_cycles:0,deployment_mode:"NO_DEPLOY",completed_effects:[],last_error:`password=hunter2`,updated_utc:new Date().toISOString()};store.save(record);const stateBytes=readFileSync(store.path(record.front_id),"utf8");assert.equal(stateBytes.includes("hunter2"),false);
  const ledger=new Ledger(join(root,"ledger"));const decision:any={schema_version:2,decision_key:"e".repeat(64),decision_id:"eeeeeeee-eeee-4eee-aeee-eeeeeeeeeeee",authorization_id:`Authorization: Bearer abc.DEF_123456789`,repository:"r",issue:1,pr:2,base_sha:"a".repeat(40),head_sha:"b".repeat(40),roadmap_id:"BRAIN-101",roadmap_item_id:"R1",risk:"LOW",deterministic_gate:"FAIL",codex_review:"BLOCKED",review_findings_count:1,review_consistent:true,policy_decision:"BLOCK",allowed_action:"NONE",policy_sha256:"c".repeat(64),evidence_sha256:"d".repeat(64),created_utc:new Date().toISOString()};ledger.record(decision);const bytes=readFileSync(join(root,"ledger","events.jsonl"),"utf8");assert.equal(bytes.includes("abc.DEF_123456789"),false);
});

test("GitHub comments and repair feedback are redacted before output",()=>{
  const calls:string[][]=[];const bus=new GitHubBus("gh");bus.setMutationGuard(()=>{});(bus as any).call=(args:string[])=>{calls.push(args);return "";};(bus as any).json=()=>({comments:[{body:"[OPERATOR-PROXY][REPAIR]\npassword=hunter2"}]});bus.comment(1,"Authorization: Bearer abc.DEF_123456789");assert.equal(calls.flat().join(" ").includes("abc.DEF_123456789"),false);assert.equal(bus.repairPrompt(1).includes("hunter2"),false);
});

test("sensitive installation receipt fails closed without propagation",()=>{
  const root=mkdtempSync(join(tmpdir(),"receipt-")),sha="a".repeat(40),artifact="b".repeat(64),front="BRAIN-101-REDACTION-INSTALL-01",spec:any={schema_version:1,repository:"cesarmanuel8102/AI_Vault",roadmap_item_id:"R1.2",front_id:front,install_target:"agent_loop_worker"};const coordinator=new RequestCoordinator(root,()=>{}),name=`install-${front}-${sha}.json`;coordinator.install(spec,sha,artifact);writeFileSync(join(root,"receipts",name),JSON.stringify({schema_version:2,kind:"install",sha,status:"PASS",access_token:"synthetic-access"}));assert.throws(()=>coordinator.install(spec,sha,artifact),/receipt invalid|sensitive/);
});
