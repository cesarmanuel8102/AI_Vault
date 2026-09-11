import test from "node:test";
import assert from "node:assert/strict";
import {createHash} from "node:crypto";
import {evaluateSemanticCompletion} from "../../../scripts/operator_proxy/semantic_completion_gate.js";
import type {SemanticCompletionInputV1} from "../../../scripts/operator_proxy/types.js";

const sha=(value:string)=>createHash("sha256").update(value).digest("hex");
const sourceSha="a".repeat(40),artifact="verified runtime observation",artifactSha=sha(artifact);

function validInput():SemanticCompletionInputV1{
  const requirement:SemanticCompletionInputV1["requirements"][number]={
    requirement_id:"REQ-R15-SOAK-001",parent_phase:"R15",original_spec_path:"docs/roadmap/BRAIN_101_ROADMAP.md",
    original_spec_sha256:sha("roadmap bytes"),requirement_text_sha256:sha("paper soak must be observed"),
    minimum_evidence_level:"L6_RUNTIME",required_evidence_kinds:["RUNTIME_OBSERVATION"],
    runtime_binding_required:true,deferment_policy:"FORBIDDEN",parent_requirement_ids:[],
    required_environments:["PAPER_RUNTIME"],independent_verifier_required:true,
    minimum_duration_seconds:60,minimum_sample_size:1,
  };
  return {
    schema_version:1,phase_or_item_id:"BR1",source_sha:sourceSha,evaluated_at_utc:"2026-09-10T00:00:00Z",expected_requirement_ids:[requirement.requirement_id],
    requirements:[requirement],deferments:[],evidence:[{
      evidence_id:"EVIDENCE-R15-001",requirement_id:requirement.requirement_id,evidence_kind:"RUNTIME_OBSERVATION",
      evidence_level:"L6_RUNTIME",source_sha:sourceSha,certified_implementation_sha:sourceSha,
      artifact_path:"docs/roadmap/evidence/runtime.json",artifact_sha256:artifactSha,
      environment:"PAPER_RUNTIME",runtime_binding:"paper-runtime:v1",observed_at_utc:"2026-09-10T00:00:00Z",producer_id:"runtime-probe",assertion_type:"OBSERVATION",
      observation:{duration_seconds:60,sample_size:1},verifier:{verifier_id:"independent-contract",source_sha:sourceSha,independent:true},
    }],
  };
}

function verifiedArtifacts():ReadonlyMap<string,string>{
  return new Map([["docs/roadmap/evidence/runtime.json",artifact]]);
}

function reasonFor(mutator:(input:SemanticCompletionInputV1)=>void){
  const input=validInput();mutator(input);return evaluateSemanticCompletion(input,verifiedArtifacts()).reason_codes;
}

test("SR01 valid bound evidence produces PASS",()=>{
  const decision=evaluateSemanticCompletion(validInput(),verifiedArtifacts());
  assert.equal(decision.decision,"PASS");
  assert.equal(decision.requirements_total,1);
  assert.equal(decision.requirements_satisfied,1);
  assert.deepEqual(decision.reason_codes,[]);
  assert.match(decision.decision_artifact_sha256,/^[0-9a-f]{64}$/);
});

test("rejects unknown input fields",()=>{
  assert.throws(()=>evaluateSemanticCompletion({...validInput(),unknown:true} as any,verifiedArtifacts()),/unknown semantic completion field/);
});

test("rejects duplicate requirement identity",()=>{
  const input=validInput();
  input.requirements.push({...input.requirements[0]});
  assert.throws(()=>evaluateSemanticCompletion(input,verifiedArtifacts()),/duplicate semantic requirement/);
});

test("rejects persisted artifact bytes in an evidence reference",()=>{
  const input=validInput();
  Object.assign(input.evidence[0],{artifact_bytes:artifact});
  assert.throws(()=>evaluateSemanticCompletion(input,verifiedArtifacts()),/unknown semantic evidence field/);
});

test("rejects non-enumerable persisted artifact bytes in an evidence reference",()=>{
  const input=validInput();
  Object.defineProperty(input.evidence[0],"artifact_bytes",{value:artifact});
  assert.throws(()=>evaluateSemanticCompletion(input,verifiedArtifacts()),/unknown semantic evidence field/);
});

test("rejects evidence records with an inherited prototype",()=>{
  const input=validInput();
  Object.setPrototypeOf(input.evidence[0],{artifact_bytes:artifact});
  assert.throws(()=>evaluateSemanticCompletion(input,verifiedArtifacts()),/semantic evidence invalid/);
});

