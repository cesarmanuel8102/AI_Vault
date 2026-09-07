# R3.4 Codex-Governed Controller Rebaseline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Safely supersede a stranded historical lifecycle attempt when canonical functional evidence already satisfies a roadmap item, then produce a truthful Codex-governed documentation closeout without dispatching the persistent Agent Loop.

**Architecture:** Add a pure historical-attempt projection, canonical-evidence verifier, append-only controller supersession ledger, and fail-closed planner under `scripts/operator_proxy/`. The planner only emits a closeout authorization; it never dispatches builders, changes historical lifecycle, or performs GitHub effects. A separate documentation closeout uses the manifested R3.4 closeout paths and records `CODEX_GOVERNED_CONTROLLER` provenance.

**Tech Stack:** TypeScript 7, Node 25, `tsx --test`, existing Operator Proxy JSONL ledger conventions, Git plumbing, JSON roadmap artifacts.

**Spec:** `docs/superpowers/specs/2026-09-07-r3-4-codex-controller-rebaseline-design.md`

## Global Constraints

- `HUMAN_FINAL_AUTHORITY=true`; `AUTO_MERGE=false`; `CANONICAL_LOCAL_SYNC=false`; `LIVE_TRADING=false`; `REAL_MONEY=false`.
- Persistent Agent Loop and both scheduled tasks remain disabled; no worker, scheduler, installation, or Agent Loop tick is part of this plan.
- Never edit historical lifecycle files, Owner grant/receipt records, Issue #248, PR #249, or their branch.
- Source code must not reference R3.4, #248, #249, or their SHA values. Those appear only in fixtures and documentation evidence.
- All external controller receipt writes are append-only below `D:\AI_VAULT_CONTROLLER_STATE`; test roots must be temporary directories.
- The planner has no GitHub mutation, merge, builder, installation, scheduler, trading, or canonical-sync capability.

---

## Intended File Structure

- `scripts/operator_proxy/controller_rebaseline.ts`: pure historical projection, canonical evidence verification, and rebaseline planner.
- `scripts/operator_proxy/controller_supersession_ledger.ts`: canonical JSON serialization and append-only JSONL receipt chain.
- `scripts/operator_proxy/codex_controller_rebaseline.ts`: explicit, unscheduled command that appends one validated receipt and derives the controller snapshot.
- `scripts/operator_proxy/types.ts`: narrow typed records shared by the new modules.
- `tests/contract/operator_proxy/controller_rebaseline.test.ts`: pure planner and evidence contract matrix.
- `tests/contract/operator_proxy/controller_supersession_ledger.test.ts`: ledger ordering, idempotency, corruption, and conflict matrix.
- `tests/contract/operator_proxy/controller_rebaseline_boundary.test.ts`: no-effects command boundary tests.
- `tests/contract/operator_proxy/controller_rebaseline_closeout.test.ts`: truthful closeout and one-successor contract.
- The six R3.4 closeout files declared in the manifest: changed only after generic mechanism tests pass.

## Task 1: Rebaseline Types and Historical Projection

**Files:**
- Modify: `scripts/operator_proxy/types.ts`
- Create: `scripts/operator_proxy/controller_rebaseline.ts`
- Test: `tests/contract/operator_proxy/controller_rebaseline.test.ts`

**Interfaces:**
- Produces `HistoricalAttemptRefV1`, `FunctionalEvidenceAssertionV1`, `ControllerRebaselineInput`, and `ControllerRebaselinePlan`.
- Produces `projectHistoricalAttempt(record: LifecycleRecord): HistoricalAttemptRefV1`.
- Consumes only readonly `LifecycleRecord`; it receives no `LifecycleStore`.

- [ ] **Step 1: Write the failing projection tests**

```ts
test("projects one exhausted Owner attempt without changing it",()=>{
  const before=structuredClone(exhaustedOwnerRecord());
  const projected=projectHistoricalAttempt(before);
  assert.equal(projected.repair_cycles,2);
  assert.match(projected.historical_sha256,/^[0-9a-f]{64}$/);
  assert.deepEqual(before,exhaustedOwnerRecord());
});
test("rejects nonexhausted or incomplete Owner attempts",()=>{
  assert.throws(()=>projectHistoricalAttempt({...exhaustedOwnerRecord(),repair_cycles:1}));
  assert.throws(()=>projectHistoricalAttempt({...exhaustedOwnerRecord(),owner_payload_repair:undefined}));
});
```

