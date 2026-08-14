import {join} from "node:path";
import {randomUUID} from "node:crypto";
import {runAutonomousRoadmapTick} from "./autonomous_runtime.js";
import {CampaignStateStore, initialCampaignState, type CampaignState, type IncidentRecord} from "./campaign_state.js";
import {classifyIncident, isHalt, isHumanGate, isSystemRepairable} from "./incident_classifier.js";
import {SelfRepairController, type RepairEffects} from "./self_repair_controller.js";
import {LifecycleStore} from "./lifecycle_store.js";
import {validateCampaignAuthorization, enforceHardLimits} from "./campaign_authorization.js";
import {validateProviderSession, auditFallback, type ProviderRole} from "./provider_role_authority.js";
import type {GitHubBus} from "./github_bus.js";
import type {ExternalEffectBoundary} from "./external_effect_guard.js";
import type {LifecycleRecord, ProxySpec} from "./types.js";

function nextPhase(phase: string): string {
  if (phase === "R19" || phase.startsWith("R19.")) return "COMPLETED";
  if (phase === "R3.2") return "R3.3";
  if (phase === "R3.3") return "R4";
  const match = phase.match(/^R(\d+)$/);
  if (!match) throw new Error("phase format invalid");
  const baseNum = Number.parseInt(match[1], 10);
  if (baseNum >= 19) return "COMPLETED";
  return `R${baseNum + 1}`;
}

export interface SupervisorOptions {
  maxSelfRepairs?: number;
  maxWakesWithoutHumanGate?: number;
  campaignId?: string;
  authorizationId?: string;
}

export class CampaignSupervisor {
  private readonly store: CampaignStateStore;
  private readonly selfRepair: SelfRepairController;
  private readonly maxWakesWithoutHumanGate: number;

  constructor(
    private readonly root: string,
    private readonly bus: GitHubBus,
    private readonly reviewerRepo: string,
    private readonly boundary: ExternalEffectBoundary,
    private readonly options: SupervisorOptions = {},
  ) {
    this.store = new CampaignStateStore(root);
    const lifecycleStore = new LifecycleStore(join(root, "lifecycle"));
    const repairEffects: RepairEffects = {
      reconcileBlockedCiBase: (_spec: ProxySpec, state: LifecycleRecord, _store: LifecycleStore) => state,
      reconcileBlockedCiChecks: (_spec: ProxySpec, state: LifecycleRecord, _store: LifecycleStore) => state,
    };
    this.selfRepair = new SelfRepairController(bus as any, repairEffects, lifecycleStore, options.maxSelfRepairs ?? 2);
    this.maxWakesWithoutHumanGate = options.maxWakesWithoutHumanGate ?? 3;
  }

  loadState(): CampaignState | undefined {
    return this.store.load();
  }

  saveState(state: CampaignState): void {
    this.store.save(state);
  }

  initialize(phase = "R3.2"): CampaignState {
    if (this.store.load()) throw new Error("campaign already initialized");
    const campaignId = this.options.campaignId ?? "BRAIN-101-OPERATOR-PROXY-PHASE2";
    const authorizationId = this.options.authorizationId ?? "CESAR-BRAIN-101-PHASE2-20260813-01";
    const state = initialCampaignState(campaignId, authorizationId, phase);
    this.store.save(state);
    this.store.appendEvent({event: "campaign_initialized", campaign_id: state.campaign_id, phase, started_utc: state.started_utc});
    return state;
  }

