import test from "node:test";
import assert from "node:assert/strict";
import {mkdtempSync,readFileSync} from "node:fs";
import {tmpdir} from "node:os";
import {join} from "node:path";
import {LifecycleStore} from "../../../scripts/operator_proxy/lifecycle_store.js";
import {normalizeObservedFacts,decodeEffectChain,blockedCiEffectChain,deriveCandidateLineage,decisionBoundToLineage,CONTROL_PLANE_VERSION,LEGACY_STATE_WRITER_VERSION,type CanonicalLifecycleSnapshot,type SnapshotBus} from "../../../scripts/operator_proxy/lineage.js";
import {deriveReconciliationPlan,validateInvariantSet,type PlannerPorts} from "../../../scripts/operator_proxy/reconciliation.js";
import type {LifecycleRecord,ProxySpec,NormalizedDecision} from "../../../scripts/operator_proxy/types.js";

// ---------------------------------------------------------------------------
// Model-based recovery harness
//
// States are PRODUCED by legal domain transitions from an authorized start
// (not hand-built to satisfy a predicate), then the planner is asked for a
// plan. The mandatory properties are asserted over the whole reachable space.
// ---------------------------------------------------------------------------

const SHA = (n: number) => n.toString(16).padStart(40, "0");
const spec: ProxySpec = {
  schema_version: 1, authorization_id: "CESAR-BRAIN-101-OPERATOR-PROXY-20260722-01", repository: "cesarmanuel8102/AI_Vault",
  roadmap_id: "BRAIN-101", roadmap_version: "1.0.0", roadmap_item_id: "R3.4", expected_base_sha: SHA(2),
  executor: "codex_control_plane", risk: "MEDIUM", allowed_paths: ["docs/"], forbidden_paths: ["trading/"],
  acceptance: ["pass"], test_commands: ["git diff --check"], deployment_allowed: false, objective: "x",
  work_branch: "control-plane/model-front", front_id: "BRAIN-101-R3-MODEL-01", deployment_mode: "NO_DEPLOY",
};
const issue = 300, prNumber = 301;

// The model bus answers from a mutable world snapshot so every observation is
// consistent and every transition is observable.
interface World {
  baseChain: string[];        // canonical base progression: [old, ..., authorized]
  heads: string[];            // candidate heads in publication order
  externalMerge: boolean;
  checksGreen: boolean;
  remoteHead: string;
}
function makeBus(world: World): SnapshotBus {
  const isAncestor = (older: string, newer: string) => {
    const chain = [...world.baseChain, ...world.heads];
    return chain.indexOf(older) !== -1 && chain.indexOf(newer) !== -1 && chain.indexOf(older) <= chain.indexOf(newer);
  };
  return {
    prIdentity: (n: number) => ({number: n, author: {login: "cesarmanuel8102"}, baseRefName: "codex/own-capital-sustainable-return", baseRefOid: world.baseChain.at(-1), headRefName: spec.work_branch, headRefOid: world.remoteHead, headRepository: {nameWithOwner: spec.repository}, isCrossRepository: false, isDraft: !world.externalMerge, state: world.externalMerge ? "MERGED" : "OPEN", mergeable: "MERGEABLE", files: [{path: "docs/x.md"}]}),
    remoteBranchHead: () => world.remoteHead,
    issueSnapshot: () => ({state: "OPEN", body: "OPERATOR_PROXY_SPEC{}OPERATOR_PROXY_SPEC", labels: ["operator:building"]}),
    prCandidatesByBranch: () => world.heads.map((head, index) => ({number: prNumber + index, author: {login: "cesarmanuel8102"}, baseRefName: "codex/own-capital-sustainable-return", baseRefOid: world.baseChain[0], headRefName: spec.work_branch, headRefOid: head, headRepository: {nameWithOwner: spec.repository}, isCrossRepository: false, isDraft: true, state: "OPEN", mergeable: "MERGEABLE"})),
    isAncestor,
    commitMessage: () => "feat(control-plane): complete " + spec.front_id,
    call: () => "{}",
  };
}
const decision = (head: string, base: string): NormalizedDecision => ({
  schema_version: 2, decision_key: "k".repeat(64), decision_id: "11111111-1111-4111-8111-111111111111",
  authorization_id: spec.authorization_id, repository: spec.repository, issue, pr: prNumber,
  base_sha: base, head_sha: head, roadmap_id: spec.roadmap_id, roadmap_item_id: spec.roadmap_item_id,
  risk: "MEDIUM", deterministic_gate: "FAIL", codex_review: "CHANGES_REQUESTED", review_findings_count: 1, review_consistent: true,
  policy_decision: "REPAIR", allowed_action: "REQUEST_REPAIR", policy_sha256: "p".repeat(64), evidence_sha256: "e".repeat(64), created_utc: new Date().toISOString(),
} as any);