- [ ] **Step 2: Run the test and confirm it fails**

Run: `npx tsx --test ../../tests/contract/operator_proxy/controller_rebaseline.test.ts`

Expected: FAIL because `projectHistoricalAttempt` is absent.

- [ ] **Step 3: Implement the minimum projection**

```ts
export function projectHistoricalAttempt(record: LifecycleRecord): HistoricalAttemptRefV1 {
  if (record.repair_cycles !== 2 || !record.owner_payload_repair) {
    throw new Error("historical Owner attempt is not exhausted");
  }
  const core={schema_version:1 as const,front_id:record.front_id,
    roadmap_item_id:record.roadmap_item_id,issue:record.issue,pr:record.pr,
    base_sha:record.base_sha,failed_head_sha:record.head_sha,
    repair_cycles:record.repair_cycles,...record.owner_payload_repair};
  return {...core,historical_sha256:canonicalSha256(core)};
}
```

Validate lower-case SHA fields, positive Issue/PR IDs, nonterminal lifecycle,
all three Owner anchors, and exact `repair_cycles===2`. Add no R3.4 branch.

- [ ] **Step 4: Verify the focused suite**

Run: `npx tsx --test ../../tests/contract/operator_proxy/controller_rebaseline.test.ts && npm run typecheck`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/operator_proxy/types.ts scripts/operator_proxy/controller_rebaseline.ts tests/contract/operator_proxy/controller_rebaseline.test.ts
git commit -m "feat(controller): project immutable historical attempts"
```

## Task 2: Canonical Functional-Evidence Verification

**Files:**
- Modify: `scripts/operator_proxy/controller_rebaseline.ts`
- Modify: `tests/contract/operator_proxy/controller_rebaseline.test.ts`

**Interfaces:**
- Produces `verifyFunctionalEvidenceForRebaseline(input): FunctionalEvidenceAssertionV1`.
- Input contains `{ item_id, task_id, evidence_path, canonical_ref, evidence_bytes, required_markers, hard_limits }`.
- Result binds `evidence_sha256` and `assertion_sha256`; it exposes no unverified free text.

- [ ] **Step 1: Write failing verification tests**

```ts
test("accepts pinned passed evidence with every required marker",()=>{
  assert.equal(verifyFunctionalEvidenceForRebaseline(validEvidenceInput()).status,"PASSED");
});
for(const mutate of [removePassed,removeAck,removeStage,enableLiveTrading]){
  test(`rejects ${mutate.name}`,()=>assert.throws(()=>verifyFunctionalEvidenceForRebaseline(mutate(validEvidenceInput()))));
}
```

- [ ] **Step 2: Run and confirm RED**

Run: `npx tsx --test ../../tests/contract/operator_proxy/controller_rebaseline.test.ts`

Expected: FAIL because the verifier is absent.

- [ ] **Step 3: Implement byte-pinned verification**

Require a lowercase SHA-1 ref, relative allowlisted evidence path, exact passed
status and acknowledgement, every declared pipeline marker, and all five hard
limits. Hash bytes exactly and canonicalize only the assertion object. Reject
empty, duplicate, and unknown required marker inputs.

- [ ] **Step 4: Run focused verification**

Run: `npx tsx --test ../../tests/contract/operator_proxy/controller_rebaseline.test.ts`

Expected: PASS for valid evidence and every isolated rejection.

- [ ] **Step 5: Commit**

```bash
git add scripts/operator_proxy/controller_rebaseline.ts tests/contract/operator_proxy/controller_rebaseline.test.ts
git commit -m "feat(controller): verify canonical functional evidence"
```

## Task 3: Append-Only Supersession Receipt Ledger

**Files:**
- Create: `scripts/operator_proxy/controller_supersession_ledger.ts`
- Modify: `scripts/operator_proxy/types.ts`
- Test: `tests/contract/operator_proxy/controller_supersession_ledger.test.ts`

**Interfaces:**
- Produces `ControllerSupersessionReceiptV1` and `ControllerSupersessionLedger`.
- `validate(): readonly ControllerSupersessionReceiptV1[]` verifies full JSONL chain.
- `append(receipt): ControllerSupersessionReceiptV1` is idempotent only for byte-equivalent receipt keys.

- [ ] **Step 1: Write failing ledger tests**

```ts
test("appends a chained receipt and replays exact bytes idempotently",()=>{
  const ledger=new ControllerSupersessionLedger(tempLedgerPath());
  const first=ledger.append(validReceipt());
  assert.equal(ledger.append(validReceipt()).event_sha256,first.event_sha256);
});
test("rejects conflict, duplicate sequence, and bad predecessor",()=>{
  const ledger=new ControllerSupersessionLedger(seedLedger(validReceipt()));
  assert.throws(()=>ledger.append({...validReceipt(),canonical_base_sha:"a".repeat(40)}));
  assert.throws(()=>ledger.validate(corruptPreviousHash()));
});
```

- [ ] **Step 2: Run and confirm RED**

Run: `npx tsx --test ../../tests/contract/operator_proxy/controller_supersession_ledger.test.ts`

Expected: FAIL because the ledger module is absent.

- [ ] **Step 3: Implement canonical chained JSONL**

Use stable-key JSON serialization and `sha256(Buffer.from(serialized,"utf8"))`.
Validate contiguous sequences, predecessor hashes, canonical receipt hashes,
and one exact record per `supersession_key`. Revalidate before and after atomic
append. Never truncate, rewrite, or compact the file.

- [ ] **Step 4: Run focused ledger tests**

Run: `npx tsx --test ../../tests/contract/operator_proxy/controller_supersession_ledger.test.ts`

Expected: PASS including corruption and conflict cases.

- [ ] **Step 5: Commit**

```bash
git add scripts/operator_proxy/controller_supersession_ledger.ts scripts/operator_proxy/types.ts tests/contract/operator_proxy/controller_supersession_ledger.test.ts
git commit -m "feat(controller): add append-only supersession receipts"
```

## Task 4: Pure Fail-Closed Rebaseline Planner

**Files:**
- Modify: `scripts/operator_proxy/controller_rebaseline.ts`
- Modify: `tests/contract/operator_proxy/controller_rebaseline.test.ts`
- Test: `tests/contract/operator_proxy/controller_rebaseline_boundary.test.ts`

**Interfaces:**
- Produces `planControllerRebaseline(input): ControllerRebaselinePlan` with `REBASELINE_REQUIRED`, `CLOSEOUT_ALLOWED`, `ALREADY_SUPERSEDED`, or `BLOCKED`.
- Consumes historical projection, verified evidence, canonical binding, and ledger view.
- Does not accept `GitHubBus`, `LifecycleStore`, `ExternalEffectBoundary`, builder, or scheduler dependencies.

- [ ] **Step 1: Write failing planner and boundary tests**

```ts
test("returns CLOSEOUT_ALLOWED only for exact current anchors",()=>{
  assert.equal(planControllerRebaseline(validInput()).status,"CLOSEOUT_ALLOWED");
});
test("blocks stale base, manifest drift, road map drift, or hard-limit drift",()=>{
  for(const input of invalidPlannerInputs()) assert.equal(planControllerRebaseline(input).status,"BLOCKED");
});
test("planner cannot invoke production effects",()=>{
  const effects=forbiddenEffects();
  planControllerRebaseline({...validInput(),effects});
  assert.deepEqual(effects.calls,[]);
});
```

- [ ] **Step 2: Run and confirm RED**

Run: `npx tsx --test ../../tests/contract/operator_proxy/controller_rebaseline.test.ts ../../tests/contract/operator_proxy/controller_rebaseline_boundary.test.ts`

Expected: FAIL because the planner is absent.

- [ ] **Step 3: Implement pure planning**

Build the deterministic key from repository, roadmap item, historical hash, and
assertion hash. Validate exact base, manifest, and roadmap hashes, then look up
the exact receipt key. Return `REBASELINE_REQUIRED` only before a receipt;
`CLOSEOUT_ALLOWED` only with an exact receipt; `ALREADY_SUPERSEDED` only for a
closed canonical item whose recorded receipt matches. Return `BLOCKED` with a
stable reason for every mismatch.

- [ ] **Step 4: Verify focal tests and typecheck**

Run: `npx tsx --test ../../tests/contract/operator_proxy/controller_rebaseline.test.ts ../../tests/contract/operator_proxy/controller_rebaseline_boundary.test.ts && npm run typecheck`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/operator_proxy/controller_rebaseline.ts tests/contract/operator_proxy/controller_rebaseline.test.ts tests/contract/operator_proxy/controller_rebaseline_boundary.test.ts
git commit -m "feat(controller): plan fail-closed historical supersession"
```

