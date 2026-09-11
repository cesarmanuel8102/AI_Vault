import test from "node:test";
import assert from "node:assert/strict";
import {createHash} from "node:crypto";
import {mkdtempSync} from "node:fs";
import {tmpdir} from "node:os";
import {join} from "node:path";
import {AutonomousFlow,newLifecycle,type AutonomousEffects} from "../../../scripts/operator_proxy/autonomous_flow.js";
import {LifecycleStore} from "../../../scripts/operator_proxy/lifecycle_store.js";
import {evaluateSemanticCompletion} from "../../../scripts/operator_proxy/semantic_completion_gate.js";
import {ProductionEffects,resolveSemanticInput} from "../../../scripts/operator_proxy/production_effects.js";
import {closeoutSpec,resolveExecutableFront} from "../../../scripts/operator_proxy/roadmap_sequencer.js";
import {issueBody} from "../../../scripts/operator_proxy/spec_contract.js";
import {Ledger} from "../../../scripts/operator_proxy/decision_ledger.js";
import {POLICY_SHA256,stableDecisionId} from "../../../scripts/operator_proxy/policy_engine.js";
import type {LifecycleRecord,ProxySpec,ReviewerOutput,SemanticCompletionDecisionV1,SemanticCompletionInputV1} from "../../../scripts/operator_proxy/types.js";

const sha=(value:string)=>createHash("sha256").update(value).digest("hex");
const sourceSha="a".repeat(40);
const artifact="verified runtime observation";
const artifactPath="docs/roadmap/evidence/runtime.json";

// ---------------------------------------------------------------------------
// Canonical semantic universe, owned by the trusted source — never the caller.
// ---------------------------------------------------------------------------
const authoritativeRequirement:SemanticCompletionInputV1["requirements"][number]={
  requirement_id:"REQ-R15-SOAK-001",parent_phase:"R15",original_spec_path:"docs/roadmap/BRAIN_101_ROADMAP.md",
  original_spec_sha256:sha("roadmap bytes"),requirement_text_sha256:sha("paper soak must be observed"),
  minimum_evidence_level:"L6_RUNTIME",required_evidence_kinds:["RUNTIME_OBSERVATION"],
  runtime_binding_required:true,deferment_policy:"FORBIDDEN",parent_requirement_ids:[],
  required_environments:["PAPER_RUNTIME"],independent_verifier_required:true,
  minimum_duration_seconds:60,minimum_sample_size:1,
};
const canonicalEvidence={
  evidence_id:"EVIDENCE-R15-001",requirement_id:authoritativeRequirement.requirement_id,evidence_kind:"RUNTIME_OBSERVATION",
  evidence_level:"L6_RUNTIME",source_sha:sourceSha,certified_implementation_sha:sourceSha,
  artifact_path:artifactPath,artifact_sha256:sha(artifact),environment:"PAPER_RUNTIME",runtime_binding:"paper-runtime:v1",
  observed_at_utc:"2026-09-10T00:00:00.000Z",producer_id:"runtime-probe",assertion_type:"OBSERVATION" as const,
  observation:{duration_seconds:60,sample_size:1},verifier:{verifier_id:"independent-contract",source_sha:sourceSha,independent:true},
};
const parentSpec:ProxySpec={schema_version:1,authorization_id:"CESAR-BRAIN-101-OPERATOR-PROXY-20260722-01",repository:"cesarmanuel8102/AI_Vault",roadmap_id:"BRAIN-101",roadmap_version:"1.0.0-reconstructed-glm-harmonized",roadmap_item_id:"R15",expected_base_sha:sourceSha,executor:"codex_control_plane",risk:"LOW",allowed_paths:["docs/roadmap/"],forbidden_paths:["trading/"],acceptance:["pass"],test_commands:["git diff --check"],deployment_allowed:false,objective:"semantic closeout",work_branch:"control-plane/semantic",dependencies:["R0"],deployment_mode:"DOCUMENTATION_CLOSEOUT",front_id:"BRAIN-101-R15-SEMANTIC-01",semantic_completion:{requirements_path:"docs/roadmap/semantic/requirements.json",evidence_path:"docs/roadmap/semantic/evidence.json"}};

/** Trusted canonical source. Everything the evaluator consumes originates here. */
function trustedSource(overrides?:{evidence?:Partial<typeof canonicalEvidence>|null;requirements?:SemanticCompletionInputV1["requirements"]|null;artifactBytes?:string|null;now?:string}){
  const state={requirements:overrides?.requirements??[{...authoritativeRequirement}],evidence:overrides?.evidence===null?[]:[{...canonicalEvidence,...(overrides?.evidence??{})}],artifactBytes:overrides?.artifactBytes===null?undefined:overrides?.artifactBytes??artifact,now:overrides?.now??"2026-09-10T00:00:00.000Z"};
  const source={
    semanticRequirements:()=>state.requirements,
    semanticEvidence:()=>state.evidence,
    semanticDeferments:()=>[],
    semanticDefermentAuthorizations:()=>[],
    artifactBytes:()=>state.artifactBytes,
    canonicalSourceSha:()=>sourceSha,
    nowIsoUtc:()=>state.now,
  };
  return source as unknown as import("../../../scripts/operator_proxy/types.js").SemanticSourceV1 & {artifactBytes():string|undefined};
}
type TrustedSource=ReturnType<typeof trustedSource>;

/** Flow fixture with an injected semantic resolver over the trusted source. */
function semanticFixture(source:TrustedSource){
  let issueCalls=0,buildCalls=0,mergeCalls=0,closeoutCalls=0,nextCalls=0,semanticCalls=0;
  const effects:AutonomousEffects={
    bindLifecycle:()=>{},
    resolveSemanticCompletion:(spec:ProxySpec,merge:string)=>{semanticCalls++;return productionResolveSemanticCompletion(spec,merge,source);},
    ensureIssue:()=>{issueCalls++;return 70;},
    ensureBuild:(_s,_i,session)=>{buildCalls++;return Promise.resolve({pr:71,head_sha:"b".repeat(40),session});},
    ci:()=>"PASS",
    review:(_p,head,session)=>({session:`actual-${session}`,output:{verdict:"PASS",head_sha:head,summary:"PASS",findings:[]} as ReviewerOutput}),
    policy:()=>({outcome:"APPROVE",decision_id:"d".repeat(8)+"-4b3e-4c99-9f2e-1a2b3c4d5e6f"}),
    ensureMerge:()=>{mergeCalls++;return "f".repeat(40);},
    ensureInstall:()=>"PASS",
    ensureRuntimePilot:()=>"PASS",
    ensureCloseout:()=>{closeoutCalls++;return Promise.resolve("PASS");},
    discoverNext:()=>{nextCalls++;},
  };
  return {effects,counts:()=>({issueCalls,buildCalls,mergeCalls,closeoutCalls,nextCalls,semanticCalls})};
}
async function drive(flow:AutonomousFlow,spec:ProxySpec,max=40):Promise<LifecycleRecord>{
  let state:LifecycleRecord;for(let i=0;i<max;i++){state=await flow.step(spec);if(state.state==="TERMINAL_COMPLETED"||state.state==="BLOCKED")break;}return state!;
}
function semanticParentRecord(spec:ProxySpec):LifecycleRecord{
  const head="f".repeat(40);
  return {...newLifecycle(spec),state:"CLOSEOUT_PENDING",issue:70,pr:71,head_sha:head,builder_session:"builder-one",reviewer_session:"reviewer-one",decision_id:"d".repeat(8)+"-4b3e-4c99-9f2e-1a2b3c4d5e6f",completed_effects:["issue:70",`build:${head}`,`merge:${head}`]};
}

