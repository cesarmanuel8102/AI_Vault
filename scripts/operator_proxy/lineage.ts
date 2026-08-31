import type {LifecycleRecord, ProxySpec, NormalizedDecision} from "./types.js";
import {LEGACY_NEUTRALIZATION_TRAILER,LEGACY_REBUILD_TRAILER,PRIOR_UNATTESTED_HEAD_TRAILER,RESET_BASE_TRAILER,NEUTRALIZATION_HEAD_TRAILER,FRESH_BUILDER_HEAD_TRAILER} from "./builder_attempt_provenance.js";

// ---------------------------------------------------------------------------
// Control plane identity
//
// The recovery plane runs self-hosted: its own source lives on the branch it
// governs. Persisted lifecycle state can therefore have been written by an
// earlier control plane. Every snapshot records both the writer version of the
// persisted record and the version of the running plane so reconciliation can
// treat an upgrade as an explicit modeled transition.
// ---------------------------------------------------------------------------
export const CONTROL_PLANE_VERSION = 2;
export const LEGACY_STATE_WRITER_VERSION = 1;
const writerVersion = (value: unknown): number =>
  typeof value === "number" && Number.isInteger(value) && value >= 1 && value <= CONTROL_PLANE_VERSION ? value : LEGACY_STATE_WRITER_VERSION;

// ---------------------------------------------------------------------------
// Shared fact extraction
//
// The pre-consolidation code encoded domain facts positionally inside session
// strings (`builder-recovered:<sha>`, `agent-loop-builder-<sha>`,
// `reviewer:builder-provenance-recovery:<sha>`) and re-derived the same
// identity checks in production_effects.ts, lifecycle_store.ts and
// external_effect_guard.ts. These helpers extract each fact exactly once.
// ---------------------------------------------------------------------------
export const SHA40 = /^[0-9a-f]{40}$/;
export function recoveredBuilderSessionHead(session: string | undefined): string | undefined {
  return session?.startsWith("builder-recovered:") ? session.slice("builder-recovered:".length) : undefined;
}
export function agentLoopBuilderSessionHead(session: string | undefined): string | undefined {
  return session?.startsWith("agent-loop-builder-") ? session.slice("agent-loop-builder-".length) : undefined;
}
export function deterministicBuilderProvenanceRepairSessionHead(session: string | undefined): string | undefined {
  return session?.startsWith("reviewer:builder-provenance-recovery:") ? session.slice("reviewer:builder-provenance-recovery:".length) : undefined;
}
export function deterministicCiRepairerSessionHead(session: string | undefined): string | undefined {
  return session?.startsWith("reviewer:deterministic-ci:") ? session.slice("reviewer:deterministic-ci:".length) : undefined;
}
export function builderFailureClass(lastError: string | undefined): string | undefined {
  return /^BUILDER_FAILED:[A-Z_]+$/.test(lastError ?? "") ? lastError!.slice("BUILDER_FAILED:".length) : undefined;
}

// The synchronization lineage is a typed chain decoded from the positional
// completed_effects encoding. Legacy records keep their bytes; decisions read
// this structure instead of re-deriving it per predicate.
export interface EffectChain {
  issueEffect: string;
  buildHead: string;
  syncHeads: string[];
  mergeCommit?: string;
}
export function decodeEffectChain(record: Pick<LifecycleRecord, "completed_effects" | "issue" | "head_sha">): EffectChain | undefined {
  const effects = record.completed_effects;
  if (effects.length < 2 || effects[0] !== `issue:${record.issue}`) return undefined;
  const build = /^build:([0-9a-f]{40})$/.exec(effects[1] ?? "");
  if (!build) return undefined;
  const syncs: string[] = [];
  let merge: string | undefined;
  for (let index = 2; index < effects.length; index++) {
    const effect = effects[index]!;
    const sync = /^base-sync:([0-9a-f]{40})$/.exec(effect);
    if (sync) {syncs.push(sync[1]!); continue;}
    const merged = /^merge:([0-9a-f]{40})$/.exec(effect);
    if (merged && index === effects.length - 1) {merge = merged[1]; continue;}
    return undefined;
  }
  if (new Set(effects).size !== effects.length) return undefined;
  return {issueEffect: effects[0]!, buildHead: build[1]!, syncHeads: syncs, mergeCommit: merge};
}

