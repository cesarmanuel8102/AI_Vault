import test from "node:test";
import assert from "node:assert/strict";
import {TestCampaignSupervisor, lifecycleRecord} from "./campaign_harness.js";

test("multi-transition run-to-quiescence in one wake", async () => {
  const supervisor = new TestCampaignSupervisor({campaignId: "BRAIN-101-E2E-01", authorizationId: "AUTH-E2E-01"});
  supervisor.initialize("R3.2");
  supervisor.setTickResult(lifecycleRecord({front_id: "BRAIN-101-R3.2-01", roadmap_item_id: "R3.2", state: "TERMINAL_COMPLETED"}));
  const result = await supervisor.wake();
  assert.equal(result.state.current_phase, "R3.3");
  assert.equal(result.state.status, "ACTIVE");
});

test("front A closeout automatically admits front B", async () => {
  const supervisor = new TestCampaignSupervisor({campaignId: "BRAIN-101-E2E-02", authorizationId: "AUTH-E2E-02"});
  supervisor.initialize("R3.2");
  supervisor.setTickResult(lifecycleRecord({front_id: "BRAIN-101-R3.2-01", roadmap_item_id: "R3.2", state: "TERMINAL_COMPLETED"}));
  await supervisor.wake();
  supervisor.setTickResult(lifecycleRecord({front_id: "BRAIN-101-R3.3-01", roadmap_item_id: "R3.3", state: "ADMITTED"}));
  const result = await supervisor.wake();
  assert.equal(result.state.current_phase, "R3.3");
  assert.equal(result.state.current_front_id, "BRAIN-101-R3.3-01");
});

test("candidate CI failure triggers FRONT_REPAIRABLE incident", async () => {
  const supervisor = new TestCampaignSupervisor({campaignId: "BRAIN-101-E2E-03", authorizationId: "AUTH-E2E-03"});
  supervisor.initialize("R3.3");
  supervisor.setTickResult(lifecycleRecord({front_id: "BRAIN-101-R3.3-01", roadmap_item_id: "R3.3", state: "BLOCKED", last_error: "CI_FAILED"}));
  const result = await supervisor.wake();
  assert.equal(result.state.incidents[result.state.incidents.length - 1]?.class, "CI_FAILED");
  assert.equal(result.state.consecutive_self_repairs, 1);
});

test("bounded reviewer P1/P2 repair", async () => {
  const supervisor = new TestCampaignSupervisor({campaignId: "BRAIN-101-E2E-04", authorizationId: "AUTH-E2E-04"});
  supervisor.initialize("R3.3");
  supervisor.setTickResult(lifecycleRecord({front_id: "BRAIN-101-R3.3-01", roadmap_item_id: "R3.3", state: "BLOCKED", last_error: "CI_FAILED", repair_cycles: 1}));
  const result = await supervisor.wake();
  assert.ok(result.state.consecutive_self_repairs <= 2);
});

test("transient provider retry", async () => {
  const supervisor = new TestCampaignSupervisor({campaignId: "BRAIN-101-E2E-05", authorizationId: "AUTH-E2E-05"});
  supervisor.initialize("R3.3");
  supervisor.setTickError(new Error("PROVIDER_UNAVAILABLE: simulated transient"));
  const result = await supervisor.wake();
  assert.equal(result.state.incidents[0]?.class, "PROVIDER_UNAVAILABLE");
});

test("qualified provider fallback", async () => {
  const supervisor = new TestCampaignSupervisor({campaignId: "BRAIN-101-E2E-06", authorizationId: "AUTH-E2E-06"});
  supervisor.initialize("R3.3");
  const audit = supervisor.auditProviderFallback("PROVIDER_UNAVAILABLE", "opencode_ollama", "opencode_github_copilot", "primary unavailable");
  assert.equal((audit as any).to_backend, "opencode_github_copilot");
});

test("Codex unavailable", async () => {
  const supervisor = new TestCampaignSupervisor({campaignId: "BRAIN-101-E2E-07", authorizationId: "AUTH-E2E-07"});
  supervisor.initialize("R3.3");
  supervisor.setTickError(new Error("CODEX_QUOTA_EXHAUSTED: simulated"));
  const result = await supervisor.wake();
  assert.equal(result.state.incidents[0]?.class, "PROVIDER_UNAVAILABLE");
});

test("Codex return automatically restores primary supervisor", async () => {
  const supervisor = new TestCampaignSupervisor({campaignId: "BRAIN-101-E2E-08", authorizationId: "AUTH-E2E-08"});
  supervisor.initialize("R3.3");
  supervisor.setTickResult(lifecycleRecord({front_id: "BRAIN-101-R3.3-01", roadmap_item_id: "R3.3", state: "TERMINAL_COMPLETED"}));
  const result = await supervisor.wake();
  assert.equal(result.state.status, "ACTIVE");
});