test("semantic PASS persists its decision hash and reaches terminal with successor discovery",async()=>{
  const f=semanticFixture(trustedSource());
  const store=new LifecycleStore(mkdtempSync(join(tmpdir(),"sem-flow-")));
  const state=await drive(new AutonomousFlow(store,f.effects),parentSpec);
  assert.equal(state.state,"TERMINAL_COMPLETED");
  assert.ok(state.completed_effects.includes(`semantic_completion:${productionResolveSemanticCompletion(parentSpec,"f".repeat(40),trustedSource()).decision_artifact_sha256}`));
  assert.equal(f.counts().closeoutCalls,1);
  await new AutonomousFlow(store,f.effects).step(parentSpec);
  assert.equal(f.counts().nextCalls,1);
});

test("semantic BLOCK prevents closeout success, closeout merge, terminal completion, and successor discovery",async()=>{
  const blockedSource=trustedSource({evidence:{evidence_level:"L4_SIMULATED_INTEGRATION"}});
  const f=semanticFixture(blockedSource);
  const state=await drive(new AutonomousFlow(new LifecycleStore(mkdtempSync(join(tmpdir(),"sem-block-"))),f.effects),parentSpec);
  assert.equal(state.state,"BLOCKED");
  assert.equal(state.last_error,"SEMANTIC_COMPLETION_BLOCK");
  assert.equal(f.counts().closeoutCalls,0);
  assert.equal(f.counts().nextCalls,0);
  assert.ok(!state.completed_effects.some(effect=>effect.startsWith("semantic_completion:")));
});

test("semantic BLOCK prevents successor authorization on later restart",async()=>{
  const blockedSource=trustedSource({evidence:{evidence_level:"L4_SIMULATED_INTEGRATION"}});
  const f=semanticFixture(blockedSource);
  const store=new LifecycleStore(mkdtempSync(join(tmpdir(),"sem-block-restart-")));
  const state=await drive(new AutonomousFlow(store,f.effects),parentSpec);
  assert.equal(state.state,"BLOCKED");
  const again=await new AutonomousFlow(store,f.effects).step(parentSpec);
  assert.equal(again.state,"BLOCKED");
  assert.equal(again.last_error,"SEMANTIC_COMPLETION_BLOCK");
  assert.equal(f.counts().nextCalls,0);
});

test("blocked semantic state cannot be resumed into closeout by removing evidence",async()=>{
  const blockedSource=trustedSource({evidence:null});
  const f=semanticFixture(blockedSource);
  const store=new LifecycleStore(mkdtempSync(join(tmpdir(),"sem-block-empty-")));
  const state=await drive(new AutonomousFlow(store,f.effects),parentSpec);
  assert.equal(state.state,"BLOCKED");
  assert.equal(state.last_error,"SEMANTIC_COMPLETION_BLOCK");
  assert.equal(f.counts().closeoutCalls,0);
});

test("semantic PASS allows the pre-existing normal closeout path",async()=>{
  const f=semanticFixture(trustedSource());
  const store=new LifecycleStore(mkdtempSync(join(tmpdir(),"sem-normal-")));
  const flow=new AutonomousFlow(store,f.effects);
  const state=await drive(flow,parentSpec);
  assert.equal(state.state,"TERMINAL_COMPLETED");
  assert.equal(f.counts().mergeCalls,1);
  assert.equal(f.counts().closeoutCalls,1);
  assert.ok(state.completed_effects.includes("closeout:R15"));
});

test("non-semantic spec never calls the semantic resolver",async()=>{
  const f=semanticFixture(trustedSource());
  const store=new LifecycleStore(mkdtempSync(join(tmpdir(),"sem-nonbound-")));
  const plain={...parentSpec,semantic_completion:undefined,front_id:"BRAIN-101-R15-PLAIN-01"};
  const state=await drive(new AutonomousFlow(store,f.effects),plain);
  assert.equal(state.state,"TERMINAL_COMPLETED");
  assert.equal(f.counts().semanticCalls,0);
  assert.ok(!state.completed_effects.some(effect=>effect.startsWith("semantic_completion:")));
});

// ---------------------------------------------------------------------------
// Trust boundary: trusted resolver construction (RED — no production impl yet).
// ---------------------------------------------------------------------------

test("trusted resolver builds evaluator input from canonical source, not from the spec",()=>{
  const source=trustedSource();
  const input=resolveSemanticInput(parentSpec,source);
  assert.equal(input.phase_or_item_id,parentSpec.roadmap_item_id);
  assert.equal(input.source_sha,sourceSha);
  assert.deepEqual(input.expected_requirement_ids,[authoritativeRequirement.requirement_id]);
  assert.equal(input.expected_requirements.length,1);
  assert.equal(input.expected_requirements[0].requirement_id,authoritativeRequirement.requirement_id);
  assert.equal(input.requirements.length,1);
  assert.equal(input.evidence.length,1);
  // The canonical artifact bytes resolve from the trusted source and hash-bind.
  assert.equal(input.evidence[0].artifact_sha256,sha(artifact));
});

test("caller cannot self-assert expected requirement identities through the spec",()=>{
  const source=trustedSource();
  const hostileSpec={...parentSpec,semantic_completion:{requirements_path:"attacker/requirements.json",evidence_path:"attacker/evidence.json"}};
  // The resolver ignores spec paths entirely: identity comes from the source.
  const input=resolveSemanticInput(hostileSpec,source);
  assert.deepEqual(input.expected_requirement_ids,[authoritativeRequirement.requirement_id]);
  assert.equal(input.expected_requirements[0].original_spec_sha256,authoritativeRequirement.original_spec_sha256);
});

test("canonical artifact hash mismatch blocks through the trusted resolver",()=>{
  const source=trustedSource({artifactBytes:"tampered bytes"});
  const decision=productionResolveSemanticCompletion(parentSpec,"f".repeat(40),source);
  assert.equal(decision.decision,"BLOCK");
  assert.deepEqual([...decision.reason_codes],["ARTIFACT_HASH_MISMATCH"]);
});

test("missing canonical artifact bytes block",()=>{
  const source=trustedSource({artifactBytes:null});
  const decision=productionResolveSemanticCompletion(parentSpec,"f".repeat(40),source);
  assert.equal(decision.decision,"BLOCK");
  assert.ok(decision.reason_codes.includes("ARTIFACT_HASH_MISMATCH"));
});

test("stale noncanonical source SHA blocks",()=>{
  const staleSource=trustedSource();
  (staleSource as any).canonicalSourceSha=()=>"b".repeat(40);
  const decision=productionResolveSemanticCompletion(parentSpec,"f".repeat(40),staleSource);
  assert.equal(decision.decision,"BLOCK");
  assert.deepEqual([...decision.reason_codes],["STALE_SOURCE_SHA"]);
});

test("caller artifact-byte injection is structurally rejected by the pure gate",()=>{
  const source=trustedSource();
  const input=resolveSemanticInput(parentSpec,source);
  // Even if a hostile caller smuggles bytes into the evidence record, the
  // reviewed evaluator's closed schema rejects unknown fields.
  const hostile={...input,evidence:[{...input.evidence[0],artifact_bytes:"attacker"}]};
  assert.throws(()=>evaluate(hostile,source),/unknown semantic evidence field/);
});

test("non-canonical timestamps are rejected at the trust boundary",()=>{
  for(const bad of ["September 10, 2026","09/10/2026","2026-09-10T00:00:00+02:00","2026-09-10 00:00:00Z","2026-09-10T00:00Z","never"]){
    const source=trustedSource({now:bad});
    assert.throws(()=>resolveSemanticInput(parentSpec,source),/canonical UTC timestamp/,bad);
  }
});

test("canonical UTC timestamps are accepted at the trust boundary",()=>{
  const source=trustedSource({now:"2026-09-10T12:34:56.789Z"});
  const input=resolveSemanticInput(parentSpec,source);
  assert.equal(input.evaluated_at_utc,"2026-09-10T12:34:56.789Z");
});