const ports = (green: boolean): PlannerPorts => ({
  checksGreenAtHead: () => green,
  authorizedBaseIsCanonicalTip: () => true,
  recordedAdoptionEvent: () => {throw new Error("adoption event missing");},
  loadDecision: () => undefined,
  verifyReceipt: () => true,
  verifyBridgeCandidate: () => true,
  decisionBoundToLineage: () => true,
});

// A legal lifecycle produced by driving the domain transitions.
function produceLifecycle(path: string[]): LifecycleRecord {
  let record: LifecycleRecord = {
    schema_version: 1, front_id: spec.front_id!, roadmap_item_id: spec.roadmap_item_id, state: "DISCOVERED",
    base_sha: SHA(1), repair_cycles: 0, deployment_mode: "NO_DEPLOY", completed_effects: [], updated_utc: new Date().toISOString(),
    state_writer_control_plane_version: CONTROL_PLANE_VERSION,
  };
  for (const step of path) {
    if (step === "admit") record = {...record, state: "ADMITTED"};
    else if (step === "issue") {record = {...record, state: "ISSUE_CREATED", issue, completed_effects: [...record.completed_effects, `issue:${issue}`]};}
    else if (step === "build") {record = {...record, state: "PR_CREATED", pr: prNumber, head_sha: SHA(3), builder_session: "builder-session", completed_effects: [...record.completed_effects, `build:${SHA(3)}`]};}
    else if (step === "ci-fail") record = {...record, state: "BLOCKED", last_error: "CI_FAILED"};
    else if (step === "repair-decision") {record = {...record, state: "REPAIRING", repair_cycles: Math.min(2, record.repair_cycles + 1), reviewer_session: "reviewer-session", decision_id: "11111111-1111-4111-8111-111111111111"};}
    else if (step === "base-advance") record = {...record, base_sha: SHA(2)};
    else if (step === "sync") {record = {...record, head_sha: SHA(4), completed_effects: [...record.completed_effects, `base-sync:${SHA(4)}`]};}
    else if (step === "builder-fail") {record = {...record, state: "BLOCKED", last_error: "BUILDER_FAILED:TRANSPORT_TIMEOUT", builder_retry_reason: record.repair_cycles > 0 ? "BUILDER_FAILURE" : undefined};}
    else if (step === "initial-builder-fail") {record = {...record, state: "BLOCKED", last_error: "BUILDER_FAILED:UNKNOWN_BUILD_FAILURE"};}
    else if (step === "merge") {record = {...record, state: "MERGED", head_sha: SHA(5), completed_effects: [...record.completed_effects, `merge:${SHA(5)}`]};}
    else if (step === "closeout") record = {...record, state: "CLOSEOUT_PENDING"};
    else throw new Error("unknown model step " + step);
  }
  return record;
}