// Named semantic predicates shared by the planner and the effect appliers.
// These are domain roles, not incident shapes.
export const blockedCiEffectChain = (record: Pick<LifecycleRecord, "completed_effects" | "issue" | "head_sha">): boolean => {
  const chain = decodeEffectChain(record);
  if (!chain || chain.mergeCommit !== undefined) return false;
  if (chain.syncHeads.length === 0) return chain.buildHead === record.head_sha;
  return chain.syncHeads.at(-1) === record.head_sha;
};
export const expandableBlockedCiEffectChain = (record: Pick<LifecycleRecord, "completed_effects" | "issue" | "head_sha">): boolean => {
  const chain = decodeEffectChain(record);
  return !!chain && chain.mergeCommit === undefined && chain.syncHeads.at(-1) === record.head_sha && chain.syncHeads.length <= 62;
};
export const privilegedInstallEffectChain = (record: Pick<LifecycleRecord, "completed_effects" | "issue" | "head_sha">): boolean => {
  const chain = decodeEffectChain(record);
  return !!chain && chain.mergeCommit === record.head_sha && chain.syncHeads.length <= 9;
};
export const validBridgeAdoptionFacts = (record: LifecycleRecord): boolean =>
  ["CI_PENDING", "REVIEWING"].includes(record.state) && record.repair_cycles === 0 && !!record.issue && !!record.pr &&
  !record.reviewer_session && !record.decision_id && SHA40.test(record.head_sha ?? "") &&
  record.builder_session !== undefined && (decodeEffectChain(record)?.syncHeads.length ?? 0) === 0 && blockedCiEffectChain(record);

// ---------------------------------------------------------------------------
// CanonicalLifecycleSnapshot
//
// normalizeObservedFacts(): read-only evidence from the persisted record, the
// immutable decision ledger and GitHub is gathered once. Every downstream
// decision reads the snapshot; nothing re-queries or re-interprets the raw
// sources. Contradictory evidence normalizes to an INVALID_* classification
// instead of being guessed into a mutation.
// ---------------------------------------------------------------------------
export interface PrIdentity {
  number?: number;
  author?: {login?: string};
  baseRefName?: string;
  baseRefOid?: string;
  headRefName?: string;
  headRefOid?: string;
  headRepository?: {nameWithOwner?: string};
  isCrossRepository?: boolean;
  isDraft?: boolean;
  state?: string;
  mergeable?: string;
  files?: {path: string}[];
}
export interface SnapshotBus {
  prIdentity(pr: number): PrIdentity;
  remoteBranchHead(branch: string): string | undefined;
  issueSnapshot(issue: number): {state: string; body: string; labels: string[]};
  prCandidatesByBranch(branch: string): PrIdentity[];
  isAncestor(older: string, newer: string): boolean;
  commitMessage(sha: string): string;
  call(args: string[]): string;
}
export interface ObservedIssue {state: string; body: string; labels: string[]}
export interface ObservedPr {
  number: number;
  head: string;
  base: string;
  identity: PrIdentity;
  trustedAuthor: boolean;
  pathsInScope: boolean;
}
export interface CanonicalLifecycleSnapshot {
  spec: ProxySpec;
  record: LifecycleRecord;
  controlPlane: {writerVersion: number; runtimeVersion: number};
  base: {persisted: string; authorized: string; advanced: boolean; stale: boolean};
  effectChain: EffectChain | undefined;
  builder: {
    session: string | undefined;
    recoveredHead: string | undefined;
    receiptHead: string | undefined;
    receiptBase: string | undefined;
    retryPending: boolean;
  };
  decision: {id: string | undefined; loaded: NormalizedDecision | undefined; missing: boolean};
  /** Lazy read-only observations: each is gathered at most once, only when used. */
  observeIssue(): ObservedIssue | undefined;
  observePr(): ObservedPr | undefined;
  observeRemoteHead(): string | undefined;
  observePublishedCandidates(): ObservedPr[];
  facts: {
    builderFailure: string | undefined;
    ciBlocked: boolean;
    ownerEscalated: boolean;
    privilegedInstall: boolean;
    negatedRiskDecision: boolean;
    recordedRetry: boolean;
    synchronizedCandidate: boolean;
  };
  classification: {invalid?: string};
}

export const pathAllowed = (path: string, spec: Pick<ProxySpec, "allowed_paths" | "forbidden_paths">): boolean =>
  spec.allowed_paths.some(rule => rule.endsWith("/") ? path.startsWith(rule) : path === rule) &&
  !spec.forbidden_paths.some(rule => path === rule || path.startsWith(rule.endsWith("/") ? rule : `${rule}/`));

