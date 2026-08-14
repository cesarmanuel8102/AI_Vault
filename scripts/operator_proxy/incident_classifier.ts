import type {LifecycleRecord} from "./types.js";
import type {IncidentClass, Severity, IncidentRecord} from "./campaign_state.js";

export function classifyIncident(state: LifecycleRecord, error?: unknown): {class: IncidentClass; severity: Severity; detail: string} {
  const last = state.last_error;
  const message = error instanceof Error ? error.message : typeof error === "string" ? error : "";
  const detail = last ?? message ?? "unspecified incident";
  const map: Record<string, IncidentClass> = {
    CI_FAILED: "CI_FAILED",
    REPAIR_LIMIT_REACHED: "REPAIR_LIMIT_REACHED",
    OWNER_AUTHORITY_REQUIRED: "OWNER_AUTHORITY_REQUIRED",
    LOCAL_PRIVILEGE_REQUIRED: "LOCAL_PRIVILEGE_REQUIRED",
    POLICY_BLOCK: "POLICY_BLOCK",
    PROVIDER_UNAVAILABLE: "PROVIDER_UNAVAILABLE",
    PROVENANCE_RECOVERY_REQUIRED: "PROVENANCE_RECOVERY_REQUIRED",
    BUILDER_ROUTER_BLOCKED: "BUILDER_ROUTER_BLOCKED",
    WAITING_CAPACITY: "WAITING_CAPACITY",
    HUMAN_GATE_REQUIRED: "HUMAN_GATE_REQUIRED",
  };
  const resolved = map[last ?? ""] ?? (message.includes("provider") ? "PROVIDER_UNAVAILABLE" : message.includes("provenance") ? "PROVENANCE_RECOVERY_REQUIRED" : "UNKNOWN");
  const severity: Severity = resolved === "POLICY_BLOCK" || resolved === "REPAIR_LIMIT_REACHED" ? "P0" : resolved === "CI_FAILED" || resolved === "PROVENANCE_RECOVERY_REQUIRED" ? "P1" : resolved === "OWNER_AUTHORITY_REQUIRED" || resolved === "LOCAL_PRIVILEGE_REQUIRED" || resolved === "HUMAN_GATE_REQUIRED" ? "P0" : resolved === "PROVIDER_UNAVAILABLE" ? "P2" : "P3";
  return {class: resolved, severity, detail};
}

export function isSystemRepairable(incidentClass: IncidentClass): boolean {
  return ["CI_FAILED", "PROVENANCE_RECOVERY_REQUIRED", "PROVIDER_UNAVAILABLE"].includes(incidentClass);
}

export function isHumanGate(incidentClass: IncidentClass): boolean {
  return ["OWNER_AUTHORITY_REQUIRED", "LOCAL_PRIVILEGE_REQUIRED", "HUMAN_GATE_REQUIRED", "REPAIR_LIMIT_REACHED"].includes(incidentClass);
}

export function isHalt(incidentClass: IncidentClass, severity: Severity): boolean {
  return (incidentClass === "POLICY_BLOCK" && severity === "P0") || incidentClass === "REPAIR_LIMIT_REACHED";
}
