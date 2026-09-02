import test from "node:test";
import assert from "node:assert/strict";
import {appendFileSync, mkdtempSync} from "node:fs";
import {tmpdir} from "node:os";
import {join} from "node:path";
import {LifecycleStore} from "../../../scripts/operator_proxy/lifecycle_store.js";
import {newLifecycle} from "../../../scripts/operator_proxy/autonomous_flow.js";
import {deriveReconciliationPlan, validateInvariantSet, type PlannerPorts} from "../../../scripts/operator_proxy/reconciliation.js";
import {normalizeObservedFacts} from "../../../scripts/operator_proxy/lineage.js";
import type {LifecycleRecord, NormalizedDecision, ProxySpec} from "../../../scripts/operator_proxy/types.js";

const BASE = "a".repeat(40), HEAD = "b".repeat(40);
const spec: ProxySpec = {schema_version: 1, authorization_id: "CESAR-BRAIN-101-OPERATOR-PROXY-20260722-01", repository: "cesarmanuel8102/AI_Vault", roadmap_id: "BRAIN-101", roadmap_version: "1.0.0", roadmap_item_id: "R3.4", expected_base_sha: BASE, executor: "codex_control_plane", risk: "MEDIUM", allowed_paths: ["docs/"], forbidden_paths: ["trading/"], acceptance: ["pass"], test_commands: [], deployment_allowed: false, work_branch: "control-plane/r3-4", deployment_mode: "NO_DEPLOY", front_id: "BRAIN-101-R3-4-SEMANTIC-01"};

function blockedPolicyRecord(): LifecycleRecord {
  return {...newLifecycle(spec), state: "BLOCKED", last_error: "POLICY_BLOCK", issue: 248, pr: 249, head_sha: HEAD, builder_session: `builder-recovered:${HEAD}`, reviewer_session: "reviewer:opencode_ollama:model:session", decision_id: "162a4456-dd13-4c7f-9dc0-5380f82caa85", repair_cycles: 2, completed_effects: ["issue:248", `build:${HEAD}`]};
}
function blockDecision(overrides: Partial<NormalizedDecision> = {}): NormalizedDecision {
  return {schema_version: 2, decision_key: "1".repeat(64), decision_id: "162a4456-dd13-4c7f-9dc0-5380f82caa85", authorization_id: spec.authorization_id, repository: spec.repository, issue: 248, pr: 249, base_sha: BASE, head_sha: HEAD, roadmap_id: spec.roadmap_id, roadmap_item_id: spec.roadmap_item_id, risk: "MEDIUM", deterministic_gate: "PASS", codex_review: "CHANGES_REQUESTED", review_findings_count: 4, review_consistent: true, policy_decision: "BLOCK", allowed_action: "NONE", policy_sha256: "p".repeat(64), evidence_sha256: "e".repeat(64), created_utc: new Date().toISOString(), ...overrides} as NormalizedDecision;
}
function stubBus() {
  return {issueSnapshot: () => ({state: "OPEN", body: "", labels: []}), prIdentity: () => ({headRefOid: HEAD}), prCandidatesByBranch: () => [], remoteBranchHead: () => HEAD, isAncestor: () => false, commitMessage: () => "", call: () => "{}"} as any;
}
function ports(consummated: number): PlannerPorts {
  return {checksGreenAtHead: () => true, authorizedBaseIsCanonicalTip: () => true, recordedAdoptionEvent: () => {throw new Error("none");}, loadDecision: () => undefined, verifyReceipt: () => true, verifyBridgeCandidate: () => false, decisionBoundToLineage: () => true, consummatedPayloadRepairs: () => consummated};
}
function snapshot(record: LifecycleRecord, decision: NormalizedDecision | undefined) {
  return normalizeObservedFacts(spec, record, {bus: stubBus(), loadDecision: () => decision});
}

