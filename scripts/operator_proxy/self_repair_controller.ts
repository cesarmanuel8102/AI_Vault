import {randomUUID} from "node:crypto";
import type {LifecycleRecord, ProxySpec} from "./types.js";
import type {LifecycleStore} from "./lifecycle_store.js";
import type {IncidentRecord} from "./campaign_state.js";

export interface RepairEffects {
  reconcileBlockedCiBase(spec: ProxySpec, state: LifecycleRecord, store: LifecycleStore): LifecycleRecord;
  reconcileBlockedCiChecks(spec: ProxySpec, state: LifecycleRecord, store: LifecycleStore): LifecycleRecord;
}

export class SelfRepairController {
  constructor(
    private readonly bus: unknown,
    private readonly effects: RepairEffects,
    private readonly store: LifecycleStore,
    private readonly maxAttempts: number,
  ) {}

  async attemptRepair(state: LifecycleRecord, spec: ProxySpec, incident: IncidentRecord): Promise<{repaired: boolean; record?: LifecycleRecord; incident?: IncidentRecord}> {
    if (state.repair_cycles >= this.maxAttempts) {
      const waiting: IncidentRecord = {
        ...incident,
        incident_id: randomUUID(),
        class: "WAITING_CAPACITY",
        severity: "P2",
        detail: `repair limit (${this.maxAttempts}) reached for ${incident.class}`,
        detected_utc: new Date().toISOString(),
      };
      return {repaired: false, incident: waiting};
    }

    switch (incident.class) {
      case "CI_FAILED": {
        if (state.base_sha !== spec.expected_base_sha) {
          const repaired = this.effects.reconcileBlockedCiBase(spec, state, this.store);
          return {repaired: true, record: repaired};
        }
        if (state.state === "BLOCKED" && state.last_error === "CI_FAILED") {
          const repaired = this.effects.reconcileBlockedCiChecks(spec, state, this.store);
          return {repaired: true, record: repaired};
        }
        const waiting: IncidentRecord = {
          ...incident,
          incident_id: randomUUID(),
          class: "WAITING_CAPACITY",
          severity: "P2",
          detail: "CI checks not green and no base drift to reconcile",
          detected_utc: new Date().toISOString(),
        };
        return {repaired: false, incident: waiting};
      }
      case "PROVENANCE_RECOVERY_REQUIRED":
        return {repaired: false, incident};
      case "PROVIDER_UNAVAILABLE": {
        const waiting: IncidentRecord = {
          ...incident,
          incident_id: randomUUID(),
          class: "WAITING_CAPACITY",
          severity: "P2",
          detail: `provider unavailable for ${state.front_id}`,
          detected_utc: new Date().toISOString(),
        };
        return {repaired: false, incident: waiting};
      }
      default:
        return {repaired: false, incident};
    }
  }
}
