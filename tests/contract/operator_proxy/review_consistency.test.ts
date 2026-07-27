import test from "node:test";
import assert from "node:assert/strict";
import {normalizeReviewerOutput} from "../../../scripts/operator_proxy/review_contract.js";
import {execute} from "../../../scripts/operator_proxy/action_executor.js";
import {historicalDecisionKey,historicalStableDecisionId} from "../../../scripts/operator_proxy/decision_ledger.js";

const head="b".repeat(40);const p2={severity:"P2",title:"p2",evidence:"e",required_correction:"c"} as const;const p1={...p2,severity:"P1" as const};
const review=(verdict:string,findings:any[],sha=head)=>({verdict,head_sha:sha,summary:"s",findings});
test("review verdict consistency matrix",()=>{
  assert.equal(normalizeReviewerOutput(review("PASS",[]),head).verdict,"PASS");
  assert.equal(normalizeReviewerOutput(review("PASS",[p2]),head).verdict,"BLOCKED");
  assert.equal(normalizeReviewerOutput(review("PASS",[p1]),head).verdict,"BLOCKED");
  assert.equal(normalizeReviewerOutput(review("CHANGES_REQUESTED",[]),head).verdict,"BLOCKED");
  assert.equal(normalizeReviewerOutput(review("CHANGES_REQUESTED",[p2]),head).verdict,"CHANGES_REQUESTED");
  assert.equal(normalizeReviewerOutput(review("CHANGES_REQUESTED",[p2,p1]),head).verdict,"BLOCKED");
  assert.equal(normalizeReviewerOutput(review("BLOCKED",[p2]),head).verdict,"BLOCKED");
  assert.throws(()=>normalizeReviewerOutput(review("UNKNOWN",[]),head),/invalid/);
  assert.throws(()=>normalizeReviewerOutput(review("PASS",[] ,"c".repeat(40)),head),/invalid/);
  assert.throws(()=>normalizeReviewerOutput({verdict:"PASS",head_sha:head,summary:"s"},head),/invalid/);
});

test("inconsistent persisted decision cannot invoke merge executor",()=>{
  let merged=0;const bus:any={json:()=>({state:"OPEN"}),merge:()=>{merged++;}};const ledger:any={hasHead:()=>false};
  const decision:any={schema_version:2,risk:"LOW",deterministic_gate:"PASS",policy_decision:"APPROVE",allowed_action:"MERGE",codex_review:"PASS",review_findings_count:1,review_consistent:false,head_sha:head};
  assert.throws(()=>execute(bus,ledger,decision,false),/inconsistent reviewer/);assert.equal(merged,0);
});

test("transitional decisions cannot bypass risk or deterministic policy gates",()=>{
  let merged=0;const bus:any={json:()=>({state:"OPEN"}),merge:()=>{merged++;}};const ledger:any={hasHead:()=>false};
  const seed:any={schema_version:1,authorization_id:"CESAR-BRAIN-101-OPERATOR-PROXY-20260722-01",repository:"cesarmanuel8102/AI_Vault",issue:63,pr:63,base_sha:"a".repeat(40),head_sha:head,roadmap_id:"BRAIN-101",roadmap_item_id:"R1.1",risk:"LOW",deterministic_gate:"PASS",codex_review:"PASS",review_findings_count:0,review_consistent:true,policy_decision:"APPROVE",allowed_action:"MERGE",policy_sha256:"18d599689df667fac42160337a304062f47a15fd23f7d94d38fbe11ac6834781",evidence_sha256:"d".repeat(64),created_utc:"2026-07-24T00:00:00.000Z"};
  const make=(changes:any)=>{const value={...seed,...changes},key=historicalDecisionKey(value);return {...value,decision_key:key,decision_id:historicalStableDecisionId(key)};};
  for(const changes of [{risk:"HIGH"},{risk:"CRITICAL"},{deterministic_gate:"FAIL"}])assert.throws(()=>execute(bus,ledger,make(changes),false),/policy outcome invariants/);
  assert.equal(merged,0);
});