test("decision hash is bound and cannot be substituted downstream",()=>{
  const source=trustedSource();
  const decision=productionResolveSemanticCompletion(parentSpec,"f".repeat(40),source);
  const otherSource=trustedSource({evidence:{evidence_level:"L4_SIMULATED_INTEGRATION"}});
  const other=productionResolveSemanticCompletion(parentSpec,"f".repeat(40),otherSource);
  assert.notEqual(decision.decision_artifact_sha256,other.decision_artifact_sha256);
  assert.match(decision.decision_artifact_sha256,/^[0-9a-f]{64}$/);
  // The exact decision hash is what the flow persists (see PASS test above).
});

test("resolver never accepts caller-supplied decision hashes",()=>{
  const source=trustedSource();
  // There is no path through resolveSemanticInput to inject a decision hash;
  // it is always computed. The input type has no decision field at all.
  const input=resolveSemanticInput(parentSpec,source);
  assert.equal("decision_artifact_sha256" in input,false);
  assert.equal("decision" in input,false);
});

function evaluate(input:SemanticCompletionInputV1,source:TrustedSource):SemanticCompletionDecisionV1{
  const bytes=new Map<string,string>();
  bytes.set(artifactPath,source.artifactBytes()??"");
  return evaluateSemanticCompletion(input,bytes);
}

/** Mirrors the production resolver contract until the real one exists (RED). */
function productionResolveSemanticCompletion(spec:ProxySpec,merge:string,source:TrustedSource):SemanticCompletionDecisionV1{
  const input=resolveSemanticInput(spec,source);
  const bytes=new Map<string,string>();
  for(const evidence of input.evidence){const resolved=source.artifactBytes();if(resolved!==undefined)bytes.set(evidence.artifact_path,resolved);}
  return evaluateSemanticCompletion(input,bytes);
}

// ---------------------------------------------------------------------------
// Successor authorization: closeout child selection requires the parent's
// semantic PASS receipt when the parent is semantic-bound.
// ---------------------------------------------------------------------------
function semanticParentWithCloseoutSpec():{parent:ProxySpec;child:ProxySpec}{
  const parent:ProxySpec={...parentSpec,closeout:{front_id:"BRAIN-101-R15-SEMANTIC-CLOSEOUT-01",objective:"closeout",work_branch:"control-plane/r15-closeout",executor:"codex_control_plane",risk:"MEDIUM",allowed_paths:["docs/roadmap/"],forbidden_paths:["trading/"],acceptance:["close"],test_commands:["git diff --check"]}};
  return {parent,child:closeoutSpec(parent)};
}
function persistedSemanticCloseoutSpec(child:ProxySpec,parentRecord:LifecycleRecord,semanticHash?:string):ProxySpec{
  const evidence={schema_version:1,parent_front_id:parentRecord.front_id,roadmap_id:"BRAIN-101",roadmap_item_id:parentRecord.roadmap_item_id,issue:parentRecord.issue,pr:parentRecord.pr,decision_id:parentRecord.decision_id,authorization_mode:"POLICY_APPROVED",base_sha:parentRecord.base_sha,closeout_base_sha:parentRecord.head_sha,head_sha:parentRecord.head_sha,merge_commit:parentRecord.head_sha,builder_session:parentRecord.builder_session,reviewer_session:parentRecord.reviewer_session,...(semanticHash!==undefined?{semantic_decision_sha256:semanticHash}:{})};
  const serialized=JSON.stringify(evidence),instruction=`Record this immutable parent lifecycle evidence exactly; do not infer, omit, or replace known values with null: ${serialized}`;
  return {...child,objective:`${(child.objective??"").trim()}\n\nPARENT_LIFECYCLE_EVIDENCE_JSON=${serialized}`,acceptance:[...child.acceptance,instruction]};
}
/** CLOSEOUT_PENDING parent with complete merge/decision evidence, as assertCloseoutChild requires. */
function closeoutPendingParentRecord(parent:ProxySpec,extraEffects:string[]=[]):LifecycleRecord{
  const head="f".repeat(40);
  return {schema_version:1,front_id:parent.front_id!,roadmap_item_id:parent.roadmap_item_id,state:"CLOSEOUT_PENDING",base_sha:parent.expected_base_sha,head_sha:head,issue:246,pr:247,repair_cycles:0,deployment_mode:"NO_DEPLOY",completed_effects:["issue:246",`build:${head}`,`merge:${head}`,...extraEffects],builder_session:"parent-builder",reviewer_session:"parent-reviewer",decision_id:"11111111-1111-4111-8111-111111111111",updated_utc:"2026-09-10T00:00:00.000Z"};
}
function childBusFixture(child:ProxySpec,parentRecord:LifecycleRecord,childHead:string,childBase="d".repeat(40),semanticHash?:string){
  return {
    issueSnapshot:()=>({body:`${issueBody(persistedSemanticCloseoutSpec(child,parentRecord,semanticHash)).trim()}\n\nOPERATOR_PROXY_PR: 249\n`}),
    prIdentity:()=>({author:{login:"cesarmanuel8102"},baseRefName:"codex/own-capital-sustainable-return",baseRefOid:childBase,headRefName:child.work_branch,headRefOid:childHead,headRepository:{nameWithOwner:"cesarmanuel8102/AI_Vault"},isCrossRepository:false,isDraft:true,state:"OPEN"}),
    isAncestor:(left:string,right:string)=>left===right,
  };
}

test("MATCHING_PARENT_AND_CHILD_HASH admits the closeout child",()=>{
  const {parent,child}=semanticParentWithCloseoutSpec();
  const store=new LifecycleStore(mkdtempSync(join(tmpdir(),"sem-child-")));
  const decision=productionResolveSemanticCompletion(parent,"f".repeat(40),trustedSource());
  const withReceipt=closeoutPendingParentRecord(parent,[`semantic_completion:${decision.decision_artifact_sha256}`]);
  store.save(withReceipt);
  store.save({schema_version:1,front_id:child.front_id!,roadmap_item_id:parent.roadmap_item_id,state:"BUILDING",base_sha:"d".repeat(40),head_sha:"e".repeat(40),issue:248,pr:249,repair_cycles:0,deployment_mode:"NO_DEPLOY",completed_effects:["issue:248","build:"+"e".repeat(40)],builder_session:"child-builder",updated_utc:"2026-09-10T00:00:00.000Z"});
  const bus=childBusFixture(child,withReceipt,"e".repeat(40),"d".repeat(40),decision.decision_artifact_sha256);
  const resolved=resolveExecutableFront(bus,store,parent);
  assert.equal(resolved.source,"NONTERMINAL_CLOSEOUT_CHILD");
  assert.equal(resolved.spec.front_id,child.front_id);
  // The child must never be independently semantic-bound.
  assert.equal(resolved.spec.semantic_completion,undefined);
});

test("MISSING_PARENT_RECEIPT rejects the closeout child",()=>{
  const {parent,child}=semanticParentWithCloseoutSpec();
  const store=new LifecycleStore(mkdtempSync(join(tmpdir(),"sem-child-blocked-")));
  const parentRecord=closeoutPendingParentRecord(parent); // no semantic receipt
  store.save(parentRecord);
  store.save({schema_version:1,front_id:child.front_id!,roadmap_item_id:parent.roadmap_item_id,state:"BUILDING",base_sha:"d".repeat(40),head_sha:"e".repeat(40),issue:248,pr:249,repair_cycles:0,deployment_mode:"NO_DEPLOY",completed_effects:["issue:248","build:"+"e".repeat(40)],builder_session:"child-builder",updated_utc:"2026-09-10T00:00:00.000Z"});
  const bus=childBusFixture(child,parentRecord,"e".repeat(40),"d".repeat(40),"a".repeat(64));
  assert.throws(()=>resolveExecutableFront(bus,store,parent),/closeout parent semantic receipt missing/);
});