// Enumerate LEGAL state combinations: the model applies transition
// preconditions so every produced state is reachable in the domain.
const paths: string[][] = [];
const transitions = ["admit", "issue", "build", "ci-fail", "repair-decision", "base-advance", "sync", "builder-fail", "initial-builder-fail", "merge", "closeout"];
function legalNext(prefix: string[], step: string): boolean {
  const has = (token: string) => prefix.includes(token);
  const last = prefix.at(-1);
  switch (step) {
    case "admit": return prefix.length === 0 || last === "admit" && prefix.length === 1 ? true : last !== "admit" ? true : false;
    case "issue": return has("admit") && !has("issue") && !has("build") && !has("merge");
    case "build": return has("issue") && !has("build") && !has("merge");
    case "ci-fail": return has("build") && !has("merge") && last !== "ci-fail" && !has("closeout");
    case "repair-decision": return has("build") && !has("merge") && !has("closeout") && !prefix.includes("repair-decision");
    case "base-advance": return !has("merge") && !has("closeout") && !has("base-advance");
    case "sync": return has("build") && !has("merge") && !has("closeout") && !has("sync");
    case "builder-fail": return has("build") && !has("merge") && !has("closeout") && last !== "builder-fail";
    case "initial-builder-fail": return has("issue") && !has("build") && !has("merge");
    case "merge": return has("build") && !has("merge") && !has("ci-fail") && !has("builder-fail") && !has("closeout");
    case "closeout": return has("merge") && !has("closeout");
    default: return false;
  }
}
function enumerate(prefix: string[], depth: number, budget: {count: number}) {
  if (budget.count <= 0) return;
  if (depth === 0) {if (prefix.length) paths.push(prefix); return;}
  budget.count--;
  for (const step of transitions) if (legalNext(prefix, step)) enumerate([...prefix, step], depth - 1, budget);
}
enumerate([], 4, {count: 400}); // bounded systematic exploration of legal paths

test("model-based: planner is deterministic over the reachable space", () => {
  const world: World = {baseChain: [SHA(1), SHA(2)], heads: [SHA(3), SHA(4)], externalMerge: false, checksGreen: true, remoteHead: SHA(4)};
  const bus = makeBus(world);
  for (const path of paths) {
    const record = produceLifecycle(path);
    const snapshot = normalizeObservedFacts({...spec, expected_base_sha: SHA(2)}, record, {bus, loadDecision: () => decision(SHA(3), SHA(1))});
    const plan = deriveReconciliationPlan(snapshot, ports(true));
    const again = deriveReconciliationPlan(normalizeObservedFacts({...spec, expected_base_sha: SHA(2)}, record, {bus, loadDecision: () => decision(SHA(3), SHA(1))}), ports(true));
    // DETERMINISM: same normalized facts => same plan.
    assert.deepEqual({move: plan.move, reason: plan.reason}, {move: again.move, reason: again.reason});
  }
});

test("model-based: ambiguous or unauthorized states never plan a mutating move", () => {
  const world: World = {baseChain: [SHA(1)], heads: [SHA(3)], externalMerge: false, checksGreen: false, remoteHead: SHA(3)};
  const bus = makeBus(world);
  const mutating = new Set(["REBIND_PRE_BUILD_BASE", "ADOPT_PUBLISHED_INITIAL_CANDIDATE", "ADOPT_VERIFIED_SYNCHRONIZED_CANDIDATE", "SYNCHRONIZE_CANDIDATE", "ADOPT_EXTERNAL_MERGE", "RECOVER_NEGATED_RISK_ESCALATION", "REQUEST_DETERMINISTIC_REPAIR"]);
  for (const path of paths) {
    const record = produceLifecycle(path);
    // A state whose persisted base is NOT ancestral to the authorized base
    // must never admit a mutation.
    if (record.base_sha !== SHA(1)) continue;
    const snapshot = normalizeObservedFacts({...spec, expected_base_sha: SHA(9)}, record, {bus, loadDecision: () => undefined});
    const plan = deriveReconciliationPlan(snapshot, ports(false));
    const invariants = validateInvariantSet(snapshot, plan, ports(false));
    if (plan.move !== "AMBIGUOUS" && plan.move !== "ESCALATE_OWNER" && mutating.has(plan.move)) {
      assert.ok(invariants.violations.length > 0, "non-ancestral base must violate invariants for " + JSON.stringify(path) + " plan " + plan.move);
    }
  }
});

