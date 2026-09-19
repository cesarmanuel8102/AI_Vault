# BR1 Semantic Completion and Evidence Integrity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make semantic completion a fail-closed, evidence-backed prerequisite for governed closeout and successor authorization.

**Architecture:** A pure TypeScript evaluator owns all PASS/BLOCK decisions. Existing Operator Proxy production effects and CI call that evaluator; lifecycle retains only a verified decision receipt. Future/remediation specs opt into the gate while historical BRAIN-101 remains readable but cannot serve as semantic evidence.

**Tech Stack:** TypeScript 7, Node 22, `tsx --test`, existing Operator Proxy lifecycle and GitHub Actions contracts.

**Spec:** `docs/superpowers/specs/2026-09-10-br1-semantic-completion-evidence-integrity-design.md`

## Global Constraints

- `HUMAN_FINAL_AUTHORITY=true`; `AUTO_MERGE=false`; `CANONICAL_LOCAL_SYNC=false`; `LIVE_TRADING=false`; `REAL_MONEY=false`.
- Persistent Agent Loop and both schedulers remain disabled. The synthetic test does not start a worker, scheduler, broker, provider, or deployment.
- No production code references historical item numbers, Issues, PRs, or specimen SHAs.
- One authority only: `evaluateSemanticCompletion()` in `scripts/operator_proxy/semantic_completion_gate.ts` is the sole producer of semantic PASS/BLOCK.
- Historical records without explicit semantic metadata are readable history, never trusted semantic completion.

---

## Intended File Structure

- `scripts/operator_proxy/semantic_completion_gate.ts`: schema validation, canonical serialization, evidence validation, and pure decision evaluator.
- `scripts/operator_proxy/types.ts`: evidence-level, requirement, evidence, deferment, decision, and optional semantic-spec metadata types.
- `scripts/operator_proxy/production_effects.ts`: resolves canonical artifact bytes and calls the pure evaluator before closeout.
- `scripts/operator_proxy/autonomous_flow.ts`: persists only a PASS receipt effect; blocks semantic-bound closeout and successor discovery otherwise.
- `scripts/operator_proxy/roadmap_sequencer.ts`: binds a semantic closeout child to the parent decision receipt.
- `scripts/operator_proxy/package.json` and `.github/workflows/operator-proxy-contract-ubuntu.yml`: explicit CI invocation of the same semantic suite.
- `AGENTS.md`: concise persistent completion-evidence rule.
- `tests/contract/operator_proxy/semantic_completion_gate.test.ts`: SR01-SR15 pure evaluator matrix.
- `tests/contract/operator_proxy/semantic_completion_flow.test.ts`: SR16, closeout, successor, and synthetic Agent Loop integration matrix.
- Existing `autonomous_flow.test.ts`, `sequencer.test.ts`, and `policy.test.ts`: narrow ordinary-behavior regressions only when signatures require it.

## Task 1: Typed Semantic Contracts and Canonical Decision Shape

**Files:**
- Modify: `scripts/operator_proxy/types.ts`
- Create: `scripts/operator_proxy/semantic_completion_gate.ts`
- Test: `tests/contract/operator_proxy/semantic_completion_gate.test.ts`

**Interfaces:**
- Produces `EvidenceLevel`, `SemanticRequirementV1`, `EvidenceRefV1`, `DefermentV1`, `SemanticCompletionInputV1`, `SemanticCompletionDecisionV1`.
- Produces `evaluateSemanticCompletion(input: SemanticCompletionInputV1): SemanticCompletionDecisionV1`.

- [ ] **Step 1: Write the positive-control test and schema rejection tests**

```ts
test("SR01 valid bound evidence produces PASS",()=>{
  const decision=evaluateSemanticCompletion(validInput());
  assert.equal(decision.decision,"PASS");
  assert.equal(decision.requirements_total,1);
  assert.equal(decision.requirements_satisfied,1);
});
test("rejects unknown input fields and duplicate requirement identity",()=>{
  assert.throws(()=>evaluateSemanticCompletion({...validInput(),unknown:true} as any));
  assert.throws(()=>evaluateSemanticCompletion(withDuplicateRequirement(validInput())));
});
```

- [ ] **Step 2: Run RED**

Run: `npx tsx --test ../../tests/contract/operator_proxy/semantic_completion_gate.test.ts`

Expected: FAIL because the module and types do not exist.

