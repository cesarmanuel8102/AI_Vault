import test from "node:test";import assert from "node:assert/strict";import {decide} from "../../../scripts/operator_proxy/policy_engine.js";import {classify} from "../../../scripts/operator_proxy/risk_classifier.js";import {transition} from "../../../scripts/operator_proxy/state_machine.js";import type {Evidence,ProxySpec} from "../../../scripts/operator_proxy/types.js";
const spec:ProxySpec={schema_version:1,authorization_id:"CESAR-BRAIN-101-OPERATOR-PROXY-20260722-01",repository:"cesarmanuel8102/AI_Vault",roadmap_id:"BRAIN-101",roadmap_version:"1.0.0-reconstructed-glm-harmonized",roadmap_item_id:"R1.1",expected_base_sha:"a".repeat(40),executor:"codex_control_plane",risk:"LOW",allowed_paths:["docs/x.md"],forbidden_paths:["memory/","trading/"],acceptance:[],test_commands:[],deployment_allowed:false};
const evidence:Evidence={issue:1,pr:2,base_sha:"a".repeat(40),head_sha:"b".repeat(40),head_branch:"control-plane/x",base_branch:"codex/own-capital-sustainable-return",author:"cesarmanuel8102",state:"OPEN",draft:true,from_fork:false,mergeable:true,checks_terminal:true,checks_green:true,deterministic_gate:"PASS",changed_files:["docs/x.md"],sensitive_files:[],review:"PASS",builder_session:"builder-1",review_session:"reviewer-2",item_authorized:true,review_p0_p1:false,repair_cycles:0};
test("approve exact low risk",()=>{const d=decide(spec,evidence);assert.equal(d.policy_decision,"APPROVE");assert.equal(d.allowed_action,"MERGE")});
for(const [name,patch] of [["fork",{from_fork:true}],["pending",{checks_terminal:false}],["failed",{checks_green:false}],["head review",{review:"BLOCKED"}],["same session",{review_session:"builder-1"}],["outside scope",{changed_files:["x"]}],["p1",{review_p0_p1:true}]] as const)test(`block ${name}`,()=>assert.equal(decide(spec,{...evidence,...patch} as Evidence).policy_decision,"BLOCK"));
test("repair bounded",()=>assert.equal(decide(spec,{...evidence,review:"CHANGES_REQUESTED"}).policy_decision,"REPAIR"));
test("untrusted repair blocked",()=>assert.equal(decide(spec,{...evidence,author:"attacker",review:"CHANGES_REQUESTED"}).policy_decision,"BLOCK"));
test("non-draft blocked",()=>assert.equal(decide(spec,{...evidence,draft:false}).policy_decision,"BLOCK"));
test("critical escalates",()=>assert.equal(decide({...spec,risk:"CRITICAL"},evidence).policy_decision,"ESCALATE_TO_OWNER"));
test("sensitive path escalates",()=>assert.equal(decide({...spec,allowed_paths:["trading/live.py"]},evidence).policy_decision,"ESCALATE_TO_OWNER"));
for(const phrase of ["model-authored Python is never executed","roadmap item is AUTHORIZED_ACTIVE","human authority preserved","authorization consumed"]){
 test(`ordinary authority wording remains low: ${phrase}`,()=>assert.equal(classify({...spec,acceptance:[phrase]}),"LOW"));
}
for(const phrase of ["authentication change","change auth rules","rotate credentials","credential-free API-key rotation","permission change","authorization policy update","branch protection update","GitHub Actions workflow change","constitutional authority modification","access-control change","force push","production deployment","deploy to production","enable scheduled task","UAC required","enable live trading","canonical local sync","FAISS rebuild"]){
 test(`critical concept escalates: ${phrase}`,()=>assert.equal(classify({...spec,acceptance:[phrase]}),"CRITICAL"));
}
for(const path of ["auth/policy.py","memory/semantic/index.py","financial_autonomy/live.py","faiss/index.bin",".env",".env.production","config/credentials.json","keys/api_key.txt",".github/workflows/deploy.yml","scripts/operator_proxy/risk_classifier.ts","scripts/operator_proxy/evidence_collector.ts","scripts/operator_proxy/codex_reviewer.ts","scripts/operator_proxy/schemas/evidence.schema.json","scripts/Deploy-Worker.ps1"]){
 test(`critical path escalates: ${path}`,()=>assert.equal(classify({...spec,allowed_paths:[path]}),"CRITICAL"));
}
test("state machine rejects invalid",()=>assert.throws(()=>transition("completed","building")));
