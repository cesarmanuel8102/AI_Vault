import test from "node:test";
import assert from "node:assert/strict";
import {SelfRepairOrchestrator, incidentFingerprint, type RepairOrchestrationEffects, type RepairIdentity} from "../../../scripts/operator_proxy/self_repair_orchestrator.js";
import type {LifecycleRecord, ProxySpec} from "../../../scripts/operator_proxy/types.js";
import type {IncidentRecord} from "../../../scripts/operator_proxy/campaign_state.js";

function makeSpec(): ProxySpec {
  return {
    schema_version: 1,
    authorization_id: "AUTH-REPAIR",
    repository: "owner/repo",
    roadmap_id: "BRAIN-101",
    roadmap_version: "1.0.0",
    roadmap_item_id: "R3.3",
    expected_base_sha: "a".repeat(40),
    executor: "codex_control_plane",
    risk: "MEDIUM",
    allowed_paths: ["docs/"],
    forbidden_paths: [".env"],
    acceptance: ["pass"],
    test_commands: [],
    deployment_allowed: false,
    work_branch: "control-plane/brain-101-r3.3-01",
    front_id: "BRAIN-101-R3.3-01",
  };
}

function makeLifecycle(): LifecycleRecord {
  return {
    schema_version: 1,
    front_id: "BRAIN-101-R3.3-01",
    roadmap_item_id: "R3.3",
    state: "BLOCKED",
    last_error: "CI_FAILED",
    base_sha: "a".repeat(40),
    head_sha: "b".repeat(40),
    repair_cycles: 1,
    deployment_mode: "NO_DEPLOY",
    completed_effects: [],
    updated_utc: new Date().toISOString(),
  };
}

function makeIncident(): IncidentRecord {
  return {
    incident_id: "inc-1",
    class: "CI_FAILED",
    severity: "P1",
    lifecycle_front_id: "BRAIN-101-R3.3-01",
    state_at_incident: "BLOCKED",
    detected_utc: new Date().toISOString(),
    detail: "ci failed",
  };
}

function makeEffects(overrides: Partial<RepairOrchestrationEffects> = {}): RepairOrchestrationEffects {
  return {
    freezeOriginalFront: () => {},
    createRepairIdentity: (_spec, incident, fingerprint): RepairIdentity => ({
      repair_id: `repair-${incident.incident_id}`,
      branch: `repair/${incident.incident_id}`,
      worktree: `/tmp/repair-${incident.incident_id}`,
      builder_model: "ollama-cloud/kimi-k2.7-code",
      started_utc: new Date().toISOString(),
    }),
    runBuilder: async () => ({head_sha: "c".repeat(40), files: ["docs/x.md"]}),
    runTests: async () => true,
    runReview: async () => true,
    runPolicy: async () => true,
    runMerge: async () => "d".repeat(40),
    runInstall: async () => true,
    closeRepair: () => {},
    resumeOriginalFront: () => {},
    ...overrides,
  };
}

test("incident fingerprint is stable and unique", () => {
  const lifecycle = makeLifecycle();
  const incident = makeIncident();
  const fp1 = incidentFingerprint(incident, lifecycle);
  const fp2 = incidentFingerprint(incident, lifecycle);
  assert.equal(fp1.fingerprint_sha256, fp2.fingerprint_sha256);
  assert.equal(fp1.front_id, lifecycle.front_id);
  assert.equal(fp1.failure_class, incident.class);
});

test("orchestrator freezes original front, runs builder/tests/review/policy/merge/install, then resumes", async () => {
  const lifecycle = makeLifecycle();
  const incident = makeIncident();
  const spec = makeSpec();
  const log: string[] = [];
  const effects = makeEffects({
    freezeOriginalFront: (id) => log.push(`freeze:${id}`),
    runBuilder: async (identity) => {
      log.push(`builder:${identity.repair_id}`);
      return {head_sha: "c".repeat(40), files: ["docs/x.md"]};
    },
    runTests: async (identity) => {
      log.push(`tests:${identity.repair_id}`);
      return true;
    },
    runReview: async (identity) => {
      log.push(`review:${identity.repair_id}`);
      return true;
    },
    runPolicy: async (identity) => {
      log.push(`policy:${identity.repair_id}`);
      return true;
    },
    runMerge: async (identity) => {
      log.push(`merge:${identity.repair_id}`);
      return "d".repeat(40);
    },
    runInstall: async (identity) => {
      log.push(`install:${identity.repair_id}`);
      return true;
    },
    closeRepair: (identity) => log.push(`close:${identity.repair_id}`),
    resumeOriginalFront: (id) => log.push(`resume:${id}`),
  });
  const orchestrator = new SelfRepairOrchestrator(effects);
  const result = await orchestrator.orchestrate(spec, lifecycle, incident);
  assert.equal(result.success, true);
  assert.equal(result.head_sha, "c".repeat(40));
  assert.equal(result.merged, "d".repeat(40));
  assert.equal(result.installed, true);
  assert.equal(result.resumed_front_id, lifecycle.front_id);
  assert.deepEqual(log, [
    `freeze:${lifecycle.front_id}`,
    `builder:repair-inc-1`,
    `tests:repair-inc-1`,
    `review:repair-inc-1`,
    `policy:repair-inc-1`,
    `merge:repair-inc-1`,
    `install:repair-inc-1`,
    `close:repair-inc-1`,
    `resume:${lifecycle.front_id}`,
  ]);
});

test("orchestrator deduplicates identical repair fingerprints", async () => {
  const lifecycle = makeLifecycle();
  const incident = makeIncident();
  const spec = makeSpec();
  const effects = makeEffects();
  const orchestrator = new SelfRepairOrchestrator(effects);
  await orchestrator.orchestrate(spec, lifecycle, incident);
  await assert.rejects(
    orchestrator.orchestrate(spec, lifecycle, incident),
    /duplicate repair fingerprint/,
  );
});

test("orchestrator fails closed if tests fail", async () => {
  const lifecycle = makeLifecycle();
  const incident = makeIncident();
  const spec = makeSpec();
  const effects = makeEffects({runTests: async () => false});
  const orchestrator = new SelfRepairOrchestrator(effects);
  const result = await orchestrator.orchestrate(spec, lifecycle, incident);
  assert.equal(result.success, false);
  assert.equal(result.tests_passed, false);
  assert.equal(result.merged, undefined);
});

test("orchestrator fails closed if policy blocks", async () => {
  const lifecycle = makeLifecycle();
  const incident = makeIncident();
  const spec = makeSpec();
  const effects = makeEffects({runPolicy: async () => false});
  const orchestrator = new SelfRepairOrchestrator(effects);
  const result = await orchestrator.orchestrate(spec, lifecycle, incident);
  assert.equal(result.success, false);
  assert.equal(result.policy_approved, false);
  assert.equal(result.merged, undefined);
});
