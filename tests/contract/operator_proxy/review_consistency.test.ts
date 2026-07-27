import test from "node:test";
import assert from "node:assert/strict";
import {normalizeReviewerOutput} from "../../../scripts/operator_proxy/review_contract.js";
import {execute} from "../../../scripts/operator_proxy/action_executor.js";

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
  const decision:any={policy_decision:"APPROVE",allowed_action:"MERGE",codex_review:"PASS",review_findings_count:1,review_consistent:false,head_sha:head};
  assert.throws(()=>execute(bus,ledger,decision,false),/inconsistent reviewer/);assert.equal(merged,0);
});