  async wake(): Promise<{status: string; state: CampaignState; incidents: IncidentRecord[]; halted?: boolean; humanGate?: boolean}> {
    let state = this.loadState();
    if (!state) throw new Error("campaign not initialized");
    enforceHardLimits(state);
    if (state.status === "HALTED") return {status: state.status, state, incidents: state.incidents, halted: true};
    if (state.status === "PAUSED" && !state.pending_human_gate?.authorized) return {status: state.status, state, incidents: state.incidents, humanGate: true};
    if (state.status === "COMPLETED") return {status: state.status, state, incidents: state.incidents};

    const frontId = state.current_front_id ?? `BRAIN-101-${state.current_phase}-01`;
    state.current_front_id = frontId;
    state.wake_count += 1;
    state.last_wake_utc = new Date().toISOString();

    let lifecycle: LifecycleRecord | undefined;
    let error: unknown;
    try {
      lifecycle = await this.runTick();
    } catch (err) {
      error = err;
    }

    let baseState = lifecycle ?? {front_id: frontId, state: "BLOCKED", last_error: error instanceof Error ? error.message : "UNKNOWN", roadmap_item_id: state.current_phase} as LifecycleRecord;
    const classification = classifyIncident(baseState, error);
    const incident: IncidentRecord = {
      incident_id: randomUUID(),
      class: classification.class,
      severity: classification.severity,
      lifecycle_front_id: baseState.front_id ?? frontId,
      state_at_incident: baseState.state,
      detected_utc: new Date().toISOString(),
      detail: classification.detail,
    };
    state.incidents.push(incident);

    if (isHalt(classification.class, classification.severity)) {
      state.status = "HALTED";
      this.store.appendEvent({event: "campaign_halted", campaign_id: state.campaign_id, incident_id: incident.incident_id, class: incident.class, severity: incident.severity, detected_utc: incident.detected_utc});
      this.store.save(state);
      return {status: state.status, state, incidents: state.incidents, halted: true};
    }

    if (isHumanGate(classification.class)) {
      state.status = "PAUSED";
      state.pending_human_gate = {
        incident_id: incident.incident_id,
        requested_action: "HUMAN_GATE_AUTHORIZE",
        reason: `${classification.class}: ${classification.detail}`,
        requested_utc: new Date().toISOString(),
      };
      this.store.save(state);
      return {status: state.status, state, incidents: state.incidents, humanGate: true};
    }

    if (isSystemRepairable(classification.class)) {
      let repaired = false;
      let repairResult: {repaired: boolean; record?: LifecycleRecord; incident?: IncidentRecord} = {repaired: false};
      const attempts = this.options.maxSelfRepairs ?? 2;
      for (let i = 0; i < attempts; i++) {
        const spec = this.resolveSpec(state, baseState);
        repairResult = await this.selfRepair.attemptRepair(baseState, spec, incident);
        if (repairResult.repaired) {
          repaired = true;
          state.consecutive_self_repairs += 1;
          if (repairResult.record) {
            baseState = repairResult.record;
            incident.resolved_utc = new Date().toISOString();
            incident.resolution = "system_repair";
          }
          break;
        }
        if (repairResult.incident && repairResult.incident.class === "WAITING_CAPACITY") {
          state.incidents.push(repairResult.incident);
          break;
        }
      }
      if (!repaired) {
        state.consecutive_self_repairs = 0;
      }
    }

    if (baseState.state === "TERMINAL_COMPLETED") {
      const next = nextPhase(state.current_phase);
      state.current_phase = next;
      state.current_front_id = undefined;
      state.consecutive_self_repairs = 0;
      if (next === "COMPLETED") state.status = "COMPLETED";
      this.store.appendEvent({event: "campaign_phase_advanced", campaign_id: state.campaign_id, phase: next, prior_front_id: baseState.front_id, advanced_utc: new Date().toISOString()});
    }

    if (state.wake_count >= this.maxWakesWithoutHumanGate && !state.pending_human_gate) {
      state.status = "PAUSED";
      state.pending_human_gate = {
        incident_id: incident.incident_id,
        requested_action: "HUMAN_GATE_AUTHORIZE",
        reason: "max wakes without human gate",
        requested_utc: new Date().toISOString(),
      };
    }

    this.store.save(state);
    return {status: state.status, state, incidents: state.incidents, humanGate: state.status === "PAUSED"};
  }

  authorizeHumanGate(authorization: unknown): void {
    const state = this.loadState();
    if (!state) throw new Error("campaign not initialized");
    validateCampaignAuthorization(state, authorization);
    if (!state.pending_human_gate) throw new Error("no pending human gate");
    if (state.pending_human_gate.incident_id !== (authorization as any).incident_id) throw new Error("human gate incident_id mismatch");
    state.pending_human_gate.authorized = true;
    state.status = "ACTIVE";
    const incident = state.incidents.find(i => i.incident_id === state.pending_human_gate!.incident_id);
    if (incident) {
      incident.resolved_utc = new Date().toISOString();
      incident.resolution = "human_authorized";
    }
    this.store.appendEvent({event: "campaign_human_gate_authorized", campaign_id: state.campaign_id, incident_id: state.pending_human_gate.incident_id, authorized_utc: new Date().toISOString()});
    this.store.save(state);
  }

  halt(reason: string): CampaignState {
    const state = this.loadState();
    if (!state) throw new Error("campaign not initialized");
    state.status = "HALTED";
    const incident: IncidentRecord = {
      incident_id: randomUUID(),
      class: "HUMAN_GATE_REQUIRED",
      severity: "P0",
      lifecycle_front_id: state.current_front_id ?? "none",
      state_at_incident: state.status,
      detected_utc: new Date().toISOString(),
      detail: reason,
    };
    state.incidents.push(incident);
    this.store.appendEvent({event: "campaign_halted", campaign_id: state.campaign_id, reason, halted_utc: incident.detected_utc});
    this.store.save(state);
    return state;
  }

  validateProviderRole(role: ProviderRole, model: string, provider_session: unknown, auditLog: unknown[]): void {
    validateProviderSession(role, model, provider_session, auditLog as any);
  }

  auditProviderFallback(failureClass: string, fromBackend: string, toBackend: string, reason: string): unknown {
    return auditFallback(failureClass, fromBackend, toBackend, reason);
  }

  protected runTick(): Promise<LifecycleRecord> {
    return runAutonomousRoadmapTick(this.bus, join(this.root, "operator_proxy"), this.reviewerRepo, this.boundary);
  }

  private resolveSpec(state: CampaignState, lifecycle: LifecycleRecord): ProxySpec {
    return {
      schema_version: 1,
      authorization_id: state.authorization_id,
      repository: "cesarmanuel8102/AI_Vault",
      roadmap_id: "BRAIN-101",
      roadmap_version: "1.0.0-reconstructed-glm-harmonized",
      roadmap_item_id: state.current_phase,
      expected_base_sha: lifecycle.base_sha ?? "a".repeat(40),
      executor: "codex_control_plane",
      risk: "MEDIUM",
      allowed_paths: [`docs/roadmap/evidence/${state.current_phase}/`],
      forbidden_paths: [".env", ".github/", "memory/", "tmp_agent/brain_v9/trading/", "financial_autonomy/", "tmp_agent/state/"],
      acceptance: ["Preserve hard constitutional limits"],
      test_commands: ["git diff --check"],
      deployment_allowed: false,
      front_id: lifecycle.front_id ?? state.current_front_id,
    } as ProxySpec;
  }
}