test("MISSING_CHILD_HASH rejects the closeout child",()=>{
  const {parent,child}=semanticParentWithCloseoutSpec();
  const store=new LifecycleStore(mkdtempSync(join(tmpdir(),"sem-child-nohash-")));
  const decision=productionResolveSemanticCompletion(parent,"f".repeat(40),trustedSource());
  const withReceipt=closeoutPendingParentRecord(parent,[`semantic_completion:${decision.decision_artifact_sha256}`]);
  store.save(withReceipt);
  store.save({schema_version:1,front_id:child.front_id!,roadmap_item_id:parent.roadmap_item_id,state:"BUILDING",base_sha:"d".repeat(40),head_sha:"e".repeat(40),issue:248,pr:249,repair_cycles:0,deployment_mode:"NO_DEPLOY",completed_effects:["issue:248","build:"+"e".repeat(40)],builder_session:"child-builder",updated_utc:"2026-09-10T00:00:00.000Z"});
  const bus=childBusFixture(child,withReceipt,"e".repeat(40)); // no semantic hash in evidence
  assert.throws(()=>resolveExecutableFront(bus,store,parent),/closeout child semantic decision hash missing/);
});

test("DIFFERENT_CHILD_HASH rejects the closeout child",()=>{
  const {parent,child}=semanticParentWithCloseoutSpec();
  const store=new LifecycleStore(mkdtempSync(join(tmpdir(),"sem-child-diff-")));
  const decision=productionResolveSemanticCompletion(parent,"f".repeat(40),trustedSource());
  const withReceipt=closeoutPendingParentRecord(parent,[`semantic_completion:${decision.decision_artifact_sha256}`]);
  store.save(withReceipt);
  store.save({schema_version:1,front_id:child.front_id!,roadmap_item_id:parent.roadmap_item_id,state:"BUILDING",base_sha:"d".repeat(40),head_sha:"e".repeat(40),issue:248,pr:249,repair_cycles:0,deployment_mode:"NO_DEPLOY",completed_effects:["issue:248","build:"+"e".repeat(40)],builder_session:"child-builder",updated_utc:"2026-09-10T00:00:00.000Z"});
  const differentHash="9".repeat(64);
  const bus=childBusFixture(child,withReceipt,"e".repeat(40),"d".repeat(40),differentHash);
  assert.throws(()=>resolveExecutableFront(bus,store,parent),/closeout child semantic decision hash mismatch/);
});

test("MALFORMED_CHILD_HASH rejects the closeout child",()=>{
  const {parent,child}=semanticParentWithCloseoutSpec();
  const store=new LifecycleStore(mkdtempSync(join(tmpdir(),"sem-child-malformed-")));
  const decision=productionResolveSemanticCompletion(parent,"f".repeat(40),trustedSource());
  const withReceipt=closeoutPendingParentRecord(parent,[`semantic_completion:${decision.decision_artifact_sha256}`]);
  store.save(withReceipt);
  store.save({schema_version:1,front_id:child.front_id!,roadmap_item_id:parent.roadmap_item_id,state:"BUILDING",base_sha:"d".repeat(40),head_sha:"e".repeat(40),issue:248,pr:249,repair_cycles:0,deployment_mode:"NO_DEPLOY",completed_effects:["issue:248","build:"+"e".repeat(40)],builder_session:"child-builder",updated_utc:"2026-09-10T00:00:00.000Z"});
  const bus=childBusFixture(child,withReceipt,"e".repeat(40),"d".repeat(40),"NOT-A-VALID-HASH");
  assert.throws(()=>resolveExecutableFront(bus,store,parent),/closeout child semantic decision hash invalid/);
});

test("MULTIPLE_CONFLICTING_PARENT_RECEIPTS fail closed",()=>{
  const {parent,child}=semanticParentWithCloseoutSpec();
  const store=new LifecycleStore(mkdtempSync(join(tmpdir(),"sem-child-conflict-")));
  const decision=productionResolveSemanticCompletion(parent,"f".repeat(40),trustedSource());
  const conflicting=closeoutPendingParentRecord(parent,[`semantic_completion:${decision.decision_artifact_sha256}`,`semantic_completion:${"9".repeat(64)}`]);
  store.save(conflicting);
  store.save({schema_version:1,front_id:child.front_id!,roadmap_item_id:parent.roadmap_item_id,state:"BUILDING",base_sha:"d".repeat(40),head_sha:"e".repeat(40),issue:248,pr:249,repair_cycles:0,deployment_mode:"NO_DEPLOY",completed_effects:["issue:248","build:"+"e".repeat(40)],builder_session:"child-builder",updated_utc:"2026-09-10T00:00:00.000Z"});
  const bus=childBusFixture(child,conflicting,"e".repeat(40),"d".repeat(40),decision.decision_artifact_sha256);
  assert.throws(()=>resolveExecutableFront(bus,store,parent),/closeout parent semantic receipts conflict/);
});

test("closeout child never inherits semantic binding from its parent",()=>{
  const {parent,child}=semanticParentWithCloseoutSpec();
  assert.equal(parent.semantic_completion!==undefined,true);
  assert.equal(child.semantic_completion,undefined,"closeoutSpec must strip semantic_completion from the child");
  assert.equal(child.closeout_only,true);
});

test("non-semantic parent closeout child selection is unchanged",()=>{
  const {parent,child}=semanticParentWithCloseoutSpec();
  const plain={...parent,semantic_completion:undefined};
  const store=new LifecycleStore(mkdtempSync(join(tmpdir(),"sem-child-plain-")));
  const parentRecord=closeoutPendingParentRecord(plain);
  store.save(parentRecord);
  store.save({schema_version:1,front_id:child.front_id!,roadmap_item_id:plain.roadmap_item_id,state:"BUILDING",base_sha:"d".repeat(40),head_sha:"e".repeat(40),issue:248,pr:249,repair_cycles:0,deployment_mode:"NO_DEPLOY",completed_effects:["issue:248","build:"+"e".repeat(40)],builder_session:"child-builder",updated_utc:"2026-09-10T00:00:00.000Z"});
  const bus=childBusFixture(child,parentRecord,"e".repeat(40));
  const resolved=resolveExecutableFront(bus,store,plain);
  assert.equal(resolved.source,"NONTERMINAL_CLOSEOUT_CHILD");
});

test("semantic parent without a semantic receipt cannot authorize a closeout child",()=>{
  const {parent,child}=semanticParentWithCloseoutSpec();
  const store=new LifecycleStore(mkdtempSync(join(tmpdir(),"sem-child-blocked-")));
  const parentRecord=closeoutPendingParentRecord(parent); // no semantic receipt
  store.save(parentRecord);
  store.save({schema_version:1,front_id:child.front_id!,roadmap_item_id:parent.roadmap_item_id,state:"BUILDING",base_sha:"d".repeat(40),head_sha:"e".repeat(40),issue:248,pr:249,repair_cycles:0,deployment_mode:"NO_DEPLOY",completed_effects:["issue:248","build:"+"e".repeat(40)],builder_session:"child-builder",updated_utc:"2026-09-10T00:00:00.000Z"});
  const bus=childBusFixture(child,parentRecord,"e".repeat(40));
  assert.throws(()=>resolveExecutableFront(bus,store,parent),/closeout parent semantic receipt missing/);
});

