import test from "node:test";
import assert from "node:assert/strict";
import {mkdtempSync, mkdirSync, writeFileSync, readFileSync} from "node:fs";
import {tmpdir} from "node:os";
import {join} from "node:path";
import {CampaignSupervisor} from "../../../scripts/operator_proxy/campaign_supervisor.js";
import {CampaignStateStore, initialCampaignState, DEFAULT_HARD_LIMITS} from "../../../scripts/operator_proxy/campaign_state.js";
import {createOwnerAuthorization, validateCampaignAuthorization, enforceHardLimits} from "../../../scripts/operator_proxy/campaign_authorization.js";
import {validateProviderSession, auditFallback} from "../../../scripts/operator_proxy/provider_role_authority.js";
import type {LifecycleRecord, ProxySpec} from "../../../scripts/operator_proxy/types.js";

function makeBus(state: LifecycleRecord, returnErr?: Error): any {
  return {
    branchHead: () => "a".repeat(40),
    fileAt: () => "{}",
    findOpenFront: () => [],
    isAncestor: () => true,
    json: () => ({}),
    repo: "cesarmanuel8102/AI_Vault",
    call: () => "",
    setMutationGuard: () => {},
    issueSnapshot: () => ({state: "OPEN", labels: ["operator:building"], body: ""}),
    prIdentity: () => ({headRefOid: state.head_sha ?? "b".repeat(40), files: []}),
    replaceIssueBodyExact: () => {},
    reconcileLabel: () => {},
    commentOnce: () => {},
    comment: () => {},
    prComment: () => {},
    label: () => {},
    createGovernedIssue: () => 1,
    merge: () => "c".repeat(40),
    createDraftPr: () => 1,
    bindPrToIssue: () => {},
    failedGovernedMerge: () => 123,
    verifyOwnerAuthorizedMerge: () => "c".repeat(40),
    issuePaused: () => false,
  };
}

function makeBoundary(): any {
  return {
    bind: () => {},
    assert: () => {},
    beginBlockedCiRecovery: () => {},
    endBlockedCiRecovery: () => {},
    bindBlockedCiRecoveryHead: () => {},
    bindPostMerge: () => {},
    beginPrivilegedInstallResume: () => {},
    assertPrivilegedInstallResumeReady: () => {},
    endPrivilegedInstallResume: () => {},
    beginNegatedRiskRecovery: () => {},
  };
}

test("initialization creates an ACTIVE campaign state", () => {
  const root = mkdtempSync(join(tmpdir(), "campaign-init-"));
  const supervisor = new CampaignSupervisor(root, makeBus({} as any), "opencode_ollama", makeBoundary(), {campaignId: "BRAIN-101-TEST-01", authorizationId: "AUTH-TEST-01"});
  const state = supervisor.initialize("R3.2");
  assert.equal(state.status, "ACTIVE");
  assert.equal(state.current_phase, "R3.2");
  assert.equal(state.hard_limits.AUTO_MERGE, false);
  assert.equal(state.hard_limits.HUMAN_FINAL_AUTHORITY, true);
  assert.ok(existsSync(join(root, "campaign-state.json")));
});

test("hard limit violations throw", () => {
  const state = initialCampaignState("BRAIN-101-TEST-02", "AUTH-TEST-02", "R3.2");
  state.hard_limits = {...DEFAULT_HARD_LIMITS, AUTO_MERGE: true as false};
  assert.throws(() => enforceHardLimits(state), /AUTO_MERGE/);
  state.hard_limits = {...DEFAULT_HARD_LIMITS, HUMAN_FINAL_AUTHORITY: false as true};
  assert.throws(() => enforceHardLimits(state), /HUMAN_FINAL_AUTHORITY/);
});

