import test from "node:test";
import assert from "node:assert/strict";
import {CandidateExecutionKernel,type CandidateExecutionAdapter,type PreparedCandidateAttempt} from "../../../scripts/operator_proxy/candidate_execution.js";

const sha=(char:string)=>char.repeat(40);

function attempt(overrides:Partial<PreparedCandidateAttempt>={}):PreparedCandidateAttempt {
  return {
    repository:"cesarmanuel8102/AI_Vault",
    front_id:"BRAIN-101-R3-SYNTHETIC-01",
    roadmap_item_id:"R3.8",
    issue:91,
    work_branch:"control-plane/synthetic-candidate",
    expected_base_sha:sha("a"),
    allowed_paths:["docs/"],
    forbidden_paths:["scripts/operator_proxy/"],
    test_commands:["git diff --check"],
    provider_request:{prompt:"already prepared",executor_role:"codex_control_plane"},
    provider_idempotency_key:"attempt-immutable-1",
    publication_receipt:{kind:"ORDINARY",render:()=>"feat(control-plane): complete BRAIN-101-R3-SYNTHETIC-01\n\nBUILDER_BACKEND=codex_cli_openai"},
    ...overrides,
  };
}

function adapter(overrides:Partial<CandidateExecutionAdapter>={}) {
  const calls:string[]=[];
  const candidateHead=sha("b");
  const value:CandidateExecutionAdapter={
    prepare:()=>({worktree:"C:/synthetic",starting_head:sha("a")}),
    invokeProvider:async request=>{calls.push(`provider:${request.idempotency_key??"none"}`);return {executor_role:"codex_control_plane",builder_backend:"codex_cli_openai",builder_model:"gpt-5.6-sol",builder_session:"builder-1",provider_session:"provider-1",base_sha:sha("a"),head_sha:candidateHead,branch:"control-plane/synthetic-candidate"};},
    changedPaths:()=>["docs/result.md"],
    runDeclaredTests:()=>calls.push("tests"),
    diffCheck:()=>calls.push("diff-check"),
    commit:()=>candidateHead,
    push:()=>calls.push("push"),
    remoteHead:()=>candidateHead,
    existingDraftPr:()=>undefined,
    createDraftPr:()=>92,
    bindPrToIssue:()=>calls.push("bind"),
    ...overrides,
  };
  return {adapter:value,calls,candidateHead};
}

test("neutral kernel preserves the supplied idempotency key and publishes without adoption",async()=>{
  const fixture=adapter();
  const result=await new CandidateExecutionKernel(fixture.adapter).publish(attempt());
  assert.deepEqual(fixture.calls,["provider:attempt-immutable-1","tests","diff-check","push","bind"]);
  assert.equal(result.head_sha,fixture.candidateHead);
  assert.equal(result.pr,92);
  assert.equal(result.provider_idempotency_key,"attempt-immutable-1");
  assert.equal("head_bound" in result,false);
});

test("neutral kernel rejects a changed path outside the supplied allowlist before publication",async()=>{
  const fixture=adapter({changedPaths:()=>["scripts/operator_proxy/unsafe.ts"]});
  await assert.rejects(new CandidateExecutionKernel(fixture.adapter).publish(attempt()),/candidate changed path outside scope/);
  assert.deepEqual(fixture.calls,["provider:attempt-immutable-1"]);
});

test("neutral kernel stops before publication when a declared test fails",async()=>{
  const fixture=adapter({runDeclaredTests:()=>{throw new Error("declared test failed");}});
  await assert.rejects(new CandidateExecutionKernel(fixture.adapter).publish(attempt()),/declared test failed/);
  assert.deepEqual(fixture.calls,["provider:attempt-immutable-1"]);
});

test("neutral kernel accepts an uncommitted provider candidate only after receipt commit",async()=>{
  const fixture=adapter({invokeProvider:async request=>{fixture.calls.push(`provider:${request.idempotency_key??"none"}`);return {executor_role:"codex_control_plane",builder_backend:"codex_cli_openai",builder_model:"gpt-5.6-sol",builder_session:"builder-1",provider_session:"provider-1",base_sha:sha("a"),head_sha:sha("a"),branch:"control-plane/synthetic-candidate"};}});
  const result=await new CandidateExecutionKernel(fixture.adapter).publish(attempt());
  assert.equal(result.head_sha,fixture.candidateHead);
  assert.deepEqual(fixture.calls,["provider:attempt-immutable-1","tests","diff-check","push","bind"]);
});

test("neutral kernel rejects remote readback mismatch after the guarded push",async()=>{
  const fixture=adapter({remoteHead:()=>sha("c")});
  await assert.rejects(new CandidateExecutionKernel(fixture.adapter).publish(attempt()),/candidate remote head mismatch/);
  assert.deepEqual(fixture.calls,["provider:attempt-immutable-1","tests","diff-check","push"]);
});