function trustedPrIdentity(identity: PrIdentity, spec: ProxySpec, head: string): boolean {
  return identity.author?.login === spec.repository.split("/", 1)[0] &&
    identity.baseRefName === "codex/own-capital-sustainable-return" &&
    identity.headRefName === spec.work_branch &&
    identity.headRepository?.nameWithOwner === spec.repository &&
    identity.isCrossRepository === false &&
    identity.isDraft === true &&
    identity.state === "OPEN" &&
    identity.headRefOid === head;
}
function observedPr(bus: SnapshotBus, spec: ProxySpec, number: number, head: string): ObservedPr {
  const identity = bus.prIdentity(number);
  const files = (identity.files ?? []).map(entry => String(entry.path));
  return {
    number,
    head,
    base: String(identity.baseRefOid ?? ""),
    identity,
    trustedAuthor: trustedPrIdentity(identity, spec, head),
    pathsInScope: files.length > 0 && files.every(path => pathAllowed(path, spec)),
  };
}

export interface SnapshotDeps {
  bus: SnapshotBus;
  loadDecision(id: string): NormalizedDecision | undefined;
}

export function normalizeObservedFacts(spec: ProxySpec, record: LifecycleRecord, deps: SnapshotDeps): CanonicalLifecycleSnapshot {
  const {bus} = deps;
  const decisionId = record.decision_id;
  const decision = decisionId ? deps.loadDecision(decisionId) : undefined;
  const receiptHeads = [record.builder_receipt_head_sha, record.builder_receipt_base_sha];
  if (receiptHeads.some(value => value !== undefined) && !receiptHeads.every(value => typeof value === "string" && SHA40.test(value))) {
    return invalid(spec, record, "BUILDER_RECEIPT_ANCHOR_INVALID");
  }
  const builderFailure = builderFailureClass(record.last_error);
  const failure = record.state === "BLOCKED" && builderFailure !== undefined;
  return {
    spec,
    record,
    controlPlane: {writerVersion: writerVersion(record.state_writer_control_plane_version), runtimeVersion: CONTROL_PLANE_VERSION},
    base: {
      persisted: record.base_sha,
      authorized: spec.expected_base_sha,
      advanced: record.base_sha !== spec.expected_base_sha && bus.isAncestor(record.base_sha, spec.expected_base_sha),
      stale: record.base_sha !== spec.expected_base_sha,
    },
    effectChain: decodeEffectChain(record),
    builder: {
      session: record.builder_session,
      recoveredHead: recoveredBuilderSessionHead(record.builder_session),
      receiptHead: record.builder_receipt_head_sha,
      receiptBase: record.builder_receipt_base_sha,
      retryPending: record.builder_retry_reason === "BUILDER_FAILURE",
    },
    decision: {id: decisionId, loaded: decision, missing: decisionId !== undefined && decision === undefined},
    ...lazyObservations(bus, spec, record),
    facts: {
      builderFailure,
      ciBlocked: record.state === "BLOCKED" && record.last_error === "CI_FAILED",
      ownerEscalated: record.state === "ESCALATED" && record.last_error === "OWNER_AUTHORITY_REQUIRED",
      privilegedInstall: record.state === "ESCALATED" && record.last_error === "LOCAL_PRIVILEGE_REQUIRED",
      negatedRiskDecision: decision !== undefined && decision.risk === "CRITICAL" && decision.deterministic_gate === "PASS" &&
        decision.policy_decision === "ESCALATE_TO_OWNER" && decision.allowed_action === "NONE" && classifyRisk(spec) !== "CRITICAL" && classifyRisk(spec) !== "HIGH",
      recordedRetry: record.builder_retry_reason === "BUILDER_FAILURE" && record.repair_cycles > 0 && record.repair_cycles <= 2,
      synchronizedCandidate: blockedCiEffectChain(record) && ((decodeEffectChain(record)?.syncHeads.length ?? 0) > 0 || (record.builder_receipt_head_sha !== undefined && record.builder_receipt_base_sha !== undefined)),
    },
    classification: {},
  };
}
function lazyObservations(bus: SnapshotBus, spec: ProxySpec, record: LifecycleRecord): Pick<CanonicalLifecycleSnapshot, "observeIssue" | "observePr" | "observeRemoteHead" | "observePublishedCandidates"> {
  let issue: ObservedIssue | undefined;
  let issueRead = false;
  let pr: ObservedPr | undefined;
  let prRead = false;
  let remoteHead: string | undefined;
  let remoteRead = false;
  let candidates: ObservedPr[] | undefined;
  return {
    observeIssue: () => {
      if (!issueRead) {issueRead = true; issue = record.issue ? bus.issueSnapshot(record.issue) : undefined;}
      return issue;
    },
    observePr: () => {
      if (!prRead) {prRead = true; pr = record.pr && record.head_sha ? observedPr(bus, spec, record.pr, record.head_sha) : undefined;}
      return pr;
    },
    observeRemoteHead: () => {
      if (!remoteRead) {remoteRead = true; remoteHead = spec.work_branch ? bus.remoteBranchHead(spec.work_branch) : undefined;}
      return remoteHead;
    },
    observePublishedCandidates: () => {
      if (!candidates) {
        candidates = [];
        if (spec.work_branch) for (const candidate of bus.prCandidatesByBranch(spec.work_branch)) {
          const number = Number(candidate?.number), head = String(candidate?.headRefOid ?? "");
          if (!Number.isInteger(number) || number <= 0 || !SHA40.test(head)) continue;
          const files = (candidate?.files ?? []).map((entry: any) => String(entry.path));
          candidates.push({
            number, head,
            base: String(candidate?.baseRefOid ?? ""),
            identity: candidate,
            trustedAuthor: trustedPrIdentity(candidate, spec, head),
            pathsInScope: files.length > 0 && files.every(path => pathAllowed(path, spec)),
          });
        }
      }
      return candidates;
    },
  };
}
function invalid(spec: ProxySpec, record: LifecycleRecord, reason: string): CanonicalLifecycleSnapshot {
  return {
    spec, record,
    controlPlane: {writerVersion: writerVersion(record.state_writer_control_plane_version), runtimeVersion: CONTROL_PLANE_VERSION},
    base: {persisted: record.base_sha, authorized: spec.expected_base_sha, advanced: false, stale: record.base_sha !== spec.expected_base_sha},
    effectChain: undefined,
    builder: {session: record.builder_session, recoveredHead: recoveredBuilderSessionHead(record.builder_session), receiptHead: record.builder_receipt_head_sha, receiptBase: record.builder_receipt_base_sha, retryPending: record.builder_retry_reason === "BUILDER_FAILURE"},
    decision: {id: record.decision_id, loaded: undefined, missing: record.decision_id !== undefined},
    ...lazyObservations({issueSnapshot: () => undefined, prIdentity: () => ({}), prCandidatesByBranch: () => [], remoteBranchHead: () => undefined, isAncestor: () => false, commitMessage: () => "", call: () => ""} as unknown as SnapshotBus, spec, record),
    facts: {builderFailure: builderFailureClass(record.last_error), ciBlocked: false, ownerEscalated: false, privilegedInstall: false, negatedRiskDecision: false, recordedRetry: false, synchronizedCandidate: false},
    classification: {invalid: reason},
  };
}
function classifyRisk(spec: ProxySpec): string {
  return spec.risk;
}