- [ ] **Step 3: Implement the minimum closed schema and canonical digest**

```ts
export function evaluateSemanticCompletion(input:SemanticCompletionInputV1):SemanticCompletionDecisionV1 {
  const parsed=parseSemanticCompletionInput(input);
  const result=evaluateRequirements(parsed);
  return freezeDecision(result, canonicalSha256(result));
}
```

Reject unknown fields, invalid SHA/timestamp/enum values, duplicate IDs, and
unbound booleans. Define the nine levels ending exactly in
`L9_ADVERSARIAL_TARGET_ENVIRONMENT`.

- [ ] **Step 4: Verify GREEN**

Run: `npx tsx --test ../../tests/contract/operator_proxy/semantic_completion_gate.test.ts && npm run typecheck`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/operator_proxy/types.ts scripts/operator_proxy/semantic_completion_gate.ts tests/contract/operator_proxy/semantic_completion_gate.test.ts
git commit -m "feat(proxy): define semantic completion evidence contracts"
```

## Task 2: Requirement and Evidence Validation (SR02-SR15)

**Files:**
- Modify: `scripts/operator_proxy/semantic_completion_gate.ts`
- Modify: `tests/contract/operator_proxy/semantic_completion_gate.test.ts`

**Interfaces:**
- `evaluateSemanticCompletion()` returns sorted deterministic `reason_codes` and never throws for a well-formed but unsatisfied input.

- [ ] **Step 1: Write failing SR02-SR15 cases**

```ts
for(const [name,input,code] of [
  ["SR02 missing requirement",missingRequirement(),"MISSING_REQUIREMENT"],
  ["SR03 missing evidence",missingEvidence(),"MISSING_EVIDENCE"],
  ["SR04 low level",lowLevelEvidence(),"INSUFFICIENT_EVIDENCE_LEVEL"],
  ["SR05 wrong kind",wrongKindEvidence(),"WRONG_EVIDENCE_KIND"],
  ["SR06 stale source",staleSourceEvidence(),"STALE_SOURCE_SHA"],
  ["SR07 no runtime binding",unboundRuntimeEvidence(),"RUNTIME_BINDING_MISSING"],
  ["SR08 naked boolean",nakedBooleanEvidence(),"NAKED_BOOLEAN_ASSERTION"],
  ["SR09 self reference",selfReferentialEvidence(),"SELF_REFERENTIAL_EVIDENCE"],
  ["SR10 invalid deferment",invalidDeferment(),"INVALID_DEFERMENT"],
  ["SR11 parent unsatisfied",unsatisfiedParent(),"PARENT_REQUIREMENT_UNSATISFIED"],
  ["SR12 independent audit absent",missingIndependentVerifier(),"INDEPENDENT_AUDIT_MISSING"],
  ["SR13 wrong environment",simulatorForExternalPaper(),"WRONG_EVIDENCE_KIND"],
  ["SR14 stale implementation",staleImplementation(),"STALE_SOURCE_SHA"],
  ["SR15 tampered artifact",tamperedArtifact(),"ARTIFACT_HASH_MISMATCH"],
] as const) test(name,()=>assert.deepEqual(evaluateSemanticCompletion(input).reason_codes,[code]));
```

- [ ] **Step 2: Run RED**

Run: `npx tsx --test ../../tests/contract/operator_proxy/semantic_completion_gate.test.ts`

Expected: failures for unimplemented reason-code checks.

- [ ] **Step 3: Implement requirement-by-requirement validation**

Require exact requirement identity hashes, source/implementation SHA equality,
valid artifact-byte hash, required kinds, environment, duration/sample,
runtime binding, non-self verifier, freshness, and explicit deferment fields.
Do not treat a higher level as a substitute for a missing required kind.

- [ ] **Step 4: Verify GREEN and deterministic order**

Run: `npx tsx --test ../../tests/contract/operator_proxy/semantic_completion_gate.test.ts && npm run typecheck`

Expected: SR01-SR15 PASS; repeated evaluation yields byte-identical decisions.

- [ ] **Step 5: Commit**

```bash
git add scripts/operator_proxy/semantic_completion_gate.ts tests/contract/operator_proxy/semantic_completion_gate.test.ts
git commit -m "feat(proxy): enforce semantic evidence lineage and integrity"
```

## Task 3: Bind PASS to Parent Closeout and Successor Discovery

**Files:**
- Modify: `scripts/operator_proxy/types.ts`
- Modify: `scripts/operator_proxy/production_effects.ts`
- Modify: `scripts/operator_proxy/autonomous_flow.ts`
- Modify: `scripts/operator_proxy/roadmap_sequencer.ts`
- Test: `tests/contract/operator_proxy/semantic_completion_flow.test.ts`

**Interfaces:**
- `ProductionEffects.resolveSemanticCompletion(spec, merge): SemanticCompletionDecisionV1` reads canonical bound artifacts and calls only `evaluateSemanticCompletion()`.
- `AutonomousEffects.resolveSemanticCompletion?` is injected for tests.
- A PASS produces exactly `semantic_completion:<decision_artifact_sha256>` on the parent; BLOCK transitions to `BLOCKED` with `last_error="SEMANTIC_COMPLETION_BLOCK"`.

- [ ] **Step 1: Write failing flow tests**

```ts
test("semantic BLOCK prevents closeout creation, closeout merge, terminal state, and successor discovery",async()=>{
  const state=await driveSemanticFixture(blockedDecision());
  assert.equal(state.state,"BLOCKED");
  assert.equal(fixture.counts().closeoutCalls,0);
  assert.equal(fixture.counts().nextCalls,0);
});
test("semantic PASS persists its decision hash and is bound into the closeout child",async()=>{
  const state=await driveSemanticFixture(passingDecision());
  assert.equal(state.state,"TERMINAL_COMPLETED");
  assert.ok(state.completed_effects.includes(`semantic_completion:${passingDecision().decision_artifact_sha256}`));
});
```

- [ ] **Step 2: Run RED**

Run: `npx tsx --test ../../tests/contract/operator_proxy/semantic_completion_flow.test.ts`

Expected: FAIL because the flow does not resolve semantic decisions.

- [ ] **Step 3: Implement one evaluator path**

Only semantic-bound specs call the injected/production resolver. Record a PASS receipt before `ensureCloseout`; reject BLOCK before any closeout effect. The BLOCK path must make `CLOSEOUT_CREATED_AS_SUCCESS`, `CLOSEOUT_MERGED`, `TERMINAL_COMPLETED`, `SUCCESSOR_DISCOVERY`, `SUCCESSOR_AUTHORIZATION`, and certification unreachable. Require the same receipt in closeout parent evidence and in `assertCloseoutChild`. `TERMINAL_COMPLETED` may call `discoverNext` only when a semantic-bound parent has the matching PASS receipt.

- [ ] **Step 4: Verify focused integration and ordinary behavior**

Run: `npx tsx --test ../../tests/contract/operator_proxy/semantic_completion_flow.test.ts ../../tests/contract/operator_proxy/autonomous_flow.test.ts ../../tests/contract/operator_proxy/sequencer.test.ts`

Expected: PASS. Non-semantic historical fixture behavior remains unchanged.

- [ ] **Step 5: Commit**

```bash
git add scripts/operator_proxy/types.ts scripts/operator_proxy/production_effects.ts scripts/operator_proxy/autonomous_flow.ts scripts/operator_proxy/roadmap_sequencer.ts tests/contract/operator_proxy/semantic_completion_flow.test.ts tests/contract/operator_proxy/autonomous_flow.test.ts tests/contract/operator_proxy/sequencer.test.ts
git commit -m "feat(proxy): gate closeout and successors on semantic evidence"
```

## Task 4: Synthetic Agent Loop Certification and Explicit CI Consumer

**Files:**
- Modify: `scripts/operator_proxy/package.json`
- Modify: `.github/workflows/operator-proxy-contract-ubuntu.yml`
- Modify: `tests/contract/operator_proxy/semantic_completion_flow.test.ts`

**Interfaces:**
- `npm run test:semantic-completion` executes the same TypeScript test module that imports `evaluateSemanticCompletion()`.

- [ ] **Step 1: Write SR16 synthetic Agent Loop test**

```ts
test("SR16 simulated 30D cannot close an L8 soak parent",async()=>{
  const result=await runBoundedSyntheticAgentLoop({
    parent:requirement({minimum_evidence_level:"L8_SOAK"}),
    child:evidence({evidence_level:"L4_SIMULATED_INTEGRATION",environment:"SIMULATOR"}),
    ci:"PASS",review:"PASS",contracts:"PASS",
  });
  assert.equal(result.semantic_completion,"BLOCK");
  assert.equal(result.closeout,"BLOCK");
  assert.equal(result.successor_authorization,"BLOCK");
  assert.equal(result.agent_loop_semantic_gate_certification,"PASS");
});
```

- [ ] **Step 2: Run RED**

Run: `npx tsx --test ../../tests/contract/operator_proxy/semantic_completion_flow.test.ts`

Expected: FAIL because the bounded synthetic helper/assertions are absent.

- [ ] **Step 3: Implement test-only synthetic invocation and CI step**

The helper must use in-memory effects and must not import worker, scheduler,
GitHub, broker, provider, or filesystem runtime paths. Add an explicit
`Semantic completion regression` workflow step running `npm run
test:semantic-completion`; it uses the same exported gate, not a shell parser
or duplicate checker.

- [ ] **Step 4: Verify GREEN**

Run: `npm run test:semantic-completion && npm test && npm run typecheck`

Expected: all semantic and existing contracts PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/operator_proxy/package.json .github/workflows/operator-proxy-contract-ubuntu.yml tests/contract/operator_proxy/semantic_completion_flow.test.ts
git commit -m "test(proxy): certify semantic gate against synthetic agent loop"
```