test("BLOCKED CI_FAILED triggers system repair via reconcileBlockedCiBase", async () => {
  const root = mkdtempSync(join(tmpdir(), "campaign-repair-"));
  const baseSha = "a".repeat(40), expected = "b".repeat(40), nextHead = "c".repeat(40);
  const blocked: LifecycleRecord = {
    schema_version: 1, front_id: "BRAIN-101-R3.3-01", roadmap_item_id: "R3.3",
    state: "BLOCKED", last_error: "CI_FAILED", issue: 10, pr: 11, base_sha: baseSha, head_sha: nextHead,
    builder_session: "builder-one", repair_cycles: 0, deployment_mode: "NO_DEPLOY", completed_effects: ["issue:10", `build:${nextHead}`], updated_utc: new Date().toISOString(),
  };

  let reconcileCalled = false;
  const bus = makeBus(blocked);
  (bus as any).isAncestor = () => true;

  const supervisor = new CampaignSupervisor(root, bus, "opencode_ollama", makeBoundary(), {campaignId: "BRAIN-101-TEST-03", authorizationId: "AUTH-TEST-03"});
  supervisor.initialize("R3.3");

  const realEffects = (supervisor as any).selfRepair.effects;
  realEffects.reconcileBlockedCiBase = (spec: ProxySpec, state: LifecycleRecord) => {
    reconcileCalled = true;
    assert.notEqual(state.base_sha, spec.expected_base_sha);
    return {...state, base_sha: spec.expected_base_sha, head_sha: nextHead, state: "CI_PENDING", last_error: undefined};
  };

  (supervisor as any).resolveSpec = () => ({
    schema_version: 1, authorization_id: "AUTH-TEST-03", repository: "cesarmanuel8102/AI_Vault",
    roadmap_id: "BRAIN-101", roadmap_version: "1.0.0-reconstructed-glm-harmonized", roadmap_item_id: "R3.3", expected_base_sha: expected,
    executor: "codex_control_plane", risk: "MEDIUM", allowed_paths: [], forbidden_paths: [],
    acceptance: [], test_commands: [], deployment_allowed: false, front_id: "BRAIN-101-R3.3-01",
  } as unknown as ProxySpec);

  const state = supervisor.loadState()!;
  state.current_front_id = "BRAIN-101-R3.3-01";
  supervisor.saveState(state);

  const lifecycle = {...blocked};
  const result = await (supervisor as any).selfRepair.attemptRepair(lifecycle, (supervisor as any).resolveSpec(state, lifecycle), {
    incident_id: "i-1", class: "CI_FAILED", severity: "P1", lifecycle_front_id: lifecycle.front_id,
    state_at_incident: lifecycle.state, detected_utc: new Date().toISOString(), detail: "ci failed",
  });

  assert.equal(result.repaired, true);
  assert.equal(reconcileCalled, true);
  assert.equal(result.record!.state, "CI_PENDING");
});

test("REPAIR_LIMIT_REACHED triggers human gate / halt", async () => {
  const root = mkdtempSync(join(tmpdir(), "campaign-halt-"));
  const supervisor = new CampaignSupervisor(root, makeBus({} as any), "opencode_ollama", makeBoundary(), {campaignId: "BRAIN-101-TEST-04", authorizationId: "AUTH-TEST-04"});
  supervisor.initialize("R3.3");
  const lifecycle: LifecycleRecord = {
    schema_version: 1, front_id: "BRAIN-101-R3.3-01", roadmap_item_id: "R3.3",
    state: "BLOCKED", last_error: "REPAIR_LIMIT_REACHED", base_sha: "a".repeat(40), head_sha: "b".repeat(40),
    repair_cycles: 2, deployment_mode: "NO_DEPLOY", completed_effects: [], updated_utc: new Date().toISOString(),
  };
  const classification = (await import("../../../scripts/operator_proxy/incident_classifier.js")).classifyIncident(lifecycle);
  assert.equal(classification.class, "REPAIR_LIMIT_REACHED");
  assert.ok((await import("../../../scripts/operator_proxy/incident_classifier.js")).isHalt(classification.class, classification.severity));
  assert.ok((await import("../../../scripts/operator_proxy/incident_classifier.js")).isHumanGate(classification.class));
});