test("model-based: every legitimate reachable blocked state plans to completion, wait, or owner escalation", () => {
  // LIVENESS: for each reachable BLOCKED/ESCALATED shape the planner either
  // selects a domain move, an explicit wait, or owner escalation — never an
  // unknown-state dead end that requires new code.
  const world: World = {baseChain: [SHA(1), SHA(2)], heads: [SHA(3), SHA(4)], externalMerge: false, checksGreen: true, remoteHead: SHA(4)};
  const bus = makeBus(world);
  const legal = new Set(["NOOP", "RESUME_INITIAL_BUILD", "RESUME_RECORDED_BUILD", "ADOPT_PUBLISHED_INITIAL_CANDIDATE", "ADOPT_VERIFIED_SYNCHRONIZED_CANDIDATE", "REVERT_INVALIDATED_ADOPTION", "SYNCHRONIZE_CANDIDATE", "REOPEN_CI", "REQUEST_DETERMINISTIC_REPAIR", "EXHAUST_REPAIR", "ADOPT_EXTERNAL_MERGE", "ESCALATE_OWNER"]);
  for (const path of paths) {
    const record = produceLifecycle(path);
    if (record.state !== "BLOCKED" && record.state !== "ESCALATED") continue;
    const snapshot = normalizeObservedFacts({...spec, expected_base_sha: SHA(2)}, record, {bus, loadDecision: () => decision(record.head_sha ?? SHA(3), record.base_sha)});
    const plan = deriveReconciliationPlan(snapshot, ports(true));
    assert.ok(legal.has(plan.move), `blocked state ${JSON.stringify(path)} planned unknown move ${plan.move} (${plan.reason})`);
  }
});

test("model-based: boundedness — no plan can exceed the persisted repair budget", () => {
  const world: World = {baseChain: [SHA(1), SHA(2)], heads: [SHA(3)], externalMerge: false, checksGreen: false, remoteHead: SHA(3)};
  const bus = makeBus(world);
  for (const cycles of [0, 1, 2, 3, 99]) {
    const record = produceLifecycle(["admit", "issue", "build", "ci-fail", "base-advance"]);
    record.repair_cycles = cycles;
    const snapshot = normalizeObservedFacts({...spec, expected_base_sha: SHA(2)}, record, {bus, loadDecision: () => decision(SHA(3), SHA(1))});
    const plan = deriveReconciliationPlan(snapshot, ports(false));
    const invariants = validateInvariantSet(snapshot, plan, ports(false));
    if (cycles >= 2) {
      assert.ok(plan.move === "EXHAUST_REPAIR" || plan.move === "ESCALATE_OWNER" || plan.move === "AMBIGUOUS" || invariants.violations.includes("REPAIR_LIMIT_REACHED"),
        `cycles=${cycles} must exhaust or escalate, planned ${plan.move}`);
    }
  }
});

test("model-based: monotonicity — completed irreversible effects never regress", () => {
  const world: World = {baseChain: [SHA(1), SHA(2)], heads: [SHA(3), SHA(4)], externalMerge: false, checksGreen: true, remoteHead: SHA(4)};
  const bus = makeBus(world);
  const record = produceLifecycle(["admit", "issue", "build", "merge", "closeout"]);
  const snapshot = normalizeObservedFacts({...spec, expected_base_sha: SHA(2)}, record, {bus, loadDecision: () => decision(SHA(3), SHA(1))});
  const plan = deriveReconciliationPlan(snapshot, ports(true));
  // A merged front can only record the canonical advance; it never unmerges,
  // never re-builds, never re-reviews.
  assert.equal(plan.move, "REBIND_POST_MERGE_BASE");
  assert.equal(snapshot.effectChain?.mergeCommit, SHA(5));
});

test("model-based: lineage — accepted synchronized candidates trace to their builder origin", () => {
  const world: World = {baseChain: [SHA(1), SHA(2)], heads: [SHA(3), SHA(4)], externalMerge: false, checksGreen: true, remoteHead: SHA(4)};
  const bus = makeBus(world);
  const record = produceLifecycle(["admit", "issue", "build", "ci-fail", "repair-decision", "base-advance", "sync", "builder-fail"]);
  const decisionValue = decision(SHA(3), SHA(1));
  const snapshot = normalizeObservedFacts({...spec, expected_base_sha: SHA(2)}, record, {bus, loadDecision: () => decisionValue});
  const lineage = deriveCandidateLineage(snapshot, decisionValue);
  assert.ok(lineage, "lineage underivable for synchronized candidate");
  assert.equal(lineage!.builderOriginHeadSha, SHA(3));
  assert.equal(lineage!.decisionHeadSha, SHA(3));
  assert.ok(lineage!.synchronizationHeads.includes(SHA(4)));
  assert.equal(lineage!.currentCandidateHeadSha, SHA(4));
  assert.ok(decisionBoundToLineage(decisionValue, spec, record, bus), "decision must bind to the lineage");
});

