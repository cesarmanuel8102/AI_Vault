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
    runtime_binding_required:true,deferment_policy:"FORBIDDEN",
  };
  return {
    schema_version:1,phase_or_item_id:"BR1",source_sha:sourceSha,evaluated_at_utc:"2026-09-10T00:00:00Z",
    requirements:[requirement],deferments:[],evidence:[{
      evidence_id:"EVIDENCE-R15-001",requirement_id:requirement.requirement_id,evidence_kind:"RUNTIME_OBSERVATION",
      evidence_level:"L6_RUNTIME",source_sha:sourceSha,certified_implementation_sha:sourceSha,
      artifact_path:"docs/roadmap/evidence/runtime.json",artifact_sha256:artifactSha,artifact_bytes:artifact,
      environment:"PAPER_RUNTIME",runtime_binding:"paper-runtime:v1",observed_at_utc:"2026-09-10T00:00:00Z",
      observation:{duration_seconds:60,sample_size:1},verifier:{verifier_id:"independent-contract",source_sha:sourceSha,independent:true},
    }],
  };
}

test("SR01 valid bound evidence produces PASS",()=>{
  const decision=evaluateSemanticCompletion(validInput());
  assert.equal(decision.decision,"PASS");
  assert.equal(decision.requirements_total,1);
  assert.equal(decision.requirements_satisfied,1);
  assert.deepEqual(decision.reason_codes,[]);
  assert.match(decision.decision_artifact_sha256,/^[0-9a-f]{64}$/);
});

test("rejects unknown input fields",()=>{
  assert.throws(()=>evaluateSemanticCompletion({...validInput(),unknown:true} as any),/unknown semantic completion field/);
});

test("rejects duplicate requirement identity",()=>{
  const input=validInput();
  input.requirements.push({...input.requirements[0]});
  assert.throws(()=>evaluateSemanticCompletion(input),/duplicate semantic requirement/);
});