test("non-semantic parent closeout child selection is unchanged",()=>{
  const {parent,child}=semanticParentWithCloseoutSpec();
  const plain={...parent,semantic_completion:undefined};
  const store=new LifecycleStore(mkdtempSync(join(tmpdir(),"sem-child-plain-")));
  const parentRecord=closeoutPendingParentRecord(plain);
  store.save(parentRecord);
  store.save({schema_version:1,front_id:child.front_id!,roadmap_item_id:plain.roadmap_item_id,state:"BUILDING",base_sha:"d".repeat(40),head_sha:"e".repeat(40),issue:248,pr:249,repair_cycles:0,deployment_mode:"NO_DEPLOY",completed_effects:["issue:248","build:"+"e".repeat(40)],builder_session:"child-builder",updated_utc:"2026-09-10T00:00:00.000Z"});
  const bus=childBusFixture(child,parentRecord,"e".repeat(40));
  const resolved=resolveExecutableFront(bus,store,plain);
  assert.equal(resolved.source,"NONTERMINAL_CLOSEOUT_CHILD");
});
// ---------------------------------------------------------------------------
// P1-1: PRODUCTION canonical Git resolution via GitHubBus.fileAt(path, merge).
// The productive resolver must not depend on an externally pre-bound source.
// ---------------------------------------------------------------------------
const requirementsPath="docs/roadmap/semantic/requirements.json";
const evidencePath="docs/roadmap/semantic/evidence.json";
const canonicalRequirementsJson=JSON.stringify([{...authoritativeRequirement}]);
const canonicalEvidenceJson=JSON.stringify([{...canonicalEvidence}]);

/** Fake GitHubBus recording exact (path, ref) calls. */
function fileAtBus(files:Record<string,string>,options?:{throwOnMissing?:boolean}){
  const calls:{path:string;ref:string}[]=[];
  const bus:any={
    setMutationGuard:()=>{},
    fileAt:(path:string,ref:string)=>{
      calls.push({path,ref});
      if(!(path in files)){if(options?.throwOnMissing!==false)throw new Error("not found");return undefined;}
      return files[path];
    },
  };
  return {bus,calls:()=>calls};
}

/** Canonical semantic registry mapping the item to its authoritative paths. */
const semanticRegistryPath="docs/roadmap/semantic/semantic_registry.json";
const canonicalRegistry=JSON.stringify({schema_version:1,roadmap_id:"BRAIN-101",roadmap_items:{[parentSpec.roadmap_item_id]:{requirements_path:requirementsPath,evidence_path:evidencePath}}});
/** fileAtBus with the canonical registry pre-seeded (the default production case). */
function registryFileAtBus(files:Record<string,string>){
  return fileAtBus({[semanticRegistryPath]:canonicalRegistry,...files});
}

function productionEffectsWithBus(bus:any){
  const root=mkdtempSync(join(tmpdir(),"sem-prod-"));
  const boundary:any={assert:()=>{},bind:()=>{}};
  return new ProductionEffects(bus,new Ledger(join(root,"decisions")),root,root,boundary);
}

test("production resolver reads requirements and evidence at the exact bound merge SHA",()=>{
  const merge="f".repeat(40);
  const boundEvidence=JSON.stringify([{...canonicalEvidence,source_sha:merge,certified_implementation_sha:merge}]);
  const {bus,calls}=registryFileAtBus({[requirementsPath]:canonicalRequirementsJson,[evidencePath]:boundEvidence,[artifactPath]:artifact});
  const effects=productionEffectsWithBus(bus);
  const decision=effects.resolveSemanticCompletion(parentSpec,merge);
  assert.equal(decision.decision,"PASS");
  const requirementReads=calls().filter(call=>call.path===requirementsPath);
  const evidenceReads=calls().filter(call=>call.path===evidencePath);
  const artifactReads=calls().filter(call=>call.path===artifactPath);
  assert.equal(requirementReads.length,1);assert.equal(requirementReads[0].ref,merge);
  assert.equal(evidenceReads.length,1);assert.equal(evidenceReads[0].ref,merge);
  assert.equal(artifactReads.length,1);assert.equal(artifactReads[0].ref,merge);
});

test("production resolver does not require an externally bound semantic source",()=>{
  const merge="f".repeat(40);
  const boundEvidence=JSON.stringify([{...canonicalEvidence,source_sha:merge,certified_implementation_sha:merge}]);
  const {bus}=registryFileAtBus({[requirementsPath]:canonicalRequirementsJson,[evidencePath]:boundEvidence,[artifactPath]:artifact});
  const effects=productionEffectsWithBus(bus);
  // No bindSemanticSource call: production must resolve canonically by itself.
  const decision=effects.resolveSemanticCompletion(parentSpec,merge);
  assert.equal(decision.decision,"PASS");
});

test("production resolver rejects caller-supplied artifact bytes by resolving from Git only",()=>{
  const merge="f".repeat(40);
  const boundEvidence=JSON.stringify([{...canonicalEvidence,source_sha:merge,certified_implementation_sha:merge}]);
  const {bus,calls}=registryFileAtBus({[requirementsPath]:canonicalRequirementsJson,[evidencePath]:boundEvidence,[artifactPath]:"tampered-by-attacker"});
  const effects=productionEffectsWithBus(bus);
  const decision=effects.resolveSemanticCompletion(parentSpec,merge);
  assert.equal(decision.decision,"BLOCK");
  assert.deepEqual([...decision.reason_codes],["ARTIFACT_HASH_MISMATCH"]);
  assert.ok(calls().some(call=>call.path===artifactPath&&call.ref===merge));
});

test("production resolver fails closed when canonical bytes are missing",()=>{
  const merge="f".repeat(40);
  for(const missing of [requirementsPath,evidencePath,artifactPath]){
    const files:Record<string,string>={[requirementsPath]:canonicalRequirementsJson,[evidencePath]:canonicalEvidenceJson,[artifactPath]:artifact};
    delete files[missing];
    const {bus}=registryFileAtBus(files);
    const effects=productionEffectsWithBus(bus);
    assert.throws(()=>effects.resolveSemanticCompletion(parentSpec,merge),/canonical semantic resolution failed/,missing);
  }
});

test("production resolver binds source_sha to the bound lifecycle merge SHA",()=>{
  const merge="f".repeat(40);
  // Evidence claims SHA "b" — stale against the bound merge SHA "f".
  const staleEvidence=JSON.stringify([{...canonicalEvidence,source_sha:"b".repeat(40),certified_implementation_sha:"b".repeat(40)}]);
  const {bus}=registryFileAtBus({[requirementsPath]:canonicalRequirementsJson,[evidencePath]:staleEvidence,[artifactPath]:artifact});
  const effects=productionEffectsWithBus(bus);
  const decision=effects.resolveSemanticCompletion(parentSpec,merge);
  assert.equal(decision.decision,"BLOCK");
  assert.deepEqual([...decision.reason_codes],["STALE_SOURCE_SHA"]);
});

test("production resolver never rewrites evidence SHA values",()=>{
  const merge="f".repeat(40);
  const {bus}=registryFileAtBus({[requirementsPath]:canonicalRequirementsJson,[evidencePath]:canonicalEvidenceJson,[artifactPath]:artifact});
  const effects=productionEffectsWithBus(bus);
  // Valid case: evidence SHA "a" == merge SHA "a"? No — evidence.source_sha is "a".repeat(40)
  // and the bound merge is "f".repeat(40); a mismatch must BLOCK (not be rewritten to PASS).
  const decision=effects.resolveSemanticCompletion(parentSpec,merge);
  // The canonical fixture's evidence binds source_sha "a" — the merge is "f",
  // so this must be STALE unless the fixture is rebuilt. This asserts no rewriting.
  assert.equal(decision.decision,"BLOCK");
  assert.deepEqual([...decision.reason_codes],["STALE_SOURCE_SHA"]);
});