test("rejects symbol-keyed evidence fields",()=>{
  const input=validInput();
  Object.assign(input.evidence[0],{[Symbol("artifact_bytes")]:artifact});
  assert.throws(()=>evaluateSemanticCompletion(input,verifiedArtifacts()),/unknown semantic evidence field/);
});

test("returns a frozen immutable decision",()=>{
  const decision=evaluateSemanticCompletion(validInput(),verifiedArtifacts());
  assert.equal(Object.isFrozen(decision),true);
  assert.equal(Object.isFrozen(decision.reason_codes),true);
  assert.equal(Object.isFrozen(decision.original_requirement_refs),true);
  assert.equal(Object.isFrozen(decision.evidence_refs),true);
  assert.throws(()=>{(decision as any).decision="BLOCK";},TypeError);
  assert.throws(()=>{(decision.original_requirement_refs as string[]).push("MUTATION");},TypeError);
  assert.throws(()=>{(decision.evidence_refs as string[]).push("MUTATION");},TypeError);
});

for(const [name,mutator,code] of [
  ["SR02 missing requirement",(input:SemanticCompletionInputV1)=>{input.expected_requirement_ids=["MISSING"];},"MISSING_REQUIREMENT"],
  ["SR03 missing evidence",(input:SemanticCompletionInputV1)=>{input.evidence=[];},"MISSING_EVIDENCE"],
  ["SR04 low level",(input:SemanticCompletionInputV1)=>{input.evidence[0].evidence_level="L4_SIMULATED_INTEGRATION";},"INSUFFICIENT_EVIDENCE_LEVEL"],
  ["SR05 wrong kind",(input:SemanticCompletionInputV1)=>{input.evidence[0].evidence_kind="OTHER";},"WRONG_EVIDENCE_KIND"],
  ["SR06 stale source",(input:SemanticCompletionInputV1)=>{input.evidence[0].source_sha="b".repeat(40);},"STALE_SOURCE_SHA"],
  ["SR07 no runtime binding",(input:SemanticCompletionInputV1)=>{input.evidence[0].runtime_binding="";},"RUNTIME_BINDING_MISSING"],
  ["SR08 naked boolean",(input:SemanticCompletionInputV1)=>{input.evidence[0].assertion_type="BOOLEAN";},"NAKED_BOOLEAN_ASSERTION"],
  ["SR09 self reference",(input:SemanticCompletionInputV1)=>{input.evidence[0].producer_id=input.evidence[0].verifier.verifier_id;},"SELF_REFERENTIAL_EVIDENCE"],
  ["SR12 independent audit absent",(input:SemanticCompletionInputV1)=>{input.evidence[0].verifier.independent=false;},"INDEPENDENT_AUDIT_MISSING"],
  ["SR13 wrong environment",(input:SemanticCompletionInputV1)=>{input.evidence[0].environment="SIMULATOR";},"WRONG_EVIDENCE_KIND"],
  ["SR14 stale implementation",(input:SemanticCompletionInputV1)=>{input.evidence[0].certified_implementation_sha="b".repeat(40);},"STALE_SOURCE_SHA"],
] as const)test(name,()=>assert.deepEqual(reasonFor(mutator),[code]));

test("SR15 tampered artifact blocks",()=>{
  const input=validInput();
  assert.deepEqual(evaluateSemanticCompletion(input,new Map([[input.evidence[0].artifact_path,"tampered"]])).reason_codes,["ARTIFACT_HASH_MISMATCH"]);
});

test("SR10 invalid deferment blocks",()=>{
  assert.deepEqual(reasonFor(input=>{input.deferments=[{deferment_id:"D1",requirement_id:input.requirements[0].requirement_id,authorization_source:"owner",reason:"later",successor_owner:"owner",scope:"BR1",expiration_or_revisit_condition:"next",evidence_refs:[]}];}),["INVALID_DEFERMENT"]);
});

test("SR11 unsatisfied parent blocks",()=>{
  assert.deepEqual(reasonFor(input=>{input.requirements[0].parent_requirement_ids=["PARENT"];}),["PARENT_REQUIREMENT_UNSATISFIED"]);
});

test("SR16 simulation cannot substitute for required soak",()=>{
  assert.deepEqual(reasonFor(input=>{input.requirements[0].minimum_evidence_level="L8_SOAK";input.evidence[0].evidence_level="L4_SIMULATED_INTEGRATION";}),["SIMULATION_SUBSTITUTION"]);
});