// ---------------------------------------------------------------------------
// CandidateLineage
//
// The first-class lineage object required by reconciliation. All SHAs that are
// domain facts are explicit fields; none survive only inside session strings.
// ---------------------------------------------------------------------------
export interface CandidateLineage {
  roadmapItemId: string;
  issue: number;
  pr: number;
  authorizedBaseSha: string;
  persistedBaseSha: string;
  builderOriginHeadSha: string;
  builderReceiptHeadSha: string;
  builderReceiptBaseSha: string;
  decisionId: string;
  decisionBaseSha: string;
  decisionHeadSha: string;
  synchronizationHeads: string[];
  currentCandidateHeadSha: string;
  mergeCommitSha: string | undefined;
}
export function deriveCandidateLineage(snapshot: CanonicalLifecycleSnapshot, decision: NormalizedDecision): CandidateLineage | undefined {
  const chain = snapshot.effectChain;
  const record = snapshot.record;
  if (!chain || !record.issue || !record.pr || !record.head_sha) return undefined;
  return {
    roadmapItemId: record.roadmap_item_id,
    issue: record.issue,
    pr: record.pr,
    authorizedBaseSha: snapshot.spec.expected_base_sha,
    persistedBaseSha: record.base_sha,
    builderOriginHeadSha: chain.buildHead,
    builderReceiptHeadSha: snapshot.builder.receiptHead ?? chain.buildHead,
    builderReceiptBaseSha: snapshot.builder.receiptBase ?? decision.base_sha,
    decisionId: decision.decision_id,
    decisionBaseSha: decision.base_sha,
    decisionHeadSha: decision.head_sha,
    synchronizationHeads: chain.syncHeads,
    currentCandidateHeadSha: record.head_sha,
    mergeCommitSha: chain.mergeCommit,
  };
}