test("production resolver accepts evidence whose SHA equals the bound merge SHA",()=>{
  const merge="f".repeat(40);
  const boundEvidence=JSON.stringify([{...canonicalEvidence,source_sha:merge,certified_implementation_sha:merge}]);
  const {bus}=registryFileAtBus({[requirementsPath]:canonicalRequirementsJson,[evidencePath]:boundEvidence,[artifactPath]:artifact});
  const effects=productionEffectsWithBus(bus);
  const decision=effects.resolveSemanticCompletion(parentSpec,merge);
  assert.equal(decision.decision,"PASS");
});

// ---------------------------------------------------------------------------
// P2-1: strict canonical timestamps for EVERY trusted-boundary timestamp.
// ---------------------------------------------------------------------------
test("NONCANONICAL_OBSERVED_AT_REJECTED at the trust boundary",()=>{
  for(const bad of ["September 10, 2026","09/10/2026","2026-09-10T00:00:00+02:00","2026-09-10 00:00:00Z","2026-09-10T00:00Z","2026-13-45T99:99:99.999Z","2026-02-30T00:00:00.000Z"]){
    const merge="f".repeat(40);
    const badEvidence=JSON.stringify([{...canonicalEvidence,source_sha:merge,certified_implementation_sha:merge,observed_at_utc:bad}]);
    const {bus}=registryFileAtBus({[requirementsPath]:canonicalRequirementsJson,[evidencePath]:badEvidence,[artifactPath]:artifact});
    const effects=productionEffectsWithBus(bus);
    assert.throws(()=>effects.resolveSemanticCompletion(parentSpec,merge),/not canonical UTC timestamp/,bad);
  }
});

test("NONCANONICAL_AUTHORIZED_AT_REJECTED at the trust boundary",()=>{
  const merge="f".repeat(40);
  const boundEvidence=JSON.stringify([{...canonicalEvidence,source_sha:merge,certified_implementation_sha:merge}]);
  const auth=JSON.stringify([{authorization_id:"AUTH-1",requirement_id:authoritativeRequirement.requirement_id,authorization_source_sha:sha("owner authorization"),authorized_by:"owner",scope:"BR1",authorized_at_utc:"09/10/2026"}]);
  // The evidence JSON needs a deferments+authorizations structure: pack both files.
  const {bus}=registryFileAtBus({[requirementsPath]:canonicalRequirementsJson,[evidencePath]:boundEvidence,[artifactPath]:artifact});
  const effects=productionEffectsWithBus(bus);
  // Resolve through the exported trust-boundary function with a hostile source.
  const hostileSource=trustedSource();
  (hostileSource as any).semanticDefermentAuthorizations=()=>JSON.parse(auth);
  assert.throws(()=>resolveSemanticInput(parentSpec,hostileSource),/not canonical UTC timestamp/);
});

test("CANONICAL_ALL_TIMESTAMPS_ACCEPTED at the trust boundary",()=>{
  const merge="f".repeat(40);
  const boundEvidence=JSON.stringify([{...canonicalEvidence,source_sha:merge,certified_implementation_sha:merge,observed_at_utc:"2026-09-10T00:00:00.000Z"}]);
  const {bus}=registryFileAtBus({[requirementsPath]:canonicalRequirementsJson,[evidencePath]:boundEvidence,[artifactPath]:artifact});
  const effects=productionEffectsWithBus(bus);
  const decision=effects.resolveSemanticCompletion(parentSpec,merge);
  assert.equal(decision.decision,"PASS");
});

// ---------------------------------------------------------------------------
// closeoutParentEvidence binds semantic_decision_sha256 (P1-2 end-to-end).
// ---------------------------------------------------------------------------
test("closeout parent evidence carries semantic_decision_sha256 for a semantic-bound parent",()=>{
  const root=mkdtempSync(join(tmpdir(),"sem-evidence-"));
  const ledger=new Ledger(join(root,"decisions"));
  const merge="f".repeat(40),candidate="9".repeat(40);
  const decisionKey=sha("decision-key");
  const decisionId=stableDecisionId(decisionKey);
  ledger.record({schema_version:2,decision_key:decisionKey,decision_id:decisionId,authorization_id:parentSpec.authorization_id,repository:parentSpec.repository,issue:77,pr:78,base_sha:parentSpec.expected_base_sha,head_sha:candidate,roadmap_id:parentSpec.roadmap_id,roadmap_item_id:parentSpec.roadmap_item_id,risk:"LOW",deterministic_gate:"PASS",codex_review:"PASS",review_findings_count:0,review_consistent:true,policy_decision:"APPROVE",allowed_action:"MERGE",policy_sha256:POLICY_SHA256,evidence_sha256:"e".repeat(64),created_utc:"2026-09-10T00:00:00.000Z"} as any);
  ledger.ensureConsumed(ledger.findByKey(decisionKey)!);
  const {bus}=registryFileAtBus({[requirementsPath]:canonicalRequirementsJson,[evidencePath]:JSON.stringify([{...canonicalEvidence,source_sha:merge,certified_implementation_sha:merge}]),[artifactPath]:artifact});
  const effects=new ProductionEffects(bus,ledger,root,root,{assert:()=>{},bind:()=>{}} as any);
  const semanticDecision=effects.resolveSemanticCompletion(parentSpec,merge);
  effects.bindLifecycle(parentSpec,{schema_version:1,front_id:parentSpec.front_id!,roadmap_item_id:parentSpec.roadmap_item_id,state:"CLOSEOUT_PENDING",issue:77,pr:78,base_sha:parentSpec.expected_base_sha,head_sha:merge,builder_session:"builder-parent",reviewer_session:"reviewer-parent",decision_id:decisionId,repair_cycles:0,deployment_mode:"DOCUMENTATION_CLOSEOUT",completed_effects:["issue:77",`build:${candidate}`,`merge:${merge}`,`semantic_completion:${semanticDecision.decision_artifact_sha256}`],updated_utc:"2026-09-10T00:00:00.000Z"});
  const evidence=(effects as any).closeoutParentEvidence(parentSpec,merge);
  assert.equal(evidence.semantic_decision_sha256,semanticDecision.decision_artifact_sha256);
  assert.match(evidence.semantic_decision_sha256,/^[0-9a-f]{64}$/);
});

test("closeout parent evidence fails closed with zero or conflicting semantic receipts",()=>{
  const root=mkdtempSync(join(tmpdir(),"sem-evidence-deny-"));
  const ledger=new Ledger(join(root,"decisions"));
  const merge="f".repeat(40),candidate="9".repeat(40);
  const decisionKey=sha("decision-key-deny");
  const decisionId=stableDecisionId(decisionKey);
  ledger.record({schema_version:2,decision_key:decisionKey,decision_id:decisionId,authorization_id:parentSpec.authorization_id,repository:parentSpec.repository,issue:77,pr:78,base_sha:parentSpec.expected_base_sha,head_sha:candidate,roadmap_id:parentSpec.roadmap_id,roadmap_item_id:parentSpec.roadmap_item_id,risk:"LOW",deterministic_gate:"PASS",codex_review:"PASS",review_findings_count:0,review_consistent:true,policy_decision:"APPROVE",allowed_action:"MERGE",policy_sha256:POLICY_SHA256,evidence_sha256:"e".repeat(64),created_utc:"2026-09-10T00:00:00.000Z"} as any);
  ledger.ensureConsumed(ledger.findByKey(decisionKey)!);
  const {bus}=fileAtBus({});
  const effects=new ProductionEffects(bus,ledger,root,root,{assert:()=>{},bind:()=>{}} as any);
  // Zero receipts.
  effects.bindLifecycle(parentSpec,{schema_version:1,front_id:parentSpec.front_id!,roadmap_item_id:parentSpec.roadmap_item_id,state:"CLOSEOUT_PENDING",issue:77,pr:78,base_sha:parentSpec.expected_base_sha,head_sha:merge,builder_session:"builder-parent",reviewer_session:"reviewer-parent",decision_id:decisionId,repair_cycles:0,deployment_mode:"DOCUMENTATION_CLOSEOUT",completed_effects:["issue:77",`build:${candidate}`,`merge:${merge}`],updated_utc:"2026-09-10T00:00:00.000Z"});
  assert.throws(()=>(effects as any).closeoutParentEvidence(parentSpec,merge),/closeout parent semantic receipt missing/);
  // Conflicting receipts.
  const store=new LifecycleStore(join(root,"lifecycle"));
  const conflicting={schema_version:1,front_id:parentSpec.front_id!,roadmap_item_id:parentSpec.roadmap_item_id,state:"CLOSEOUT_PENDING",issue:77,pr:78,base_sha:parentSpec.expected_base_sha,head_sha:merge,builder_session:"builder-parent",reviewer_session:"reviewer-parent",decision_id:decisionId,repair_cycles:0,deployment_mode:"DOCUMENTATION_CLOSEOUT",completed_effects:["issue:77",`build:${candidate}`,`merge:${merge}`,`semantic_completion:${"a".repeat(64)}`,`semantic_completion:${"9".repeat(64)}`],updated_utc:"2026-09-10T00:00:00.000Z"} as LifecycleRecord;
  store.save(conflicting);
  effects.bindLifecycle(parentSpec,conflicting);
  assert.throws(()=>(effects as any).closeoutParentEvidence(parentSpec,merge),/closeout parent semantic receipts conflict/);
});