test("semantic accounting counts only consummated payload repairs, never recovery churn", () => {
  const store = new LifecycleStore(mkdtempSync(join(tmpdir(), "semantic-")));
  assert.equal(store.consummatedPayloadRepairs(248, 249), 0);
  const events = join(store.root, "events.jsonl");
  // Lifecycle/system recovery churn: base syncs, builder failure recoveries, adoption events.
  appendFileSync(events, `${JSON.stringify({event: "lifecycle_builder_failure_base_recovered", issue: 248, pr: 249, decision_id: "d1", repair_cycle: 2})}\n`);
  appendFileSync(events, `${JSON.stringify({event: "lifecycle_blocked_ci_base_recovered", issue: 248, pr: 249})}\n`);
  appendFileSync(events, `${JSON.stringify({event: "lifecycle_verified_synchronized_builder_candidate_adopted", issue: 248, pr: 249, repair_cycle: 2})}\n`);
  assert.equal(store.consummatedPayloadRepairs(248, 249), 0);
  // One consummated payload repair, journaled twice under the same decision, counts once.
  appendFileSync(events, `${JSON.stringify({event: "lifecycle_repair_build_replaced", issue: 248, pr: 249, decision_id: "repair-1", old_head_sha: "x", new_head_sha: "y"})}\n`);
  appendFileSync(events, `${JSON.stringify({event: "lifecycle_repair_build_replaced", issue: 248, pr: 249, decision_id: "repair-1", old_head_sha: "x", new_head_sha: "y"})}\n`);
  assert.equal(store.consummatedPayloadRepairs(248, 249), 1);
  // Another front's consummation never leaks into this candidate's budget.
  appendFileSync(events, `${JSON.stringify({event: "lifecycle_repair_build_replaced", issue: 999, pr: 998, decision_id: "repair-other"})}\n`);
  assert.equal(store.consummatedPayloadRepairs(248, 249), 1);
  assert.throws(() => store.consummatedPayloadRepairs(0, 249), /identity invalid/);
});

test("resumeUnconsummatedRepair transitions POLICY_BLOCK to REPAIRING within the payload budget", () => {
  const store = new LifecycleStore(mkdtempSync(join(tmpdir(), "semantic-resume-")));
  const record = blockedPolicyRecord();
  store.save(record);
  const updated = store.resumeUnconsummatedRepair(record, 0);
  assert.equal(updated.state, "REPAIRING");
  assert.equal(updated.last_error, undefined);
  assert.equal(updated.repair_cycles, 1);
  assert.equal(updated.decision_id, record.decision_id);
  assert.equal(updated.reviewer_session, record.reviewer_session);
  const reloaded = store.load(spec.front_id!)!;
  assert.equal(reloaded.state, "REPAIRING");
});

test("resumeUnconsummatedRepair fails closed on every inadmissible shape", () => {
  const store = new LifecycleStore(mkdtempSync(join(tmpdir(), "semantic-deny-")));
  const record = blockedPolicyRecord();
  for (const drift of [
    {...record, last_error: "CI_FAILED"},
    {...record, state: "REVIEWING" as const},
    {...record, decision_id: undefined},
    {...record, reviewer_session: undefined},
    {...record, builder_session: undefined},
    {...record, completed_effects: ["issue:248"]},
  ]) assert.throws(() => store.resumeUnconsummatedRepair(drift as LifecycleRecord, 0), /denied/);
  // Budget: two consummated payload repairs exhaust the resume.
  assert.throws(() => store.resumeUnconsummatedRepair(record, 2), /denied/);
  assert.throws(() => store.resumeUnconsummatedRepair(record, -1), /denied/);
  // Accounting drift between the claimed and journaled count is denied.
  assert.throws(() => store.resumeUnconsummatedRepair(record, 1), /denied/);
});

