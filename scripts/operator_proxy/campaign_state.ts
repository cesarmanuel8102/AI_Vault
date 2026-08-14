import {existsSync, mkdirSync, readFileSync, renameSync, writeFileSync, appendFileSync} from "node:fs";
import {join} from "node:path";
import {safeJson, redactSensitiveData} from "./redaction.js";

export type CampaignStatus = "ACTIVE" | "PAUSED" | "HALTED" | "COMPLETED";
export type IncidentClass =
  | "CI_FAILED"
  | "REPAIR_LIMIT_REACHED"
  | "OWNER_AUTHORITY_REQUIRED"
  | "LOCAL_PRIVILEGE_REQUIRED"
  | "POLICY_BLOCK"
  | "PROVIDER_UNAVAILABLE"
  | "PROVENANCE_RECOVERY_REQUIRED"
  | "BUILDER_ROUTER_BLOCKED"
  | "WAITING_CAPACITY"
  | "HUMAN_GATE_REQUIRED"
  | "UNKNOWN";
export type Severity = "P0" | "P1" | "P2" | "P3";

export interface IncidentRecord {
  incident_id: string;
  class: IncidentClass;
  severity: Severity;
  lifecycle_front_id: string;
  state_at_incident: string;
  detected_utc: string;
  resolved_utc?: string;
  resolution?: string;
  detail: string;
}

export interface PendingHumanGate {
  incident_id: string;
  requested_action: string;
  reason: string;
  requested_utc: string;
  authorized?: boolean;
}

export interface HardLimits {
  AUTO_MERGE: false;
  LIVE_TRADING: false;
  REAL_MONEY: false;
  CANONICAL_LOCAL_SYNC: false;
  HUMAN_FINAL_AUTHORITY: true;
}

export interface CampaignState {
  schema_version: 1;
  campaign_id: string;
  authorization_id: string;
  status: CampaignStatus;
  current_phase: string;
  current_front_id?: string;
  started_utc: string;
  last_wake_utc?: string;
  wake_count: number;
  max_wakes_without_human_gate: number;
  consecutive_self_repairs: number;
  max_consecutive_self_repairs: number;
  incidents: IncidentRecord[];
  hard_limits: HardLimits;
  pending_human_gate?: PendingHumanGate;
}

export const DEFAULT_HARD_LIMITS: HardLimits = {
  AUTO_MERGE: false,
  LIVE_TRADING: false,
  REAL_MONEY: false,
  CANONICAL_LOCAL_SYNC: false,
  HUMAN_FINAL_AUTHORITY: true,
};

function safeCampaignId(value: string): string {
  if (!/^[A-Z0-9][A-Z0-9._-]{5,127}$/.test(value)) throw new Error("campaign id invalid");
  return value;
}

export class CampaignStateStore {
  private readonly eventsPath: string;

  constructor(readonly root: string) {
    mkdirSync(root, {recursive: true});
    this.eventsPath = join(root, "campaign-events.jsonl");
  }

  private statePath(): string {
    return join(this.root, "campaign-state.json");
  }

  load(): CampaignState | undefined {
    const path = this.statePath();
    if (!existsSync(path)) return undefined;
    const state = JSON.parse(readFileSync(path, "utf8")) as CampaignState;
    if (state.schema_version !== 1 || !state.campaign_id || !state.authorization_id) throw new Error("campaign state invalid");
    return state;
  }

  save(state: CampaignState): void {
    const clean = redactSensitiveData(state);
    const path = this.statePath();
    this.atomicWrite(path, `${safeJson(clean)}\n`);
    this.appendEvent({event: "campaign_state_saved", campaign_id: state.campaign_id, status: state.status, phase: state.current_phase, wake_count: state.wake_count, updated_utc: new Date().toISOString()});
  }

  atomicWrite(path: string, payload: string): void {
    const tmp = `${path}.${process.pid}.tmp`;
    writeFileSync(tmp, payload, {flag: "wx"});
    renameSync(tmp, path);
  }

  appendEvent(event: Record<string, unknown>): void {
    appendFileSync(this.eventsPath, `${safeJson(event)}\n`);
  }
}

export function initialCampaignState(campaignId: string, authorizationId: string, phase: string): CampaignState {
  return {
    schema_version: 1,
    campaign_id: safeCampaignId(campaignId),
    authorization_id: authorizationId,
    status: "ACTIVE",
    current_phase: phase,
    started_utc: new Date().toISOString(),
    wake_count: 0,
    max_wakes_without_human_gate: 3,
    consecutive_self_repairs: 0,
    max_consecutive_self_repairs: 2,
    incidents: [],
    hard_limits: DEFAULT_HARD_LIMITS,
  };
}