// A decision participates in the lineage by semantic role: it is a governed
// repair decision bound to this front whose head is the provenance root of the
// current candidate and whose base is an ancestor of the persisted base. The
// exact historical enum combination observed in one incident is never a gate.
export function decisionBoundToLineage(decision: NormalizedDecision, spec: ProxySpec, record: LifecycleRecord, bus: SnapshotBus): boolean {
  if (decision.authorization_id !== spec.authorization_id || decision.repository !== spec.repository) return false;
  if (decision.issue !== record.issue || decision.pr !== record.pr) return false;
  if (decision.roadmap_id !== spec.roadmap_id || decision.roadmap_item_id !== spec.roadmap_item_id) return false;
  if (decision.policy_decision !== "REPAIR" || decision.allowed_action !== "REQUEST_REPAIR") return false;
  if (!SHA40.test(decision.head_sha) || !SHA40.test(decision.base_sha)) return false;
  if (!record.head_sha) return false;
  const headRecorded = record.completed_effects.includes(`build:${decision.head_sha}`) || record.completed_effects.includes(`base-sync:${decision.head_sha}`);
  const headBound = decision.head_sha === record.head_sha || headRecorded && bus.isAncestor(decision.head_sha, record.head_sha);
  const baseBound = decision.base_sha === record.base_sha || bus.isAncestor(decision.base_sha, record.base_sha);
  return headBound && baseBound;
}

// ---------------------------------------------------------------------------
// Builder provenance verifier (single implementation)
//
// Consolidates the three duplicated commit-tree/trailer walks that previously
// lived in inspectRouterBuilderReceipt, verifyLegacyRebuild and
// inspectBridgeCandidate. All provenance interpretation happens here, once.
// ---------------------------------------------------------------------------
const ALLOWED_BUILDER_BACKENDS = new Set(["codex_cli_openai", "opencode_github_copilot", "opencode_ollama"]);
const SAFE_MODEL = /^[a-z0-9][a-z0-9._:/-]{2,127}$/;
const SAFE_PROVIDER_SESSION = /^[a-z0-9][a-z0-9._:/-]{2,127}$/;

export interface CommitAccess {
  message(sha: string): string;
  parents(sha: string): string[];
  tree(sha: string): string;
}
export function commitAccessFromBus(bus: {repo: string; commitMessage(sha: string): string; call(args: string[]): string}): CommitAccess {
  return {
    message: sha => bus.commitMessage(sha),
    parents: sha => {
      const commit = JSON.parse(bus.call(["api", `repos/${bus.repo}/git/commits/${sha}`]));
      return Array.isArray(commit?.parents) ? commit.parents.map((parent: any) => String(parent?.sha ?? "")).filter((value: string) => SHA40.test(value)) : [];
    },
    tree: sha => {
      const commit = JSON.parse(bus.call(["api", `repos/${bus.repo}/git/commits/${sha}`]));
      return typeof commit?.tree?.sha === "string" && SHA40.test(commit.tree.sha) ? commit.tree.sha : "";
    },
  };
}
export interface BuilderReceipt {model: string; headCommit: string; status: "VERIFIED" | "PROVENANCE_RECOVERY_REQUIRED"}

const firstLine = (message: string) => message.replace(/\r\n/g, "\n").split("\n", 1)[0];
const trailers = (message: string, prefix: string) => message.replace(/\r\n/g, "\n").split("\n").slice(1).filter(line => line.startsWith(prefix)).map(line => line.slice(prefix.length));