test("OWNER_AUTHORITY_REQUIRED triggers human gate", async () => {
  const lifecycle: LifecycleRecord = {
    schema_version: 1, front_id: "BRAIN-101-R3.3-01", roadmap_item_id: "R3.3",
    state: "ESCALATED", last_error: "OWNER_AUTHORITY_REQUIRED", base_sha: "a".repeat(40), head_sha: "b".repeat(40),
    repair_cycles: 0, deployment_mode: "NO_DEPLOY", completed_effects: [], updated_utc: new Date().toISOString(),
  };
  const {classifyIncident, isHumanGate, isHalt} = await import("../../../scripts/operator_proxy/incident_classifier.js");
  const c = classifyIncident(lifecycle);
  assert.equal(c.class, "OWNER_AUTHORITY_REQUIRED");
  assert.ok(isHumanGate(c.class));
  assert.ok(!isHalt(c.class, c.severity));
});

test("terminal completed advances phase and status", async () => {
  const root = mkdtempSync(join(tmpdir(), "campaign-complete-"));
  const lifecycle: LifecycleRecord = {
    schema_version: 1, front_id: "BRAIN-101-R3.2-01", roadmap_item_id: "R3.2",
    state: "TERMINAL_COMPLETED", base_sha: "a".repeat(40), head_sha: "b".repeat(40),
    repair_cycles: 0, deployment_mode: "NO_DEPLOY", completed_effects: [], updated_utc: new Date().toISOString(),
  };
  const supervisor = new CampaignSupervisor(root, makeBus(lifecycle), "opencode_ollama", makeBoundary(), {campaignId: "BRAIN-101-TEST-05", authorizationId: "AUTH-TEST-05"});
  supervisor.initialize("R3.2");
  const state = supervisor.loadState()!;
  state.current_front_id = lifecycle.front_id;
  supervisor.saveState(state);
  (supervisor as any).runTick = async () => lifecycle;
  const result = await supervisor.wake();
  assert.equal(result.state.current_phase, "R3.3");
  assert.equal(result.state.status, "ACTIVE");
});

test("provider role authority rejects mixed builder/owner sessions and audits fallback", () => {
  const ownerSession = {provider: "owner-vault", model: "owner/model", session_id: "owner:01"};
  const builderSession = {provider: "owner-vault", model: "builder/model", session_id: "builder:01"};
  assert.throws(() => validateProviderSession("builder", "builder/model", builderSession, []), /must not equal owner or supervisor/);
  const log = [auditFallback("PROVIDER_UNAVAILABLE", "opencode_ollama", "owner-vault", "fallback for owner gate")];
  assert.equal(log[0].failure_class, "PROVIDER_UNAVAILABLE");
  assert.equal(log[0].to_backend, "owner-vault");
});

test("campaign authorization validates owner signature", () => {
  const state = initialCampaignState("BRAIN-101-TEST-06", "AUTH-TEST-06", "R3.3");
  const auth = createOwnerAuthorization(state.campaign_id, state.authorization_id, "WAKE", "test");
  assert.doesNotThrow(() => validateCampaignAuthorization(state, auth));
  assert.throws(() => validateCampaignAuthorization(state, {...auth, owner_signature: "bad"}), /owner signature invalid/);
  assert.throws(() => validateCampaignAuthorization(state, {...auth, action: "TRADE"}), /action invalid/);
});

function existsSync(path: string): boolean {
  try {
    readFileSync(path);
    return true;
  } catch {
    return false;
  }
}

const runAutonomousRoadmapTick = (bus: any, root: string, reviewerRepo: string, boundary: any): LifecycleRecord => {
  return {state: "TERMINAL_COMPLETED", front_id: "BRAIN-101-R3.2-01", roadmap_item_id: "R3.2", base_sha: "a".repeat(40), repair_cycles: 0, deployment_mode: "NO_DEPLOY", completed_effects: [], updated_utc: new Date().toISOString(), schema_version: 1} as LifecycleRecord;
};