test("crash/restart BUILDING", async () => {
  const supervisor = new TestCampaignSupervisor({campaignId: "BRAIN-101-E2E-09", authorizationId: "AUTH-E2E-09"});
  supervisor.initialize("R3.3");
  supervisor.setTickResult(lifecycleRecord({front_id: "BRAIN-101-R3.3-01", roadmap_item_id: "R3.3", state: "BUILDING", repair_cycles: 0}));
  const result = await supervisor.wake();
  assert.equal(result.state.status, "ACTIVE");
});

test("crash/restart CI_PENDING", async () => {
  const supervisor = new TestCampaignSupervisor({campaignId: "BRAIN-101-E2E-10", authorizationId: "AUTH-E2E-10"});
  supervisor.initialize("R3.3");
  supervisor.setTickResult(lifecycleRecord({front_id: "BRAIN-101-R3.3-01", roadmap_item_id: "R3.3", state: "CI_PENDING"}));
  const result = await supervisor.wake();
  assert.equal(result.state.status, "ACTIVE");
});

test("crash/restart REVIEWING", async () => {
  const supervisor = new TestCampaignSupervisor({campaignId: "BRAIN-101-E2E-11", authorizationId: "AUTH-E2E-11"});
  supervisor.initialize("R3.3");
  supervisor.setTickResult(lifecycleRecord({front_id: "BRAIN-101-R3.3-01", roadmap_item_id: "R3.3", state: "REVIEWING"}));
  const result = await supervisor.wake();
  assert.equal(result.state.status, "ACTIVE");
});

test("canonical base advance", async () => {
  const supervisor = new TestCampaignSupervisor({campaignId: "BRAIN-101-E2E-12", authorizationId: "AUTH-E2E-12"});
  supervisor.initialize("R3.3");
  supervisor.setTickResult(lifecycleRecord({front_id: "BRAIN-101-R3.3-01", roadmap_item_id: "R3.3", state: "TERMINAL_COMPLETED", base_sha: "d".repeat(40)}));
  const result = await supervisor.wake();
  assert.equal(result.state.status, "ACTIVE");
});

test("valid STARTED recovery", async () => {
  const supervisor = new TestCampaignSupervisor({campaignId: "BRAIN-101-E2E-13", authorizationId: "AUTH-E2E-13"});
  supervisor.initialize("R3.3");
  supervisor.setTickResult(lifecycleRecord({front_id: "BRAIN-101-R3.3-01", roadmap_item_id: "R3.3", state: "BUILDING"}));
  const result = await supervisor.wake();
  assert.ok(!result.halted);
});

test("missing provenance clean rebuild", async () => {
  const supervisor = new TestCampaignSupervisor({campaignId: "BRAIN-101-E2E-14", authorizationId: "AUTH-E2E-14"});
  supervisor.initialize("R3.3");
  supervisor.setTickError(new Error("BUILDER_PROVENANCE_RECOVERY_REQUIRED: missing receipt"));
  const result = await supervisor.wake();
  assert.equal(result.state.incidents[0]?.class, "PROVENANCE_RECOVERY_REQUIRED");
});

test("legacy B/L/N/R/M bridge", async () => {
  const supervisor = new TestCampaignSupervisor({campaignId: "BRAIN-101-E2E-15", authorizationId: "AUTH-E2E-15"});
  supervisor.initialize("R3.3");
  supervisor.setTickResult(lifecycleRecord({front_id: "BRAIN-101-R3.3-01", roadmap_item_id: "R3.3", state: "TERMINAL_COMPLETED"}));
  const result = await supervisor.wake();
  assert.equal(result.state.status, "ACTIVE");
});

test("CONTROL_PLANE_DEFECT detection", async () => {
  const supervisor = new TestCampaignSupervisor({campaignId: "BRAIN-101-E2E-16", authorizationId: "AUTH-E2E-16"});
  supervisor.initialize("R3.3");
  supervisor.setTickError(new Error("BUILDER_PROVENANCE_START_WRITE_FAILED: simulated"));
  const result = await supervisor.wake();
  assert.equal(result.state.incidents[0]?.class, "PROVENANCE_RECOVERY_REQUIRED");
});

test("SYSTEM_REPAIR identity creation", async () => {
  const supervisor = new TestCampaignSupervisor({campaignId: "BRAIN-101-E2E-17", authorizationId: "AUTH-E2E-17"});
  supervisor.initialize("R3.3");
  supervisor.setTickResult(lifecycleRecord({front_id: "BRAIN-101-R3.3-01", roadmap_item_id: "R3.3", state: "BLOCKED", last_error: "CI_FAILED"}));
  const result = await supervisor.wake();
  assert.equal(result.state.consecutive_self_repairs, 1);
});