## Task 5: Persistent Completion Rule and Full Verification

**Files:**
- Modify: `AGENTS.md`
- Modify only Task 1-4 files if a test reveals a scoped defect.

- [ ] **Step 1: Add concise persistent instructions**

Add exactly the rule that before any COMPLETE/CLOSED/VERIFIED/READY/CERTIFIED
claim or successor authorization, a worker re-reads the parent requirement,
resolves `SemanticCompletionGate`, uses fresh verification, and invokes
`superpowers:verification-before-completion`. State that agent claims,
reviewer claims, and lifecycle status are not semantic evidence.

- [ ] **Step 2: Run documentation contract check**

Run: `rg -n "SemanticCompletionGate|Agent claim is not evidence|Reviewer claim is not evidence|Lifecycle status is not semantic evidence" AGENTS.md`

Expected: all required lines found exactly once.

- [ ] **Step 3: Run full regression and security checks**

```bash
npm run typecheck
npm test
npm run test:semantic-completion
git diff --check
rg -n "L9_ADVERSARIAL_LIVE_ENVIRONMENT|semantic_completion_verified" scripts/operator_proxy tests/contract/operator_proxy AGENTS.md
```

Expected: all tests/typecheck/diff pass; final scan has no matches.

- [ ] **Step 4: Request and receive independent review**