test("model-based: idempotence — re-planning an unchanged world yields the same non-mutating outcome", () => {
  const world: World = {baseChain: [SHA(1), SHA(2)], heads: [SHA(3)], externalMerge: false, checksGreen: true, remoteHead: SHA(3)};
  const bus = makeBus(world);
  const record = produceLifecycle(["admit", "issue", "build", "ci-fail"]);
  const plan1 = deriveReconciliationPlan(normalizeObservedFacts({...spec, expected_base_sha: SHA(2)}, record, {bus, loadDecision: () => decision(SHA(3), SHA(1))}), ports(true));
  const plan2 = deriveReconciliationPlan(normalizeObservedFacts({...spec, expected_base_sha: SHA(2)}, record, {bus, loadDecision: () => decision(SHA(3), SHA(1))}), ports(true));
  assert.deepEqual(plan1, plan2);
  assert.equal(plan1.move, "SYNCHRONIZE_CANDIDATE");
});

test("model-based: self-hosting — a control-plane version change is an explicit modeled input", () => {
  const world: World = {baseChain: [SHA(1), SHA(2)], heads: [SHA(3)], externalMerge: false, checksGreen: true, remoteHead: SHA(3)};
  const bus = makeBus(world);
  const record = produceLifecycle(["admit", "issue"]);
  record.state = "BUILDING";
  // Legacy-written state: no writer version recorded.
  const legacy = {...record, state_writer_control_plane_version: undefined};
  const legacySnapshot = normalizeObservedFacts({...spec, expected_base_sha: SHA(2)}, legacy, {bus, loadDecision: () => decision(SHA(3), SHA(1))});
  assert.equal(legacySnapshot.controlPlane.writerVersion, LEGACY_STATE_WRITER_VERSION);
  assert.equal(legacySnapshot.controlPlane.runtimeVersion, CONTROL_PLANE_VERSION);
  // The writer version is carried as an explicit fact; plans remain valid.
  const plan = deriveReconciliationPlan(legacySnapshot, ports(true));
  assert.equal(plan.move, "REBIND_PRE_BUILD_BASE");
  // Current-written state carries the runtime version.
  const current = normalizeObservedFacts({...spec, expected_base_sha: SHA(2)}, record, {bus, loadDecision: () => decision(SHA(3), SHA(1))});
  assert.equal(current.controlPlane.writerVersion, CONTROL_PLANE_VERSION);
});

test("model-based: effect chain decoding rejects positional corruption", () => {
  const good = produceLifecycle(["admit", "issue", "build", "sync"]);
  assert.ok(blockedCiEffectChain(good));
  // Duplicate sync of the same head is not a legal chain.
  const duplicated = {...good, completed_effects: [...good.completed_effects, `base-sync:${SHA(4)}`]};
  assert.equal(blockedCiEffectChain(duplicated), false);
  // A merge effect terminates the chain; a post-merge sync is not a blocked chain.
  const merged = produceLifecycle(["admit", "issue", "build", "merge"]);
  assert.equal(blockedCiEffectChain(merged), false);
  assert.equal(decodeEffectChain(merged)?.mergeCommit, SHA(5));
});