// ---------------------------------------------------------------------------
// FINAL REMEDIATION P1-1: canonical registry binding — the caller may name the
// item but may never choose the authoritative registry paths.
// ---------------------------------------------------------------------------

test("hostile requirements_path substitution is rejected",()=>{
  const merge="f".repeat(40);
  const hostile={...parentSpec,semantic_completion:{requirements_path:"attacker/requirements.json",evidence_path:evidencePath}};
  const {bus}=fileAtBus({[semanticRegistryPath]:canonicalRegistry,[requirementsPath]:canonicalRequirementsJson,[evidencePath]:JSON.stringify([{...canonicalEvidence,source_sha:merge,certified_implementation_sha:merge}]),[artifactPath]:artifact,["attacker/requirements.json"]:JSON.stringify([{...authoritativeRequirement,minimum_evidence_level:"L0_PRESENCE"}])});
  const effects=productionEffectsWithBus(bus);
  assert.throws(()=>effects.resolveSemanticCompletion(hostile,merge),/SEMANTIC_CANONICAL_BINDING_MISMATCH|canonical semantic registry/);
});

test("hostile evidence_path substitution is rejected",()=>{
  const merge="f".repeat(40);
  const hostile={...parentSpec,semantic_completion:{requirements_path:requirementsPath,evidence_path:"attacker/evidence.json"}};
  const {bus}=fileAtBus({[semanticRegistryPath]:canonicalRegistry,[requirementsPath]:canonicalRequirementsJson,[evidencePath]:JSON.stringify([{...canonicalEvidence,source_sha:merge,certified_implementation_sha:merge}]),[artifactPath]:artifact,["attacker/evidence.json"]:JSON.stringify([{...canonicalEvidence,evidence_level:"L0_PRESENCE"}])});
  const effects=productionEffectsWithBus(bus);
  assert.throws(()=>effects.resolveSemanticCompletion(hostile,merge),/SEMANTIC_CANONICAL_BINDING_MISMATCH|canonical semantic registry/);
});

test("alternate weaker registry selected through spec paths is rejected",()=>{
  const merge="f".repeat(40);
  // Even if BOTH attacker files exist in the repo at the merge, the spec may
  // not point at them: the canonical registry mapping is the only authority.
  const hostile={...parentSpec,semantic_completion:{requirements_path:"attacker/weak-requirements.json",evidence_path:"attacker/weak-evidence.json"}};
  const {bus}=fileAtBus({[semanticRegistryPath]:canonicalRegistry,[requirementsPath]:canonicalRequirementsJson,[evidencePath]:JSON.stringify([{...canonicalEvidence,source_sha:merge,certified_implementation_sha:merge}]),[artifactPath]:artifact,["attacker/weak-requirements.json"]:JSON.stringify([{...authoritativeRequirement,minimum_evidence_level:"L0_PRESENCE"}]),["attacker/weak-evidence.json"]:JSON.stringify([{...canonicalEvidence,evidence_level:"L0_PRESENCE",source_sha:merge,certified_implementation_sha:merge}])});
  const effects=productionEffectsWithBus(bus);
  assert.throws(()=>effects.resolveSemanticCompletion(hostile,merge),/SEMANTIC_CANONICAL_BINDING_MISMATCH|canonical semantic registry/);
});

test("correct canonical registry mapping passes",()=>{
  const merge="f".repeat(40);
  const {bus}=fileAtBus({[semanticRegistryPath]:canonicalRegistry,[requirementsPath]:canonicalRequirementsJson,[evidencePath]:JSON.stringify([{...canonicalEvidence,source_sha:merge,certified_implementation_sha:merge}]),[artifactPath]:artifact});
  const effects=productionEffectsWithBus(bus);
  const decision=effects.resolveSemanticCompletion(parentSpec,merge);
  assert.equal(decision.decision,"PASS");
});

test("unknown roadmap item in the canonical registry fails closed",()=>{
  const merge="f".repeat(40);
  const emptyRegistry=JSON.stringify({schema_version:1,roadmap_id:"BRAIN-101",roadmap_items:{}});
  const {bus}=fileAtBus({[semanticRegistryPath]:emptyRegistry,[requirementsPath]:canonicalRequirementsJson,[evidencePath]:JSON.stringify([{...canonicalEvidence,source_sha:merge,certified_implementation_sha:merge}]),[artifactPath]:artifact});
  const effects=productionEffectsWithBus(bus);
  assert.throws(()=>effects.resolveSemanticCompletion(parentSpec,merge),/canonical semantic registry/);
});

test("missing canonical registry file fails closed",()=>{
  const merge="f".repeat(40);
  // NO registry in the fixture — the registry file itself is absent.
  const {bus}=fileAtBus({[requirementsPath]:canonicalRequirementsJson,[evidencePath]:JSON.stringify([{...canonicalEvidence,source_sha:merge,certified_implementation_sha:merge}]),[artifactPath]:artifact});
  const effects=productionEffectsWithBus(bus);
  assert.throws(()=>effects.resolveSemanticCompletion(parentSpec,merge),/canonical semantic registry/);
});

// ---------------------------------------------------------------------------
// FINAL REMEDIATION P1-2: no runtime source substitution inside ProductionEffects.
// ---------------------------------------------------------------------------
test("ProductionEffects exposes no runtime source injection API",()=>{
  const effects=productionEffectsWithBus(fileAtBus({}).bus);
  assert.equal("bindSemanticSource" in effects,false,"bindSemanticSource must not exist on the production class");
  assert.equal((effects as any).semanticSource,undefined,"no injectable semantic source field may remain");
});