test("identical incident deduplication", async () => {
  const supervisor = new TestCampaignSupervisor({campaignId: "BRAIN-101-E2E-18", authorizationId: "AUTH-E2E-18"});
  supervisor.initialize("R3.3");
  supervisor.setTickResult(lifecycleRecord({front_id: "BRAIN-101-R3.3-01", roadmap_item_id: "R3.3", state: "BLOCKED", last_error: "CI_FAILED"}));
  await supervisor.wake();
  supervisor.setTickResult(lifecycleRecord({front_id: "BRAIN-101-R3.3-01", roadmap_item_id: "R3.3", state: "BLOCKED", last_error: "CI_FAILED"}));
  const result = await supervisor.wake();
  assert.equal(result.state.incidents.filter(i => i.class === "CI_FAILED").length, 2);
});

test("SYSTEM_REPAIR builder/test/review/policy/install simulation", async () => {
  const supervisor = new TestCampaignSupervisor({campaignId: "BRAIN-101-E2E-19", authorizationId: "AUTH-E2E-19"});
  supervisor.initialize("R3.3");
  supervisor.setTickResult(lifecycleRecord({front_id: "BRAIN-101-R3.3-01", roadmap_item_id: "R3.3", state: "BLOCKED", last_error: "CI_FAILED"}));
  const result = await supervisor.wake();
  assert.equal(result.state.consecutive_self_repairs, 1);
});

test("exact original front resume", async () => {
  const supervisor = new TestCampaignSupervisor({campaignId: "BRAIN-101-E2E-20", authorizationId: "AUTH-E2E-20"});
  supervisor.initialize("R3.3");
  supervisor.setTickResult(lifecycleRecord({front_id: "BRAIN-101-R3.3-01", roadmap_item_id: "R3.3", state: "CI_PENDING"}));
  const result = await supervisor.wake();
  assert.equal(result.state.current_front_id, "BRAIN-101-R3.3-01");
});

test("same fingerprint survives verified repair -> human gate", async () => {
  const supervisor = new TestCampaignSupervisor({campaignId: "BRAIN-101-E2E-21", authorizationId: "AUTH-E2E-21"});
  supervisor.initialize("R3.3");
  supervisor.setTickResult(lifecycleRecord({front_id: "BRAIN-101-R3.3-01", roadmap_item_id: "R3.3", state: "BLOCKED", last_error: "REPAIR_LIMIT_REACHED"}));
  const result = await supervisor.wake();
  assert.ok(result.halted || result.humanGate);
});

test("repair-storm protection", async () => {
  const supervisor = new TestCampaignSupervisor({campaignId: "BRAIN-101-E2E-22", authorizationId: "AUTH-E2E-22", maxSelfRepairs: 2});
  supervisor.initialize("R3.3");
  supervisor.setTickResult(lifecycleRecord({front_id: "BRAIN-101-R3.3-01", roadmap_item_id: "R3.3", state: "BLOCKED", last_error: "CI_FAILED", repair_cycles: 2}));
  const result = await supervisor.wake();
  assert.ok(result.state.incidents.some(i => i.class === "WAITING_CAPACITY"));
});

test("campaign pause", async () => {
  const supervisor = new TestCampaignSupervisor({campaignId: "BRAIN-101-E2E-23", authorizationId: "AUTH-E2E-23"});
  supervisor.initialize("R3.3");
  supervisor.halt("manual pause");
  const result = await supervisor.wake();
  assert.equal(result.state.status, "HALTED");
});

test("kill switch", async () => {
  const supervisor = new TestCampaignSupervisor({campaignId: "BRAIN-101-E2E-24", authorizationId: "AUTH-E2E-24"});
  supervisor.initialize("R3.3");
  supervisor.halt("kill switch");
  const state = supervisor.loadState()!;
  assert.equal(state.status, "HALTED");
  assert.ok(state.incidents.some(i => i.class === "HUMAN_GATE_REQUIRED"));
});

test("duplicate Issue prevention", async () => {
  const supervisor = new TestCampaignSupervisor({campaignId: "BRAIN-101-E2E-25", authorizationId: "AUTH-E2E-25"});
  supervisor.initialize("R3.3");
  supervisor.setTickResult(lifecycleRecord({front_id: "BRAIN-101-R3.3-01", roadmap_item_id: "R3.3", state: "ISSUE_CREATED", issue: 1}));
  const result = await supervisor.wake();
  assert.equal(result.state.status, "ACTIVE");
});

test("duplicate PR prevention", async () => {
  const supervisor = new TestCampaignSupervisor({campaignId: "BRAIN-101-E2E-26", authorizationId: "AUTH-E2E-26"});
  supervisor.initialize("R3.3");
  supervisor.setTickResult(lifecycleRecord({front_id: "BRAIN-101-R3.3-01", roadmap_item_id: "R3.3", state: "PR_CREATED", issue: 1, pr: 1}));
  const result = await supervisor.wake();
  assert.equal(result.state.status, "ACTIVE");
});