Use `superpowers:requesting-code-review`; validate each finding with
`superpowers:receiving-code-review`. Fix only valid scoped findings, then
repeat the focused and full suites.

- [ ] **Step 5: Final verification and commit**

```bash
git status --short --untracked-files=all
git diff --check
git diff --stat origin/codex/own-capital-sustainable-return...HEAD
git add AGENTS.md scripts/operator_proxy tests/contract/operator_proxy .github/workflows/operator-proxy-contract-ubuntu.yml
git commit -m "feat(proxy): require evidence-backed semantic completion"
```

Expected: clean tree after commit; no scheduler, worker, deployment, trading,
HIVE, or canonical-sync changes.

## Task 6: Governed Publication and Stop Gate

**Files:**
- No source modifications unless CI/review reveals a valid scoped defect.

- [ ] **Step 1: Publish normal branch and open Draft PR**

```bash
git push -u origin codex/br1-semantic-completion-evidence-integrity
```

Open one Draft PR against `codex/own-capital-sustainable-return`; do not enable
auto-merge or merge it.

- [ ] **Step 2: Verify exact-head CI and independent review**

Require the explicit semantic CI step, all Operator Proxy contracts, security,
phase1, hygiene, and nontrading checks on the exact PR head. Review the diff
independently, rerun fresh verification, and report SR01-SR16 plus the positive
control.

- [ ] **Step 3: Stop for human merge authorization**

Return `BR1_READY_FOR_HUMAN_MERGE_AUTHORIZATION`. Keep H1 and BR2 unauthorized,
persistent Agent Loop deferred, schedulers disabled, and all five hard limits
unchanged.



PERSISTENT_AGENT_LOOP=DEFERRED; SCHEDULERS=DISABLED.