## Task 5: Explicit Controller Receipt Command

**Files:**
- Create: `scripts/operator_proxy/codex_controller_rebaseline.ts`
- Modify: `scripts/operator_proxy/package.json`
- Modify: `tests/contract/operator_proxy/controller_rebaseline_boundary.test.ts`

**Interfaces:**
- `runCodexControllerRebaseline(args,deps)` reads pinned Git data, validates, and appends one receipt.
- Produces `{status,supersession_key,event_sha256,controller:"CODEX_GOVERNED_CONTROLLER"}`.
- Writes `CODEX_GOVERNED_CONTROLLER_RUN.json` only after a valid ledger append and only from validated data.

- [ ] **Step 1: Write failing command tests**

```ts
test("command appends one receipt and writes a derived snapshot",()=>{
  assert.equal(runCodexControllerRebaseline(validCommandArgs(),fakeDeps()).status,"CLOSEOUT_ALLOWED");
});
test("command rejects before ledger or snapshot write when Git/evidence differs",()=>{
  const deps=fakeDeps({manifest:"wrong"});
  assert.throws(()=>runCodexControllerRebaseline(validCommandArgs(),deps));
  assert.equal(deps.writeCalls,0);
});
```

- [ ] **Step 2: Run and confirm RED**

Run: `npx tsx --test ../../tests/contract/operator_proxy/controller_rebaseline_boundary.test.ts`

