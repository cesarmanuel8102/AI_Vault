import {randomUUID, createHash} from "node:crypto";
import type {LifecycleRecord, ProxySpec} from "./types.js";
import type {IncidentRecord} from "./campaign_state.js";

export interface RepairFingerprint {
  incident_id: string;
  front_id: string;
  failure_class: string;
  base_sha: string;
  repair_cycle: number;
  fingerprint_sha256: string;
}

export interface RepairIdentity {
  repair_id: string;
  branch: string;
  worktree: string;
  builder_model: string;
  started_utc: string;
}

export interface RepairOrchestrationResult {
  repair_id: string;
  success: boolean;
  head_sha?: string;
  tests_passed: boolean;
  review_passed: boolean;
  policy_approved: boolean;
  merged?: string;
  installed?: boolean;
  resumed_front_id: string;
  incident: IncidentRecord;
}

export interface RepairOrchestrationEffects {
  freezeOriginalFront(front_id: string): void;
  createRepairIdentity(spec: ProxySpec, incident: IncidentRecord, fingerprint: RepairFingerprint): RepairIdentity;
  runBuilder(identity: RepairIdentity, spec: ProxySpec): Promise<{head_sha: string; files: string[]}>;
  runTests(identity: RepairIdentity, spec: ProxySpec): Promise<boolean>;
  runReview(identity: RepairIdentity, spec: ProxySpec, head_sha: string): Promise<boolean>;
  runPolicy(identity: RepairIdentity, spec: ProxySpec, review_passed: boolean): Promise<boolean>;
  runMerge(identity: RepairIdentity, spec: ProxySpec, head_sha: string): Promise<string | undefined>;
  runInstall(identity: RepairIdentity, spec: ProxySpec, merge: string): Promise<boolean>;
  closeRepair(identity: RepairIdentity, incident: IncidentRecord): void;
  resumeOriginalFront(front_id: string): void;
}

export function incidentFingerprint(incident: IncidentRecord, lifecycle: LifecycleRecord): RepairFingerprint {
  const canonical = JSON.stringify({
    incident_id: incident.incident_id,
    front_id: lifecycle.front_id,
    failure_class: incident.class,
    base_sha: lifecycle.base_sha,
    repair_cycle: lifecycle.repair_cycles,
  });
  return {
    incident_id: incident.incident_id,
    front_id: lifecycle.front_id,
    failure_class: incident.class,
    base_sha: lifecycle.base_sha,
    repair_cycle: lifecycle.repair_cycles,
    fingerprint_sha256: createHash("sha256").update(canonical).digest("hex"),
  };
}

export class SelfRepairOrchestrator {
  private readonly seen = new Set<string>();

  constructor(private readonly effects: RepairOrchestrationEffects) {}

  async orchestrate(
    spec: ProxySpec,
    lifecycle: LifecycleRecord,
    incident: IncidentRecord,
  ): Promise<RepairOrchestrationResult> {
    const fingerprint = incidentFingerprint(incident, lifecycle);
    if (this.seen.has(fingerprint.fingerprint_sha256)) {
      throw new Error("duplicate repair fingerprint: human gate required");
    }
    this.seen.add(fingerprint.fingerprint_sha256);

    this.effects.freezeOriginalFront(lifecycle.front_id);
    const identity = this.effects.createRepairIdentity(spec, incident, fingerprint);
    const build = await this.effects.runBuilder(identity, spec);
    const tests = await this.effects.runTests(identity, spec);
    const review = tests ? await this.effects.runReview(identity, spec, build.head_sha) : false;
    const policy = review ? await this.effects.runPolicy(identity, spec, review) : false;
    const merge = policy ? await this.effects.runMerge(identity, spec, build.head_sha) : undefined;
    const installed = merge ? await this.effects.runInstall(identity, spec, merge) : false;

    this.effects.closeRepair(identity, incident);
    this.effects.resumeOriginalFront(lifecycle.front_id);

    return {
      repair_id: identity.repair_id,
      success: installed,
      head_sha: build.head_sha,
      tests_passed: tests,
      review_passed: review,
      policy_approved: policy,
      merged: merge,
      installed,
      resumed_front_id: lifecycle.front_id,
      incident,
    };
  }
}