function verifyFreshReceipt(commits: CommitAccess, sha: string, frontId: string): BuilderReceipt | undefined {
  if (firstLine(commits.message(sha)) !== `feat(control-plane): complete ${frontId}`) return undefined;
  const lines = commits.message(sha).replace(/\r\n/g, "\n").split("\n");
  const values = (prefix: string) => lines.slice(1).filter(line => line.startsWith(prefix)).map(line => line.slice(prefix.length));
  const backend = values("BUILDER_BACKEND="), model = values("BUILDER_MODEL="), provider = values("PROVIDER_SESSION="), fallback = values("FALLBACK_REASON=");
  if (backend.length !== 1 || !ALLOWED_BUILDER_BACKENDS.has(backend[0]!) || model.length !== 1 || !SAFE_MODEL.test(model[0]!) ||
    provider.length !== 1 || !SAFE_PROVIDER_SESSION.test(provider[0]!) || fallback.length > 1) return undefined;
  return {model: model[0]!, headCommit: sha, status: "VERIFIED"};
}

// Legacy B/L/N/R/M bridge: a neutralization commit N (tree == base) joined
// with a fresh attested rebuild R through a bridge M (tree == R).
function verifyLegacyRebuild(commits: CommitAccess, sha: string, baseSha: string, frontId: string, isAncestor: (older: string, newer: string) => boolean): BuilderReceipt | undefined {
  const message = commits.message(sha);
  if (firstLine(message) !== `feat(control-plane): complete ${frontId}`) return undefined;
  const legacy = trailers(message, `${LEGACY_REBUILD_TRAILER}=`);
  if (legacy.length !== 1 || legacy[0] !== "true") return undefined;
  const parents = commits.parents(sha);
  if (parents.length !== 2) return undefined;
  const [n, r] = parents;
  const nMessage = commits.message(n!), rMessage = commits.message(r!);
  const nNeutral = trailers(nMessage, `${LEGACY_NEUTRALIZATION_TRAILER}=`);
  if (nNeutral.length !== 1 || nNeutral[0] !== "true" || firstLine(nMessage) !== `chore(control-plane): neutralize ${frontId} legacy baseline`) return undefined;
  const priorHead = trailers(nMessage, `${PRIOR_UNATTESTED_HEAD_TRAILER}=`)[0];
  const resetBase = trailers(nMessage, `${RESET_BASE_TRAILER}=`)[0];
  const bridgeN = trailers(message, `${NEUTRALIZATION_HEAD_TRAILER}=`)[0];
  const bridgeR = trailers(message, `${FRESH_BUILDER_HEAD_TRAILER}=`)[0];
  if (!priorHead || !resetBase || !bridgeN || !bridgeR || bridgeN !== n || bridgeR !== r) return undefined;
  if (resetBase !== baseSha) return undefined;
  if (!isAncestor(baseSha, priorHead) || !isAncestor(baseSha, r!)) return undefined;
  if (commits.tree(n!) !== commits.tree(baseSha)) return undefined;
  if (commits.tree(sha) !== commits.tree(r!)) return undefined;
  return verifyFreshReceipt(commits, r!, frontId);
}

export function verifyBuilderProvenance(commits: CommitAccess, head: string, baseSha: string, frontId: string, isAncestor: (older: string, newer: string) => boolean, maxDepth = 64): BuilderReceipt {
  if (!SHA40.test(head) || !SHA40.test(baseSha) || !/^[A-Z0-9][A-Z0-9._-]{5,127}$/.test(frontId)) throw new Error("builder model receipt history invalid");
  let current = head, depth = 0;
  let candidate: BuilderReceipt | undefined;
  while (current !== baseSha && !isAncestor(current, baseSha) && depth++ < maxDepth) {
    const legacy = verifyLegacyRebuild(commits, current, baseSha, frontId, isAncestor);
    if (legacy) return legacy;
    const message = commits.message(current);
    if (firstLine(message) === `chore(control-plane): synchronize ${frontId} base`) {
      const parents = commits.parents(current);
      if (parents.length !== 2 || !isAncestor(baseSha, parents[1]!)) return {model: "", headCommit: "", status: "PROVENANCE_RECOVERY_REQUIRED"};
      current = parents[0]!;
      continue;
    }
    const fresh = verifyFreshReceipt(commits, current, frontId);
    if (!fresh) return {model: "", headCommit: "", status: "PROVENANCE_RECOVERY_REQUIRED"};
    if (!candidate) candidate = fresh;
    const parents = commits.parents(current);
    if (parents.length === 0) return {model: "", headCommit: "", status: "PROVENANCE_RECOVERY_REQUIRED"};
    current = parents[0]!;
  }
  if (candidate && (current === baseSha || isAncestor(current, baseSha))) return candidate;
  return {model: "", headCommit: "", status: "PROVENANCE_RECOVERY_REQUIRED"};
}