Expected: FAIL because command module is absent.

- [ ] **Step 3: Implement the no-effect command**

Read canonical artifacts through injected `git show <sha>:<path>` dependencies;
use temporary paths in tests; restrict production state root to the supplied
controller root. Do not import `ProductionEffects`, `Run-OperatorProxy`,
`LifecycleStore.save`, scheduler modules, or builder adapters. Add an explicit
npm script only; it must not be scheduled or included in `npm test`.

- [ ] **Step 4: Verify command tests and typecheck**

Run: `npx tsx --test ../../tests/contract/operator_proxy/controller_rebaseline_boundary.test.ts && npm run typecheck`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/operator_proxy/codex_controller_rebaseline.ts scripts/operator_proxy/package.json tests/contract/operator_proxy/controller_rebaseline_boundary.test.ts
git commit -m "feat(controller): add explicit rebaseline receipt command"
```

## Task 6: Truthful R3.4 Closeout Artifact Contract

**Files:**
- Test: `tests/contract/operator_proxy/controller_rebaseline_closeout.test.ts`
- Modify after RED test only: `docs/roadmap/BRAIN_101_MANIFEST.json`, `docs/roadmap/BRAIN_101_ROADMAP.md`, `docs/roadmap/BRAIN_101_SCORECARD.json`, `ROADMAP_STATUS.json`, `docs/MIGRATION_CONTROL_LEDGER.md`, `docs/roadmap/evidence/BRAIN_101_R3_4_AGENT_V2_COGNITIVE_PIPELINE_E2E_CLOSEOUT.json`

**Interfaces:**
- Closeout evidence exposes `execution_controller`, `supersession_receipt_sha256`, `historical_attempt_sha256`, `functional_evidence_sha256`, `historical_attempt_disposition`, and `next_authorized_item`.

- [ ] **Step 1: Write failing closeout contract tests**

```ts
test("R3.4 closeout is truthful and controller-governed",()=>{
  const evidence=readCloseoutEvidence(candidateRoot);
  assert.equal(evidence.execution_controller,"CODEX_GOVERNED_CONTROLLER");
  assert.equal(evidence.historical_attempt_disposition,"PRESERVED_NONEXECUTABLE");
  assert.match(evidence.supersession_receipt_sha256,/^[0-9a-f]{64}$/);
});
test("closeout preserves one active successor and all hard limits",()=>{
  assert.equal(activeRoadmapItems(candidateManifest).length,1);
  assert.deepEqual(hardLimits(candidateManifest),requiredHardLimits);
});
```

- [ ] **Step 2: Run and confirm RED**

Run: `npx tsx --test ../../tests/contract/operator_proxy/controller_rebaseline_closeout.test.ts`

Expected: FAIL because current artifacts use historical Agent Loop closeout language.

- [ ] **Step 3: Implement only declared closeout artifacts**

After a real receipt exists, update exactly the six manifest-declared R3.4
closeout files. Preserve historical Issue/PR, Owner anchors, failed head, and
repair counter as immutable references. Close only after the new evidence test
passes. Authorize one next manifest item. Do not change runtime, workflow,
scheduler, config, or historical evidence.

- [ ] **Step 4: Verify closeout, sequencer, and diff**

Run: `npx tsx --test ../../tests/contract/operator_proxy/controller_rebaseline_closeout.test.ts ../../tests/contract/operator_proxy/sequencer.test.ts && git diff --check`

Expected: PASS, exactly one active item, no hard-limit regression.

- [ ] **Step 5: Commit**

```bash
git add docs/roadmap/BRAIN_101_MANIFEST.json docs/roadmap/BRAIN_101_ROADMAP.md docs/roadmap/BRAIN_101_SCORECARD.json ROADMAP_STATUS.json docs/MIGRATION_CONTROL_LEDGER.md docs/roadmap/evidence/BRAIN_101_R3_4_AGENT_V2_COGNITIVE_PIPELINE_E2E_CLOSEOUT.json tests/contract/operator_proxy/controller_rebaseline_closeout.test.ts
git commit -m "docs(roadmap): close R3.4 under Codex controller"
```

## Task 7: Regression, Safety, and Governed Publication

**Files:**
- Modify only files created by Tasks 1-6 if a failing scoped regression identifies a defect.

- [ ] **Step 1: Run focal contracts**

```bash
npx tsx --test ../../tests/contract/operator_proxy/controller_rebaseline.test.ts \
  ../../tests/contract/operator_proxy/controller_supersession_ledger.test.ts \
  ../../tests/contract/operator_proxy/controller_rebaseline_boundary.test.ts \
  ../../tests/contract/operator_proxy/controller_rebaseline_closeout.test.ts \
  ../../tests/contract/operator_proxy/sequencer.test.ts \
  ../../tests/contract/operator_proxy/owner_payload_repair_lifecycle.test.ts