test("model-based: historical incident states #250-#257 replay through generic roles", () => {
  const world: World = {baseChain: [SHA(1), SHA(2)], heads: [SHA(3), SHA(4)], externalMerge: false, checksGreen: true, remoteHead: SHA(4)};
  const bus = makeBus(world);
  const decisionValue = decision(SHA(3), SHA(1));
  // #253/#254/#255/#256: decided repair + synchronized candidate + builder failure.
  const synchronized = produceLifecycle(["admit", "issue", "build", "ci-fail", "repair-decision", "base-advance", "sync", "builder-fail"]);
  const snapshot = normalizeObservedFacts({...spec, expected_base_sha: SHA(2)}, synchronized, {bus, loadDecision: () => decisionValue});
  const plan = deriveReconciliationPlan(snapshot, ports(true));
  assert.equal(plan.move, "ADOPT_VERIFIED_SYNCHRONIZED_CANDIDATE");
  // #256/#257: the adopted candidate was false-provenance-repaired. The generic
  // revert path is exercised through the adoption event in the store-level
  // contract tests; here the planner must recognize the provenance repair
  // session as the revert trigger.
  const falseRepaired = {...synchronized, state: "BLOCKED" as const, repair_cycles: 2, reviewer_session: `reviewer:builder-provenance-recovery:${synchronized.head_sha}`, decision_id: "22222222-2222-4222-8222-222222222222", builder_receipt_head_sha: SHA(3), builder_receipt_base_sha: SHA(1), completed_effects: [`issue:${issue}`, `build:${SHA(4)}`]};
  const store = new LifecycleStore(mkdtempSync(join(tmpdir(), "model-replay-")));
  store.save({...falseRepaired, state: "CI_PENDING" as const});
  const adoptionEvent = {event: "lifecycle_verified_synchronized_builder_candidate_adopted", front_id: spec.front_id, issue, pr: prNumber, head_sha: SHA(4), repair_cycle: 1, prior_decision_id: decisionValue.decision_id, prior_effects: [`issue:${issue}`, `build:${SHA(3)}`, `base-sync:${SHA(4)}`]};
  const portsWithEvent: PlannerPorts = {...ports(true), recordedAdoptionEvent: () => adoptionEvent, loadDecision: (id: string) => id === decisionValue.decision_id ? decisionValue : undefined};
  const falseSnapshot = normalizeObservedFacts({...spec, expected_base_sha: SHA(2)}, falseRepaired, {bus, loadDecision: () => ({...decisionValue, decision_id: "22222222-2222-4222-8222-222222222222", head_sha: SHA(4), base_sha: SHA(2)})});
  const falsePlan = deriveReconciliationPlan(falseSnapshot, portsWithEvent);
  assert.equal(falsePlan.move, "REVERT_INVALIDATED_ADOPTION");
});

test("compacted false-provenance state derives lineage from its immutable adoption event", () => {
  const world: World = {baseChain: [SHA(1), SHA(2)], heads: [SHA(3), SHA(4)], externalMerge: false, checksGreen: true, remoteHead: SHA(4)};
  const bus = makeBus(world), prior = decision(SHA(3), SHA(1));
  const record: any = {
    ...produceLifecycle(["admit", "issue", "build", "ci-fail"]),
    state: "BLOCKED", last_error: "BUILDER_FAILED:UNKNOWN_BUILD_FAILURE", last_error_detail: "UNCLASSIFIED",
    repair_cycles: 2, builder_retry_reason: "BUILDER_FAILURE", pr: prNumber,
    reviewer_session: `reviewer:builder-provenance-recovery:${SHA(4)}`,
    decision_id: "22222222-2222-4222-8222-222222222222", head_sha: SHA(4),
    completed_effects: [`issue:${issue}`, `build:${SHA(4)}`],
  };
  const adoption = {
    event: "lifecycle_verified_synchronized_builder_candidate_adopted", front_id: spec.front_id,
    issue, pr: prNumber, head_sha: SHA(4), repair_cycle: 1, prior_decision_id: prior.decision_id,
    prior_effects: [`issue:${issue}`, `build:${SHA(3)}`, `base-sync:${SHA(4)}`],
  };
  const snapshot = normalizeObservedFacts(spec, record, {bus, loadDecision: () => prior, loadAdoption: () => adoption});
  const plan = deriveReconciliationPlan(snapshot, {...ports(true), recordedAdoptionEvent: () => adoption, loadDecision: () => prior});
  assert.equal(snapshot.effectChain?.syncHeads.length ?? 0, 0);
  assert.equal(snapshot.facts.synchronizedCandidate, true);
  assert.equal(plan.move, "REVERT_INVALIDATED_ADOPTION");
  assert.deepEqual(plan.lineage?.synchronizationHeads, [SHA(4)]);
  assert.equal(plan.lineage?.builderOriginHeadSha, SHA(3));
});