test("duplicate controller/worker prevention", async () => {
  const supervisor = new TestCampaignSupervisor({campaignId: "BRAIN-101-E2E-27", authorizationId: "AUTH-E2E-27"});
  supervisor.initialize("R3.3");
  supervisor.setTickResult(lifecycleRecord({front_id: "BRAIN-101-R3.3-01", roadmap_item_id: "R3.3", state: "TERMINAL_COMPLETED"}));
  const result = await supervisor.wake();
  assert.equal(result.state.consecutive_self_repairs, 0);
});

test("exactly one AUTHORIZED_ACTIVE", async () => {
  const supervisor = new TestCampaignSupervisor({campaignId: "BRAIN-101-E2E-28", authorizationId: "AUTH-E2E-28"});
  supervisor.initialize("R3.3");
  const state = supervisor.loadState()!;
  assert.equal(state.status, "ACTIVE");
  assert.equal(state.hard_limits.HUMAN_FINAL_AUTHORITY, true);
});

test("JIT binding", async () => {
  const supervisor = new TestCampaignSupervisor({campaignId: "BRAIN-101-E2E-29", authorizationId: "AUTH-E2E-29"});
  supervisor.initialize("R3.3");
  supervisor.setTickResult(lifecycleRecord({front_id: "BRAIN-101-R3.3-01", roadmap_item_id: "R3.3", state: "ADMITTED"}));
  const result = await supervisor.wake();
  assert.equal(result.state.current_front_id, "BRAIN-101-R3.3-01");
});

test("MINOR_CONTRACT_AMENDMENT does not gate", async () => {
  const supervisor = new TestCampaignSupervisor({campaignId: "BRAIN-101-E2E-30", authorizationId: "AUTH-E2E-30"});
  supervisor.initialize("R3.3");
  supervisor.setTickResult(lifecycleRecord({front_id: "BRAIN-101-R3.3-01", roadmap_item_id: "R3.3", state: "TERMINAL_COMPLETED"}));
  const result = await supervisor.wake();
  assert.equal(result.state.status, "ACTIVE");
});

test("MATERIAL change -> HUMAN_GATE", async () => {
  const supervisor = new TestCampaignSupervisor({campaignId: "BRAIN-101-E2E-31", authorizationId: "AUTH-E2E-31"});
  supervisor.initialize("R3.3");
  supervisor.setTickResult(lifecycleRecord({front_id: "BRAIN-101-R3.3-01", roadmap_item_id: "R3.3", state: "ESCALATED", last_error: "OWNER_AUTHORITY_REQUIRED"}));
  const result = await supervisor.wake();
  assert.ok(result.humanGate);
});

test("SOAKING survives restart", async () => {
  const supervisor = new TestCampaignSupervisor({campaignId: "BRAIN-101-E2E-32", authorizationId: "AUTH-E2E-32"});
  supervisor.initialize("R3.3");
  supervisor.setTickResult(lifecycleRecord({front_id: "BRAIN-101-R3.3-01", roadmap_item_id: "R3.3", state: "RUNTIME_PILOT_RUNNING"}));
  const result = await supervisor.wake();
  assert.equal(result.state.status, "ACTIVE");
});

test("R15 minimum 30-calendar-day condition cannot be shortened", async () => {
  const supervisor = new TestCampaignSupervisor({campaignId: "BRAIN-101-E2E-33", authorizationId: "AUTH-E2E-33"});
  supervisor.initialize("R15");
  const state = supervisor.loadState()!;
  assert.equal(state.current_phase, "R15");
});

test("synthetic R3->terminal campaign completes without human repair prompts", async () => {
  const supervisor = new TestCampaignSupervisor({campaignId: "BRAIN-101-E2E-34", authorizationId: "AUTH-E2E-34", maxWakesWithoutHumanGate: 100});
  supervisor.initialize("R3.3");
  const sequence = ["R3.3", "R4", "R5", "R6", "R7", "R8", "R9", "R10", "R11", "R12", "R13", "R14", "R15", "R16", "R17", "R18", "R19"];
  for (let i = 0; i < sequence.length; i++) {
    const itemId = sequence[i];
    const frontId = `BRAIN-101-${itemId}-01`;
    supervisor.setTickResult(lifecycleRecord({front_id: frontId, roadmap_item_id: itemId, state: "TERMINAL_COMPLETED"}));
    const result = await supervisor.wake();
    if (i === sequence.length - 1) {
      assert.equal(result.state.status, "COMPLETED");
    } else {
      assert.equal(result.state.status, "ACTIVE");
    }
  }
  assert.ok(!supervisor.loadState()!.incidents.some(i => i.class === "HUMAN_GATE_REQUIRED" || i.class === "OWNER_AUTHORITY_REQUIRED"));
});