```

Expected: PASS. Existing Owner payload tests prove ordinary repair semantics remain unchanged.

- [ ] **Step 2: Run full contractual regression**

Run: `npm run typecheck && npm test && git diff --check`

Expected: all tests PASS, typecheck PASS, whitespace check PASS.

- [ ] **Step 3: Run static safety scans**

```bash
rg -n "#248|#249|R3\\.4|R3_4" scripts/operator_proxy/controller_*.ts
rg -n "ProductionEffects|AgentLoopBuilder|Run-OperatorProxy|ScheduledTask|Enable-ScheduledTask|Start-ScheduledTask" scripts/operator_proxy/controller_*.ts
```

Expected: no specimen-specific production code and no privileged effect imports.

- [ ] **Step 4: Review exact scope**

Run: `git diff --check && git diff --stat origin/codex/own-capital-sustainable-return...HEAD && git status --short --untracked-files=all`

Expected: only planned modules, tests, and declared closeout artifacts.

- [ ] **Step 5: Publish and validate**

Push normal `control-plane/r3-4-codex-controller-rebaseline`, open a Draft PR,
require exact-head CI, independent review, policy, and human-authorized normal
merge. Do not auto-merge, install, schedule, or run Agent Loop. After merge,
read canonical manifest and evidence, validate the receipt, update the external
controller snapshot, and begin the sole next authorized item through the same
Codex-governed process.
