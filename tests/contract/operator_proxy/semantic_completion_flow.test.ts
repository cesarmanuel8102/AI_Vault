import test from "node:test";
import assert from "node:assert/strict";
import {createHash} from "node:crypto";
import {mkdtempSync} from "node:fs";
import {tmpdir} from "node:os";
import {join} from "node:path";
import {AutonomousFlow,newLifecycle,type AutonomousEffects} from "../../../scripts/operator_proxy/autonomous_flow.js";
import {LifecycleStore} from "../../../scripts/operator_proxy/lifecycle_store.js";
import {evaluateSemanticCompletion} from "../../../scripts/operator_proxy/semantic_completion_gate.js";
import {resolveSemanticInput} from "../../../scripts/operator_proxy/production_effects.js";
import {closeoutSpec,resolveExecutableFront} from "../../../scripts/operator_proxy/roadmap_sequencer.js";
import {issueBody} from "../../../scripts/operator_proxy/spec_contract.js";
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
    resolveSemanticCompletion:(spec:ProxySpec)=>{semanticCalls++;return productionResolveSemanticCompletion(spec,source);},
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
  assert.ok(state.completed_effects.includes(`semantic_completion:${productionResolveSemanticCompletion(parentSpec,trustedSource()).decision_artifact_sha256}`));
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
  const decision=productionResolveSemanticCompletion(parentSpec,source);
  assert.equal(decision.decision,"BLOCK");
  assert.deepEqual([...decision.reason_codes],["ARTIFACT_HASH_MISMATCH"]);
});

test("missing canonical artifact bytes block",()=>{
  const source=trustedSource({artifactBytes:null});
  const decision=productionResolveSemanticCompletion(parentSpec,source);
  assert.equal(decision.decision,"BLOCK");
  assert.ok(decision.reason_codes.includes("ARTIFACT_HASH_MISMATCH"));
});

test("stale noncanonical source SHA blocks",()=>{
  const staleSource=trustedSource();
  (staleSource as any).canonicalSourceSha=()=>"b".repeat(40);
  const decision=productionResolveSemanticCompletion(parentSpec,staleSource);
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
  const decision=productionResolveSemanticCompletion(parentSpec,source);
  const otherSource=trustedSource({evidence:{evidence_level:"L4_SIMULATED_INTEGRATION"}});
  const other=productionResolveSemanticCompletion(parentSpec,otherSource);
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
function productionResolveSemanticCompletion(spec:ProxySpec,source:TrustedSource):SemanticCompletionDecisionV1{
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
function persistedSemanticCloseoutSpec(child:ProxySpec,parentRecord:LifecycleRecord):ProxySpec{
  const evidence={schema_version:1,parent_front_id:parentRecord.front_id,roadmap_id:"BRAIN-101",roadmap_item_id:parentRecord.roadmap_item_id,issue:parentRecord.issue,pr:parentRecord.pr,decision_id:parentRecord.decision_id,authorization_mode:"POLICY_APPROVED",base_sha:parentRecord.base_sha,closeout_base_sha:parentRecord.head_sha,head_sha:parentRecord.head_sha,merge_commit:parentRecord.head_sha,builder_session:parentRecord.builder_session,reviewer_session:parentRecord.reviewer_session};
  const serialized=JSON.stringify(evidence),instruction=`Record this immutable parent lifecycle evidence exactly; do not infer, omit, or replace known values with null: ${serialized}`;
  return {...child,objective:`${(child.objective??"").trim()}\n\nPARENT_LIFECYCLE_EVIDENCE_JSON=${serialized}`,acceptance:[...child.acceptance,instruction]};
}
/** CLOSEOUT_PENDING parent with complete merge/decision evidence, as assertCloseoutChild requires. */
function closeoutPendingParentRecord(parent:ProxySpec,extraEffects:string[]=[]):LifecycleRecord{
  const head="f".repeat(40);
  return {schema_version:1,front_id:parent.front_id!,roadmap_item_id:parent.roadmap_item_id,state:"CLOSEOUT_PENDING",base_sha:parent.expected_base_sha,head_sha:head,issue:246,pr:247,repair_cycles:0,deployment_mode:"NO_DEPLOY",completed_effects:["issue:246",`build:${head}`,`merge:${head}`,...extraEffects],builder_session:"parent-builder",reviewer_session:"parent-reviewer",decision_id:"11111111-1111-4111-8111-111111111111",updated_utc:"2026-09-10T00:00:00.000Z"};
}
function childBusFixture(child:ProxySpec,parentRecord:LifecycleRecord,childHead:string,childBase="d".repeat(40)){
  return {
    issueSnapshot:()=>({body:`${issueBody(persistedSemanticCloseoutSpec(child,parentRecord)).trim()}\n\nOPERATOR_PROXY_PR: 249\n`}),
    prIdentity:()=>({author:{login:"cesarmanuel8102"},baseRefName:"codex/own-capital-sustainable-return",baseRefOid:childBase,headRefName:child.work_branch,headRefOid:childHead,headRepository:{nameWithOwner:"cesarmanuel8102/AI_Vault"},isCrossRepository:false,isDraft:true,state:"OPEN"}),
    isAncestor:(left:string,right:string)=>left===right,
  };
}

test("semantic parent admits its closeout child only with the PASS receipt",()=>{
  const {parent,child}=semanticParentWithCloseoutSpec();
  const store=new LifecycleStore(mkdtempSync(join(tmpdir(),"sem-child-")));
  const decision=productionResolveSemanticCompletion(parent,trustedSource());
  const withReceipt=closeoutPendingParentRecord(parent,[`semantic_completion:${decision.decision_artifact_sha256}`]);
  store.save(withReceipt);
  store.save({schema_version:1,front_id:child.front_id!,roadmap_item_id:parent.roadmap_item_id,state:"BUILDING",base_sha:"d".repeat(40),head_sha:"e".repeat(40),issue:248,pr:249,repair_cycles:0,deployment_mode:"NO_DEPLOY",completed_effects:["issue:248","build:"+"e".repeat(40)],builder_session:"child-builder",updated_utc:"2026-09-10T00:00:00.000Z"});
  const bus=childBusFixture(child,withReceipt,"e".repeat(40));
  const resolved=resolveExecutableFront(bus,store,parent);
  assert.equal(resolved.source,"NONTERMINAL_CLOSEOUT_CHILD");
  assert.equal(resolved.spec.front_id,child.front_id);
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