// ---------------------------------------------------------------------------
// FINAL REMEDIATION P1-3: semantic decision idempotency at CLOSEOUT_PENDING.
// ---------------------------------------------------------------------------
function flowFixtureWithResolver(resolver:(spec:ProxySpec,merge:string)=>SemanticCompletionDecisionV1,closeoutResult:()=>"PASS"|"PENDING"){
  let semanticCalls=0,closeoutCalls=0,nextCalls=0;
  const effects:AutonomousEffects={
    bindLifecycle:()=>{},
    resolveSemanticCompletion:(spec,merge)=>{semanticCalls++;return resolver(spec,merge);},
    ensureIssue:()=>70,
    ensureBuild:(_s,_i,session)=>Promise.resolve({pr:71,head_sha:"b".repeat(40),session}),
    ci:()=>"PASS",
    review:(_p,head,session)=>({session:`actual-${session}`,output:{verdict:"PASS",head_sha:head,summary:"PASS",findings:[]} as ReviewerOutput}),
    policy:()=>({outcome:"APPROVE",decision_id:"d".repeat(8)+"-4b3e-4c99-9f2e-1a2b3c4d5e6f"}),
    ensureMerge:()=>"f".repeat(40),
    ensureInstall:()=>"PASS",
    ensureRuntimePilot:()=>"PASS",
    ensureCloseout:()=>{closeoutCalls++;return Promise.resolve(closeoutResult());},
    discoverNext:()=>{nextCalls++;},
  };
  return {effects,counts:()=>({semanticCalls,closeoutCalls,nextCalls})};
}
const fixedDecision={schema_version:1 as const,phase_or_item_id:parentSpec.roadmap_item_id,original_requirement_refs:Object.freeze([authoritativeRequirement.requirement_id]),requirements_total:1,requirements_satisfied:1,requirements_deferred_valid:0,requirements_blocked:0,evidence_refs:Object.freeze(["EVIDENCE-R15-001"]),decision:"PASS" as const,reason_codes:Object.freeze([]),source_sha:"f".repeat(40),evaluated_at_utc:"2026-09-10T00:00:00.000Z",decision_artifact_sha256:"a".repeat(64)};

test("PASS then closeout PENDING retry reuses the receipt and never re-resolves",async()=>{
  const store=new LifecycleStore(mkdtempSync(join(tmpdir(),"sem-retry-")));
  const resolverCalls:{hash:string}[]=[];
  const f=flowFixtureWithResolver(()=>{
    // Wall-clock drift simulation: each resolution returns a DIFFERENT hash.
    const hash=sha("hash-"+resolverCalls.length);
    resolverCalls.push({hash});
    return {...fixedDecision,decision_artifact_sha256:hash};
  },()=> "PENDING");
  const flow=new AutonomousFlow(store,f.effects);
  // Step manually until the semantic gate has run inside CLOSEOUT_PENDING
  // (the state then still reports CLOSEOUT_PENDING after a PENDING closeout).
  let state:LifecycleRecord=await flow.step(parentSpec);
  for(let i=0;i<40&&state.state!=="BLOCKED"&&(state.state!=="CLOSEOUT_PENDING"||!state.completed_effects.some(e=>e.startsWith("semantic_completion:")));i++)state=await flow.step(parentSpec);
  assert.equal(state.state,"CLOSEOUT_PENDING");
  const receiptsAfterFirst=state.completed_effects.filter(e=>e.startsWith("semantic_completion:"));
  assert.equal(receiptsAfterFirst.length,1);
  // Retry: wall clock advanced → resolver would return a different hash, but
  // the flow MUST NOT call it again.
  state=await flow.step(parentSpec);
  assert.equal(f.counts().semanticCalls,1,"semantic resolver must be called exactly once");
  assert.equal(f.counts().closeoutCalls,2,"closeout retried");
  const receiptsAfterRetry=state.completed_effects.filter(e=>e.startsWith("semantic_completion:"));
  assert.equal(receiptsAfterRetry.length,1,"exactly one semantic receipt after retry");
  assert.equal(receiptsAfterRetry[0],receiptsAfterFirst[0],"receipt unchanged after wall-clock drift");
});

test("closeout eventually PASSes after retries with exactly one receipt",async()=>{
  const store=new LifecycleStore(mkdtempSync(join(tmpdir(),"sem-retry-pass-")));
  let pendingCount=0;
  const f=flowFixtureWithResolver(()=>fixedDecision,()=> ++pendingCount<3?"PENDING":"PASS");
  const flow=new AutonomousFlow(store,f.effects);
  let state:LifecycleRecord=await drive(flow,parentSpec);
  for(let i=0;i<5&&state.state==="CLOSEOUT_PENDING";i++)state=await flow.step(parentSpec);
  assert.equal(state.state,"TERMINAL_COMPLETED");
  const receipts=state.completed_effects.filter(e=>e.startsWith("semantic_completion:"));
  assert.equal(receipts.length,1);
  assert.equal(f.counts().semanticCalls,1,"resolver called exactly once across all retries");
});

test("existing single valid receipt skips semantic resolution entirely",async()=>{
  const store=new LifecycleStore(mkdtempSync(join(tmpdir(),"sem-retry-skip-")));
  const head="f".repeat(40);
  // Pre-persist a record already holding a receipt, sitting at CLOSEOUT_PENDING.
  const seeded=semanticParentRecord(parentSpec);
  store.save({...seeded,head_sha:head,completed_effects:[...seeded.completed_effects,`semantic_completion:${"c".repeat(64)}`]});
  let resolverShouldNotBeCalled=false;
  const f=flowFixtureWithResolver(()=>{if(resolverShouldNotBeCalled)throw new Error("resolver must not be called");return fixedDecision;},()=>"PASS");
  resolverShouldNotBeCalled=true;
  const flow=new AutonomousFlow(store,f.effects);
  const state=await flow.step(parentSpec);
  assert.equal(state.state,"CLOSEOUT_MERGED");
  assert.equal(f.counts().semanticCalls,0);
});

test("multiple distinct pre-existing receipts fail closed before closeout",async()=>{
  const store=new LifecycleStore(mkdtempSync(join(tmpdir(),"sem-retry-conflict-")));
  const head="f".repeat(40);
  const base=semanticParentRecord(parentSpec);
  store.save({...base,head_sha:head,completed_effects:[...base.completed_effects,`semantic_completion:${"a".repeat(64)}`,`semantic_completion:${"9".repeat(64)}`]});
  const f=flowFixtureWithResolver(()=>fixedDecision,()=>"PASS");
  const flow=new AutonomousFlow(store,f.effects);
  const state=await flow.step(parentSpec);
  assert.equal(state.state,"BLOCKED");
  assert.equal(state.last_error,"SEMANTIC_COMPLETION_BLOCK");
  assert.equal(f.counts().closeoutCalls,0,"no closeout may run on conflicting receipts");
});

test("malformed pre-existing receipt fails closed",async()=>{
  const store=new LifecycleStore(mkdtempSync(join(tmpdir(),"sem-retry-malformed-")));
  const head="f".repeat(40);
  const base=semanticParentRecord(parentSpec);
  store.save({...base,head_sha:head,completed_effects:[...base.completed_effects,"semantic_completion:NOT-A-HASH"]});
  const f=flowFixtureWithResolver(()=>fixedDecision,()=>"PASS");
  const flow=new AutonomousFlow(store,f.effects);
  const state=await flow.step(parentSpec);
  assert.equal(state.state,"BLOCKED");
  assert.equal(state.last_error,"SEMANTIC_COMPLETION_BLOCK");
});

test("BLOCK decision persists no receipt and blocks closeout",async()=>{
  const store=new LifecycleStore(mkdtempSync(join(tmpdir(),"sem-retry-block-")));
  const blockedDecision={...fixedDecision,decision:"BLOCK" as const,reason_codes:Object.freeze(["INSUFFICIENT_EVIDENCE_LEVEL" as const])};
  const f=flowFixtureWithResolver(()=>blockedDecision,()=>"PASS");
  const flow=new AutonomousFlow(store,f.effects);
  let state:LifecycleRecord=await flow.step(parentSpec);
  for(let i=0;i<40&&state.state!=="BLOCKED"&&state.state!=="TERMINAL_COMPLETED";i++)state=await flow.step(parentSpec);
  assert.equal(state.state,"BLOCKED");
  assert.equal(state.last_error,"SEMANTIC_COMPLETION_BLOCK");
  assert.equal(state.completed_effects.some(e=>e.startsWith("semantic_completion:")),false);
  assert.equal(f.counts().closeoutCalls,0);
});