test("planner derives RESUME_UNCONSUMMATED_REPAIR only from semantic block evidence", () => {
  const record = blockedPolicyRecord();
  const plan = deriveReconciliationPlan(snapshot(record, blockDecision()), ports(0));
  assert.equal(plan.move, "RESUME_UNCONSUMMATED_REPAIR");
  assert.equal(validateInvariantSet(snapshot(record, blockDecision()), plan, ports(0)).violations.length, 0);
  // Budget exhaustion escalates instead of resuming; invariants also refuse.
  assert.equal(deriveReconciliationPlan(snapshot(record, blockDecision()), ports(2)).move, "ESCALATE_OWNER");
  assert.ok(validateInvariantSet(snapshot(record, blockDecision()), plan, ports(2)).violations.includes("PAYLOAD_REPAIR_BUDGET_EXHAUSTED"));
});

test("planner refuses the resume for every non-semantic block", () => {
  const record = blockedPolicyRecord();
  // Review passed: nothing to repair.
  assert.notEqual(deriveReconciliationPlan(snapshot(record, blockDecision({codex_review: "PASS", review_findings_count: 0})), ports(0)).move, "RESUME_UNCONSUMMATED_REPAIR");
  // Inconsistent review evidence.
  assert.notEqual(deriveReconciliationPlan(snapshot(record, blockDecision({review_consistent: false} as any)), ports(0)).move, "RESUME_UNCONSUMMATED_REPAIR");
  // Deterministic gate failed.
  assert.notEqual(deriveReconciliationPlan(snapshot(record, blockDecision({deterministic_gate: "FAIL"})), ports(0)).move, "RESUME_UNCONSUMMATED_REPAIR");
  // High risk requires the owner.
  assert.notEqual(deriveReconciliationPlan(snapshot(record, blockDecision({risk: "HIGH"})), ports(0)).move, "RESUME_UNCONSUMMATED_REPAIR");
  // Decision bound to a different head.
  assert.notEqual(deriveReconciliationPlan(snapshot(record, blockDecision({head_sha: "c".repeat(40)})), ports(0)).move, "RESUME_UNCONSUMMATED_REPAIR");
  // Decision missing from the immutable ledger.
  assert.notEqual(deriveReconciliationPlan(snapshot(record, undefined), ports(0)).move, "RESUME_UNCONSUMMATED_REPAIR");
  // Stale base never resumes in place.
  assert.notEqual(deriveReconciliationPlan(snapshot({...record, base_sha: "9".repeat(40)}, blockDecision({base_sha: "9".repeat(40)})), ports(0)).move, "RESUME_UNCONSUMMATED_REPAIR");
  // Missing reviewer/decision evidence.
  assert.notEqual(deriveReconciliationPlan(snapshot({...record, reviewer_session: undefined}, blockDecision()), ports(0)).move, "RESUME_UNCONSUMMATED_REPAIR");
});

test("historical replay: lifecycle recovery churn alone never exhausts the payload budget", () => {
  // Replays the empirical R3.4 history: lifecycle repair_cycles reached 2 through
  // builder-failure recovery and base synchronization, while only zero or one
  // payload repair was ever consummated. The semantic budget therefore remains.
  const store = new LifecycleStore(mkdtempSync(join(tmpdir(), "semantic-replay-")));
  const events = join(store.root, "events.jsonl");
  appendFileSync(events, `${JSON.stringify({event: "lifecycle_builder_failure_base_recovered", issue: 248, pr: 249, decision_id: "85657cf4", repair_cycle: 2})}\n`);
  appendFileSync(events, `${JSON.stringify({event: "lifecycle_verified_synchronized_builder_candidate_adopted", issue: 248, pr: 249, repair_cycle: 2})}\n`);
  const record = blockedPolicyRecord();
  store.save(record);
  const consummated = store.consummatedPayloadRepairs(248, 249);
  assert.equal(consummated, 0);
  const resumed = store.resumeUnconsummatedRepair(record, consummated);
  assert.equal(resumed.state, "REPAIRING");
  assert.equal(resumed.repair_cycles, 1);
});
