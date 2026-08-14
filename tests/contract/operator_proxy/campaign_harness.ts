import {mkdtempSync, mkdirSync} from "node:fs";
import {tmpdir} from "node:os";
import {join} from "node:path";
import {CampaignSupervisor, type SupervisorOptions} from "../../../scripts/operator_proxy/campaign_supervisor.js";
import type {GitHubBus} from "../../../scripts/operator_proxy/github_bus.js";
import type {ExternalEffectBoundary} from "../../../scripts/operator_proxy/external_effect_guard.js";
import type {LifecycleRecord, ProxySpec} from "../../../scripts/operator_proxy/types.js";

export function makeBus(state: LifecycleRecord): GitHubBus {
  return {
    branchHead: () => state.base_sha ?? "a".repeat(40),
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
  } as unknown as GitHubBus;
}

export function makeBoundary(): ExternalEffectBoundary {
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
  } as unknown as ExternalEffectBoundary;
}

export function lifecycleRecord(overrides: Partial<LifecycleRecord> & {front_id: string; roadmap_item_id: string}): LifecycleRecord {
  return {
    schema_version: 1,
    state: "DISCOVERED",
    base_sha: "a".repeat(40),
    head_sha: "b".repeat(40),
    repair_cycles: 0,
    deployment_mode: "NO_DEPLOY",
    completed_effects: [],
    updated_utc: new Date().toISOString(),
    ...overrides,
  };
}

export class TestCampaignSupervisor extends CampaignSupervisor {
  private tickResult?: LifecycleRecord;
  private tickError?: Error;

  constructor(options: SupervisorOptions = {}) {
    const root = mkdtempSync(join(tmpdir(), "campaign-e2e-"));
    mkdirSync(root, {recursive: true});
    super(root, makeBus(lifecycleRecord({front_id: "BRAIN-101-R3.2-01", roadmap_item_id: "R3.2"})), "opencode_ollama", makeBoundary(), options);
  }

  setTickResult(result: LifecycleRecord): void {
    this.tickResult = result;
    this.tickError = undefined;
  }

  setTickError(error: Error): void {
    this.tickError = error;
    this.tickResult = undefined;
  }

  runTick(): Promise<LifecycleRecord> {
    if (this.tickError) return Promise.reject(this.tickError);
    if (this.tickResult) return Promise.resolve(this.tickResult);
    return Promise.reject(new Error("tick not configured"));
  }

  exposedRoot(): string {
    return (this as any).root;
  }
}
