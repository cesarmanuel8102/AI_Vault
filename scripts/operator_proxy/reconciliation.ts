import type {LifecycleRecord, ProxySpec, NormalizedDecision, OwnerAuthorizedPayloadRepairGrant} from "./types.js";
import type {OwnerGrantReceiptEvent} from "./owner_repair_receipt_ledger.js";
const pathAllowed=(path:string,spec:ProxySpec)=>spec.allowed_paths.some(p=>p.endsWith("/")?path.startsWith(p):path===p)&&!spec.forbidden_paths.some(p=>path===p||path.startsWith(p.endsWith("/")?p:`${p}/`));
import {
  type CanonicalLifecycleSnapshot, type CandidateLineage,
  blockedCiEffectChain, expandableBlockedCiEffectChain, privilegedInstallEffectChain,
  validBridgeAdoptionFacts, decisionBoundToLineage, deriveCandidateLineage,
  deterministicCiRepairerSessionHead, deterministicBuilderProvenanceRepairSessionHead,
  recoveredBuilderSessionHead, agentLoopBuilderSessionHead, SHA40,
} from "./lineage.js";

// ---------------------------------------------------------------------------
// Reconciliation domain moves
//
// A small finite set of domain moves replaces the accumulated incident-shaped
// recovery dispatchers. Move names describe domain semantics; historical
// incident identifiers never appear here.
// ---------------------------------------------------------------------------
export type ReconciliationMove =
  | "NOOP"
  | "REBIND_UNSTARTED_BASE"
  | "REBIND_PRE_BUILD_BASE"
  | "REBIND_POST_MERGE_BASE"
  | "RESUME_INITIAL_BUILD"
  | "RESUME_RECORDED_BUILD"
  | "ADOPT_PUBLISHED_INITIAL_CANDIDATE"
  | "ADOPT_PUBLISHED_REPAIR_CANDIDATE"
  | "ADOPT_VERIFIED_SYNCHRONIZED_CANDIDATE"
  | "ADOPT_ADVANCED_PAYLOAD"
  | "REVERT_INVALIDATED_ADOPTION"
  | "SYNCHRONIZE_CANDIDATE"
  | "REOPEN_CI"
  | "REQUEST_DETERMINISTIC_REPAIR"
  | "RESUME_UNCONSUMMATED_REPAIR"
  | "AUTHORIZE_OWNER_PAYLOAD_REPAIR_RESUME"
  | "EXHAUST_REPAIR"
  | "ADOPT_EXTERNAL_MERGE"
  | "RECOVER_NEGATED_RISK_ESCALATION"
  | "INVALIDATE_FAILED_MERGE"
  | "ESCALATE_OWNER"
  | "AMBIGUOUS";

export interface ReconciliationPlan {
  move: ReconciliationMove;
  reason: string;
  /** Immutable lineage the planner verified for candidate-affecting moves. */
  lineage: CandidateLineage | undefined;
}

export interface PlannerPorts {
  /** Verifies a synchronized candidate produces green terminal CI at its exact head. */
  checksGreenAtHead(head: string): boolean;
  /** Verifies the canonical branch tip is the authorized base. */
  authorizedBaseIsCanonicalTip(): boolean;
  /** Reads a recorded adoption event for the exact front/issue/pr/head. */
  recordedAdoptionEvent(record: LifecycleRecord): any;
  /** Loads the decision recorded before an adoption (provenance root of a synchronized candidate). */
  loadDecision(id: string): NormalizedDecision | undefined;
  /** Verifies builder provenance of receiptHead/receiptBase. */
  verifyReceipt(receiptHead: string, receiptBase: string): boolean;
  /** Verifies a fully attested neutralization bridge candidate against the authorized base. */
  verifyBridgeCandidate(nextBase: string, nextHead: string): boolean;
  /** Verifies the persisted repair decision authorized the current synchronized chain. */
  decisionBoundToLineage(decision: NormalizedDecision): boolean;
  /** Counts CONSUMMATED payload-review repairs (a repair decision followed by a replaced payload head). Lifecycle/system recovery churn never counts. */
  consummatedPayloadRepairs(issue: number, pr: number): number;
  /** Returns only a grant already verified against canonical authority and Owner evidence. */
  verifiedOwnerPayloadRepairGrant?(record: LifecycleRecord): OwnerAuthorizedPayloadRepairGrant | undefined;
  /** Returns only the validated append-only receipt view for the grant key. */
  ownerPayloadRepairReceipt?(grantKey: string): OwnerGrantReceiptEvent | undefined;
}

// ---------------------------------------------------------------------------
// Invariant set
//
// validateInvariantSet() is the single safety gate a plan must pass before any
// applier may mutate. Each invariant is a domain statement, not an incident.
// ---------------------------------------------------------------------------
export interface InvariantResult {violations: string[]}
export function validateInvariantSet(snapshot: CanonicalLifecycleSnapshot, plan: ReconciliationPlan, ports: PlannerPorts): InvariantResult {
  const violations: string[] = [];
  const record = snapshot.record;
  if (snapshot.classification.invalid) violations.push(snapshot.classification.invalid);
  if (snapshot.spec.front_id !== undefined && record.front_id !== snapshot.spec.front_id) violations.push("FRONT_BINDING_MISMATCH");
  if (snapshot.spec.roadmap_item_id !== undefined && record.roadmap_item_id !== snapshot.spec.roadmap_item_id) violations.push("FRONT_BINDING_MISMATCH");
  if (plan.move === "NOOP") return {violations};
  if (record.state === "BLOCKED" || record.state === "ESCALATED") {
    if (!plan.lineage && !planRequiresNoLineage(plan.move)) violations.push("CANDIDATE_AFFECTING_MOVE_WITHOUT_LINEAGE");
    if (plan.lineage && !lineageComplete(plan.lineage, ports)) violations.push("LINEAGE_UNPROVABLE");
  }
  // SAFETY: ambiguous or unauthorized identity never admits mutation.
  if (plan.move !== "ESCALATE_OWNER" && plan.move !== "EXHAUST_REPAIR") {
    if (snapshot.base.stale && !snapshot.base.advanced) violations.push("BASE_NOT_ANCESTRAL");
    if (plan.lineage && plan.lineage.authorizedBaseSha !== snapshot.spec.expected_base_sha) violations.push("AUTHORIZED_BASE_MISMATCH");
  }
  // BOUNDEDNESS: no recovery move may exceed the persisted repair budget.
  if (plan.move === "RESUME_INITIAL_BUILD" && record.repair_cycles !== 0) violations.push("INITIAL_RETRY_ALREADY_CONSUMED");
  if (plan.move === "REQUEST_DETERMINISTIC_REPAIR" && record.repair_cycles >= 2) violations.push("REPAIR_LIMIT_REACHED");
  if (plan.move === "RESUME_UNCONSUMMATED_REPAIR" && (!record.issue || !record.pr || ports.consummatedPayloadRepairs(record.issue, record.pr) >= 2)) violations.push("PAYLOAD_REPAIR_BUDGET_EXHAUSTED");
  return {violations};
}
const planRequiresNoLineage = (move: ReconciliationMove): boolean =>
  ["NOOP", "REBIND_UNSTARTED_BASE", "REBIND_PRE_BUILD_BASE", "REBIND_POST_MERGE_BASE", "RESUME_INITIAL_BUILD",
   "EXHAUST_REPAIR", "ESCALATE_OWNER", "INVALIDATE_FAILED_MERGE", "AMBIGUOUS", "RECOVER_NEGATED_RISK_ESCALATION",
   "SYNCHRONIZE_CANDIDATE", "REOPEN_CI", "ADOPT_ADVANCED_PAYLOAD", "AUTHORIZE_OWNER_PAYLOAD_REPAIR_RESUME"].includes(move) ||
  // Moves whose lineage is derived lazily by the applier after external reads.
  (move === "REQUEST_DETERMINISTIC_REPAIR" || move === "RESUME_RECORDED_BUILD" || move === "RESUME_UNCONSUMMATED_REPAIR");
function lineageComplete(lineage: CandidateLineage, ports: PlannerPorts): boolean {
  if (!SHA40.test(lineage.builderReceiptHeadSha) || !SHA40.test(lineage.builderReceiptBaseSha)) return false;
  if (!ports.verifyReceipt(lineage.builderReceiptHeadSha, lineage.builderReceiptBaseSha)) return false;
  return true;
}

// ---------------------------------------------------------------------------
// deriveReconciliationPlan
//
// Deterministic: the same normalized snapshot and the same external facts
// always produce the same plan. The planner orders candidate-preserving moves
// before base synchronization so a legitimate state is never invalidated
// merely because the canonical base advanced.
// ---------------------------------------------------------------------------
export function deriveReconciliationPlan(snapshot: CanonicalLifecycleSnapshot, ports: PlannerPorts): ReconciliationPlan {
  const record = snapshot.record;
  if (snapshot.classification.invalid) return {move: "AMBIGUOUS", reason: snapshot.classification.invalid, lineage: undefined};
  // Blocked and escalated states always need a recovery plan, even when the
  // persisted base already matches: the lifecycle itself is stopped.
  const blockedOrEscalated = record.state === "BLOCKED" || record.state === "ESCALATED";
  // An undecided post-build record whose same-PR payload advanced is itself
  // stopped at a stale head: it plans even at the matching base.
  const payloadAdvanced = !blockedOrEscalated && ["CI_PENDING", "REVIEWING"].includes(record.state) &&
    !record.reviewer_session && !record.decision_id && samePrPayloadAdvanced(snapshot);
  if (!snapshot.base.stale && !blockedOrEscalated && !payloadAdvanced) return {move: "NOOP", reason: "persisted base matches authorized base", lineage: undefined};

  if (snapshot.facts.privilegedInstall && privilegedInstallEffectChain(record)) return {move: "NOOP", reason: "privileged install waits at its own escalation path", lineage: undefined};
  if (snapshot.facts.ownerEscalated && snapshot.facts.negatedRiskDecision) return recoverNegatedRisk(snapshot, ports);
  if (snapshot.facts.builderFailure !== undefined && record.repair_cycles > 0 && record.pr !== undefined && record.head_sha !== undefined) {
    const merged = safe(() => snapshot.observePr()?.identity.state === "MERGED");
    if (merged) return adoptExternalMerge(snapshot, ports);
  }

  if (snapshot.facts.builderFailure !== undefined) return planBuilderFailure(snapshot, ports);
  if (snapshot.facts.ciBlocked) return planBlockedCi(snapshot, ports);
  if (snapshot.facts.policyBlocked) return planPolicyBlocked(snapshot, ports);
  if (record.state === "BUILDING") return planBuilding(snapshot, ports);
  if (["MERGING"].includes(record.state)) return {move: "INVALIDATE_FAILED_MERGE", reason: "merge dispatch failed under an advanced base", lineage: undefined};
  if (["DISCOVERED", "ADMITTED"].includes(record.state)) return {move: "REBIND_UNSTARTED_BASE", reason: "effect-free admission rebases to the authorized base", lineage: undefined};
  if (postMergeStates.includes(record.state)) return {move: "REBIND_POST_MERGE_BASE", reason: "post-merge closeout records the canonical advance", lineage: undefined};
  if (["CI_PENDING", "REVIEWING"].includes(record.state)) return planDecidedPostBuild(snapshot, ports);
  if (snapshot.facts.ownerEscalated) return {move: "ESCALATE_OWNER", reason: "persisted owner escalation", lineage: undefined};
  return {move: "AMBIGUOUS", reason: `no domain move for state ${record.state}`, lineage: undefined};
}

const postMergeStates = ["MERGED", "INSTALL_PENDING", "INSTALLING", "RUNTIME_PILOT_PENDING", "RUNTIME_PILOT_RUNNING", "RUNTIME_VERIFIED", "CLOSEOUT_PENDING", "CLOSEOUT_MERGED", "TERMINAL_COMPLETED"];

function planBuilderFailure(snapshot: CanonicalLifecycleSnapshot, ports: PlannerPorts): ReconciliationPlan {
  const record = snapshot.record;
  // An initial builder failure with no candidate consumes one bounded re-run.
  // The move applies at the matching base and across a verified advanced base.
  if (record.repair_cycles === 0) {
    if (snapshot.base.stale && !snapshot.base.advanced) return {move: "AMBIGUOUS", reason: "initial builder failure base is not ancestral", lineage: undefined};
    return {move: "RESUME_INITIAL_BUILD", reason: "one bounded builder re-run after the initial failure", lineage: undefined};
  }
  const retryConsumable = record.repair_cycles > 0 && record.repair_cycles <= 2 && (record.builder_retry_reason === undefined || record.builder_retry_reason === "BUILDER_FAILURE");
  if (retryConsumable && record.pr && record.head_sha && snapshot.facts.synchronizedCandidate && record.builder_session && record.reviewer_session && record.decision_id) return adoptVerifiedSynchronized(snapshot, ports);
  if (retryConsumable && record.builder_retry_reason === "BUILDER_FAILURE" && !record.pr && !record.head_sha) return adoptPublishedInitialCandidate(snapshot, ports);
  if (retryConsumable && record.builder_retry_reason === "BUILDER_FAILURE") return {move: "RESUME_RECORDED_BUILD", reason: "recorded builder retry resumes its bounded re-entry", lineage: undefined};
  // At the matching base without a consumable retry reason, the builder
  // failure waits for the governed retry to be recorded; re-entry happens
  // through the normal BUILDING step, not recovery.
  if (!snapshot.base.stale) return {move: "NOOP", reason: "builder failure waits at the matching base", lineage: undefined};
  // A decided repair whose builder failed synchronizes across the advanced
  // base while preserving its immutable decision evidence.
  const decidedRepair = record.repair_cycles > 0 && record.repair_cycles <= 2 && record.pr && record.head_sha &&
    record.builder_session && record.reviewer_session && record.decision_id && !record.builder_retry_reason &&
    snapshot.base.stale;
  if (decidedRepair) {
    if (snapshot.decision.missing) return {move: "AMBIGUOUS", reason: "repair decision missing from the immutable ledger", lineage: undefined};
    if (!snapshot.decision.loaded || !ports.decisionBoundToLineage(snapshot.decision.loaded)) return {move: "AMBIGUOUS", reason: "repair decision not bound to the candidate lineage", lineage: undefined};
    if (!blockedCiEffectChain(record)) return {move: "AMBIGUOUS", reason: "builder failure effect chain invalid", lineage: undefined};
    return {move: "SYNCHRONIZE_CANDIDATE", reason: "decided repair synchronizes across the advanced base after a builder failure", lineage: undefined};
  }
  return {move: "AMBIGUOUS", reason: "builder failure without a consumable retry", lineage: undefined};
}

function planBlockedCi(snapshot: CanonicalLifecycleSnapshot, ports: PlannerPorts): ReconciliationPlan {
  const record = snapshot.record;
  if (snapshot.base.stale && !snapshot.base.advanced) return {move: "AMBIGUOUS", reason: "blocked CI base is not ancestral", lineage: undefined};
  if (!blockedCiEffectChain(record)) return {move: "AMBIGUOUS", reason: "blocked CI effect chain invalid", lineage: undefined};
  if (!record.pr || !record.head_sha || !record.builder_session) return {move: "AMBIGUOUS", reason: "blocked CI candidate evidence missing", lineage: undefined};
  // Green exact-head CI at the persisted base reopens the pipeline without any rebuild.
  if (snapshot.base.persisted === snapshot.spec.expected_base_sha && ports.checksGreenAtHead(record.head_sha) && remoteMatchesSnapshot(snapshot)) {
    return {move: "REOPEN_CI", reason: "green exact-head CI reopens the undecided candidate", lineage: undefined};
  }
  if (record.repair_cycles >= 2) {
    if (eligibleOwnerPayloadRepair(snapshot, ports)) return {move: "AUTHORIZE_OWNER_PAYLOAD_REPAIR_RESUME", reason: "verified consumed Owner grant authorizes the one exceptional build", lineage: undefined};
    return {move: "EXHAUST_REPAIR", reason: "bounded repair budget exhausted", lineage: undefined};
  }
  if (snapshot.base.stale) return {move: "SYNCHRONIZE_CANDIDATE", reason: "terminal failed CI synchronizes the trusted candidate across the advanced base", lineage: undefined};
  return {move: "REQUEST_DETERMINISTIC_REPAIR", reason: "terminal failed CI consumes a bounded deterministic repair cycle", lineage: undefined};
}

function eligibleOwnerPayloadRepair(snapshot: CanonicalLifecycleSnapshot, ports: PlannerPorts): boolean {
  const record=snapshot.record,grant=ports.verifiedOwnerPayloadRepairGrant?.(record);
  if(!grant||!record.pr||!record.head_sha||record.base_sha!==snapshot.spec.expected_base_sha||!ownerRepairPrIdentityMatches(snapshot)||grant.authorization_id!==snapshot.spec.authorization_id||grant.repository!==snapshot.spec.repository||grant.roadmap_id!==snapshot.spec.roadmap_id||grant.roadmap_item_id!==snapshot.spec.roadmap_item_id||grant.front_id!==record.front_id||grant.issue!==record.issue||grant.pr!==record.pr||grant.work_branch!==snapshot.spec.work_branch||grant.canonical_base_sha!==snapshot.spec.expected_base_sha||grant.failed_head_sha!==record.head_sha||grant.eligible_failure_class!=="CI_FAILED"||grant.max_extra_builds!==1)return false;
  const receipt=ports.ownerPayloadRepairReceipt?.(grant.grant_key);
  return receipt?.phase==="CONSUMED"&&receipt.grant_key===grant.grant_key&&receipt.front_id===record.front_id&&receipt.failed_head_sha===record.head_sha&&typeof receipt.build_attempt_id==="string"&&/^[0-9a-f]{64}$/.test(receipt.build_attempt_id);
}

function ownerRepairPrIdentityMatches(snapshot: CanonicalLifecycleSnapshot): boolean {
  const {record,spec}=snapshot;
  if(!record.pr||!record.head_sha||!spec.work_branch)return false;
  const remote=safe(()=>snapshot.observeRemoteHead()),pr=safe(()=>snapshot.observePr()),identity=pr?.identity;
  const files=(identity?.files??[]).map((entry:any)=>String(entry.path));
  return remote===record.head_sha&&identity?.headRefOid===record.head_sha&&
    identity.author?.login===spec.repository.split("/",1)[0]&&identity.baseRefName==="codex/own-capital-sustainable-return"&&
    identity.baseRefOid===spec.expected_base_sha&&identity.headRefName===spec.work_branch&&
    identity.headRepository?.nameWithOwner===spec.repository&&identity.isCrossRepository===false&&
    identity.isDraft===true&&identity.state==="OPEN"&&files.length>0&&files.every(path=>pathAllowed(path,spec));
}

// A policy BLOCK is terminal for its decided head. It is resumable only as an
// UNCONSUMMATED payload repair: the recorded review requested changes, a repair
// was authorized, no new payload head was ever consummated, the payload repair
// budget remains, and every identity/admissibility gate still holds. Semantic
// evidence, never lifecycle recovery accounting, is the gate.
function planPolicyBlocked(snapshot: CanonicalLifecycleSnapshot, ports: PlannerPorts): ReconciliationPlan {
  const record = snapshot.record;
  const terminal: ReconciliationPlan = {move: "ESCALATE_OWNER", reason: "policy block is not resumable as an unconsummated repair", lineage: undefined};
  if (snapshot.base.stale && !snapshot.base.advanced) return {move: "AMBIGUOUS", reason: "policy-blocked base is not ancestral", lineage: undefined};
  if (!record.issue || !record.pr || !record.head_sha || !record.builder_session || !record.reviewer_session || !record.decision_id) return terminal;
  if (!blockedCiEffectChain(record)) return {move: "AMBIGUOUS", reason: "policy-blocked effect chain invalid", lineage: undefined};
  const decision = snapshot.decision.loaded;
  if (snapshot.decision.missing || !decision) return {move: "AMBIGUOUS", reason: "policy block decision missing from the immutable ledger", lineage: undefined};
  const findings = "review_findings_count" in decision ? decision.review_findings_count : undefined;
  const consistent = "review_consistent" in decision ? decision.review_consistent === true : false;
  const semantic = decision.policy_decision === "BLOCK" && decision.codex_review === "CHANGES_REQUESTED" &&
    findings !== undefined && findings > 0 && consistent && decision.deterministic_gate === "PASS" &&
    ["LOW", "MEDIUM"].includes(decision.risk) && decision.issue === record.issue && decision.pr === record.pr &&
    decision.base_sha === record.base_sha && decision.head_sha === record.head_sha &&
    decision.roadmap_id === snapshot.spec.roadmap_id && decision.roadmap_item_id === snapshot.spec.roadmap_item_id &&
    decision.authorization_id === snapshot.spec.authorization_id && decision.repository === snapshot.spec.repository;
  if (!semantic) return terminal;
  if (ports.consummatedPayloadRepairs(record.issue, record.pr) >= 2) return {move: "ESCALATE_OWNER", reason: "consummated payload repair budget exhausted", lineage: undefined};
  // Across an advanced base the unconsummated repair synchronizes exactly like
  // a blocked-CI candidate: the trusted candidate (including a governed repair
  // candidate already published on the work branch) re-enters the pipeline at
  // the authorized base and is re-decided at its new head.
  if (snapshot.base.stale) return {move: "SYNCHRONIZE_CANDIDATE", reason: "unconsummated policy-blocked repair synchronizes across the advanced base", lineage: undefined};
  if (snapshot.observeRemoteHead() !== record.head_sha || snapshot.observePr()?.identity.headRefOid !== record.head_sha) return terminal;
  return {move: "RESUME_UNCONSUMMATED_REPAIR", reason: "changes-requested review never consummated a payload repair; governed resume within the payload budget", lineage: undefined};
}

function planBuilding(snapshot: CanonicalLifecycleSnapshot, ports: PlannerPorts): ReconciliationPlan {
  const record = snapshot.record;
  if (record.repair_cycles === 1 && record.builder_retry_reason === "BUILDER_FAILURE" && !record.pr && !record.head_sha) {
    return adoptPublishedInitialCandidate(snapshot, ports);
  }
  if (record.repair_cycles > 0 && record.repair_cycles <= 2 && record.pr && record.head_sha && record.builder_session && record.reviewer_session && record.decision_id) {
    if (snapshot.decision.missing) return {move: "AMBIGUOUS", reason: "repair decision missing from the immutable ledger", lineage: undefined};
    if (!snapshot.decision.loaded || !ports.decisionBoundToLineage(snapshot.decision.loaded)) return {move: "AMBIGUOUS", reason: "repair decision not bound to the candidate lineage", lineage: undefined};
    if (!blockedCiEffectChain(record)) return {move: "AMBIGUOUS", reason: "repair effect chain invalid", lineage: undefined};
    return {move: "SYNCHRONIZE_CANDIDATE", reason: "decided repair candidate synchronizes across the advanced base", lineage: undefined};
  }
  const pristinePreBuild = record.repair_cycles === 0 && !record.pr && !record.head_sha && !record.builder_session &&
    !record.reviewer_session && !record.decision_id &&
    record.completed_effects.length === 1 && record.completed_effects[0] === `issue:${record.issue}`;
  if (pristinePreBuild) {
    return {move: "REBIND_PRE_BUILD_BASE", reason: "pristine pre-build Issue rebases to the authorized base", lineage: undefined};
  }
  return {move: "AMBIGUOUS", reason: "building state without a consumable reconciliation move", lineage: undefined};
}

function planDecidedPostBuild(snapshot: CanonicalLifecycleSnapshot, ports: PlannerPorts): ReconciliationPlan {
  const record = snapshot.record;
  if (validBridgeAdoptionFacts(record) && ports.verifyBridgeCandidate(snapshot.spec.expected_base_sha, record.head_sha!) && remoteMatchesSnapshot(snapshot)) {
    return {move: "ADOPT_PUBLISHED_INITIAL_CANDIDATE", reason: "fully attested neutralization bridge adopted before ancestry fallback", lineage: undefined};
  }
  // An undecided post-build record whose same-PR payload advanced at the
  // matching base re-enters the pipeline at the new published head: the
  // trusted repair payload replaces the stale candidate identity.
  if (!snapshot.base.stale && !record.reviewer_session && !record.decision_id && samePrPayloadAdvanced(snapshot)) {
    return {move: "ADOPT_ADVANCED_PAYLOAD", reason: "undecided candidate adopts the advanced same-PR payload head at the matching base", lineage: undefined};
  }
  if (!snapshot.base.advanced) return {move: "AMBIGUOUS", reason: "decided post-build base is not ancestral", lineage: undefined};
  return {move: "SYNCHRONIZE_CANDIDATE", reason: "undecided post-build candidate synchronizes across the advanced base", lineage: undefined};
}

function samePrPayloadAdvanced(snapshot: CanonicalLifecycleSnapshot): boolean {
  const record = snapshot.record, spec = snapshot.spec;
  if (!record.pr || !record.head_sha || !spec.work_branch) return false;
  let remoteHead: string | undefined;
  try { remoteHead = snapshot.observeRemoteHead(); } catch { return false; }
  const pr = safe(() => snapshot.observePr());
  if (!remoteHead || remoteHead === record.head_sha || pr?.identity.headRefOid !== remoteHead) return false;
  if (pr.identity.author?.login !== spec.repository.split("/", 1)[0] || pr.identity.baseRefName !== "codex/own-capital-sustainable-return" ||
    pr.identity.baseRefOid !== record.base_sha || pr.identity.headRefName !== spec.work_branch ||
    pr.identity.headRepository?.nameWithOwner !== spec.repository || pr.identity.isCrossRepository !== false ||
    pr.identity.isDraft !== true || pr.identity.state !== "OPEN" || pr.identity.mergeable !== "MERGEABLE") return false;
  const files = (pr.identity.files ?? []).map((entry: any) => String(entry.path));
  if (files.length === 0 || !files.every((path: string) => pathAllowed(path, spec))) return false;
  return true;
}

function remoteMatchesSnapshot(snapshot: CanonicalLifecycleSnapshot): boolean {
  const expected = snapshot.record.head_sha;
  const observations = [safe(() => snapshot.observeRemoteHead()), safe(() => snapshot.observePr())?.identity.headRefOid]
    .filter((head): head is string => typeof head === "string");
  return observations.length > 0 && observations.every(head => head === expected);
}

function adoptPublishedInitialCandidate(snapshot: CanonicalLifecycleSnapshot, ports: PlannerPorts): ReconciliationPlan {
  const record = snapshot.record;
  if (!snapshot.base.advanced) return {move: "AMBIGUOUS", reason: "published initial candidate base is not ancestral", lineage: undefined};
  const trusted = snapshot.observePublishedCandidates().filter(candidate =>
    candidate.trustedAuthor && candidate.base === record.base_sha &&
    (candidate.identity.mergeable === "MERGEABLE" || candidate.identity.mergeable === "UNKNOWN" || candidate.identity.mergeable === undefined) &&
    candidate.number !== record.pr);
  if (trusted.length !== 1) return {move: "AMBIGUOUS", reason: `published candidate count invalid: ${trusted.length}`, lineage: undefined};
  return {move: "ADOPT_PUBLISHED_INITIAL_CANDIDATE", reason: "one trusted published candidate adopted and synchronized", lineage: undefined};
}

function adoptVerifiedSynchronized(snapshot: CanonicalLifecycleSnapshot, ports: PlannerPorts): ReconciliationPlan {
  const record = snapshot.record;
  const chain = snapshot.effectChain;
  const originAnchored = (!!chain && (chain.syncHeads.length > 0 || (record.builder_receipt_head_sha !== undefined && record.builder_receipt_base_sha !== undefined))) ||
    (!!snapshot.adoptionEvent && Array.isArray(snapshot.adoptionEvent.prior_effects) && snapshot.adoptionEvent.prior_effects.some((effect: unknown) => typeof effect === "string" && effect.startsWith("base-sync:")));
  if (!originAnchored || !record.issue || !record.pr || !record.head_sha) {
    return {move: "AMBIGUOUS", reason: "synchronized candidate evidence incomplete", lineage: undefined};
  }
  // The builder-recovered:<head> session shape is produced by the adoption
  // applier; a synchronized candidate may still carry its original session.
  // The false-provenance repair family: the current decision is a deterministic
  // provenance-recovery repair of the exact synchronized head. Its immutable
  // adoption event names the prior governed repair decision that is the true
  // provenance root. The generic role check replaces every incident predicate.
  const provenanceRepairHead = deterministicBuilderProvenanceRepairSessionHead(record.reviewer_session);
  if (provenanceRepairHead === record.head_sha) return revertInvalidatedAdoption(snapshot, ports);
  const prior = snapshot.decision.loaded;
  if (!prior || !ports.decisionBoundToLineage(prior)) return {move: "AMBIGUOUS", reason: "synchronized candidate has no decision bound to its lineage", lineage: undefined};
  if (!ports.checksGreenAtHead(record.head_sha)) return {move: "AMBIGUOUS", reason: "synchronized candidate CI not green", lineage: undefined};
  const lineage = deriveCandidateLineage(snapshot, prior);
  if (!lineage) return {move: "AMBIGUOUS", reason: "synchronized candidate lineage underivable", lineage: undefined};
  return {move: "ADOPT_VERIFIED_SYNCHRONIZED_CANDIDATE", reason: "verified synchronized candidate re-enters review with persisted provenance", lineage};
}

function revertInvalidatedAdoption(snapshot: CanonicalLifecycleSnapshot, ports: PlannerPorts): ReconciliationPlan {
  const record = snapshot.record;
  const adoption = safe(() => ports.recordedAdoptionEvent(record));
  if (!adoption || !Number.isInteger(adoption.repair_cycle) || adoption.repair_cycle < 1) {
    return {move: "AMBIGUOUS", reason: "adoption event missing for the invalidated provenance repair", lineage: undefined};
  }
  const prior = safe(() => adoption.prior_decision_id ? ports.loadDecision(String(adoption.prior_decision_id)) : undefined);
  if (!prior) return {move: "AMBIGUOUS", reason: "prior repair decision missing from the immutable ledger", lineage: undefined};
  const priorHeadRecorded = Array.isArray(adoption.prior_effects) && (adoption.prior_effects.includes(`build:${prior.head_sha}`) || adoption.prior_effects.includes(`base-sync:${prior.head_sha}`));
  if (!ports.decisionBoundToLineage(prior) && !priorHeadRecorded) return {move: "AMBIGUOUS", reason: "prior repair decision not bound to the candidate lineage", lineage: undefined};
  if (!ports.checksGreenAtHead(record.head_sha!)) return {move: "AMBIGUOUS", reason: "same-head CI not green", lineage: undefined};
  const lineage = deriveCandidateLineage({...snapshot, decision: {id: prior.decision_id, loaded: prior, missing: false}}, prior);
  if (!lineage) return {move: "AMBIGUOUS", reason: "invalidated adoption lineage underivable", lineage: undefined};
  return {move: "REVERT_INVALIDATED_ADOPTION", reason: "false deterministic provenance repair reverted to its immutable prior adoption", lineage};
}

function adoptExternalMerge(snapshot: CanonicalLifecycleSnapshot, ports: PlannerPorts): ReconciliationPlan {
  const record = snapshot.record;
  const chain = snapshot.effectChain;
  if (!chain || !record.pr || !record.head_sha || chain.mergeCommit !== undefined) return {move: "AMBIGUOUS", reason: "external merge evidence incomplete", lineage: undefined};
  if (!ports.authorizedBaseIsCanonicalTip()) return {move: "AMBIGUOUS", reason: "authorized base is not the canonical tip", lineage: undefined};
  return {move: "ADOPT_EXTERNAL_MERGE", reason: "externally merged candidate adopted after full identity and CI verification", lineage: undefined};
}

function recoverNegatedRisk(snapshot: CanonicalLifecycleSnapshot, ports: PlannerPorts): ReconciliationPlan {
  const record = snapshot.record;
  const decision = snapshot.decision.loaded;
  if (!decision) return {move: "ESCALATE_OWNER", reason: "escalation decision missing", lineage: undefined};
  // Semantic role: an escalation decision is generically recoverable when its
  // recorded review outcome is internally consistent (PASS with no findings, or
  // CHANGES_REQUESTED with findings). The exact enum combination of one
  // historical incident is never the gate.
  const findings = "review_findings_count" in decision ? decision.review_findings_count : undefined;
  const consistent = "review_consistent" in decision ? decision.review_consistent === true : true;
  const reviewRecoverable = consistent &&
    (decision.codex_review === "PASS" ? findings === undefined || findings === 0 : false) ||
    (decision.codex_review === "CHANGES_REQUESTED" ? findings !== undefined && findings > 0 : false);
  if (!reviewRecoverable || !snapshot.base.advanced) return {move: "ESCALATE_OWNER", reason: "escalation decision is not recoverable generically", lineage: undefined};
  if (!blockedCiEffectChain(record)) return {move: "AMBIGUOUS", reason: "negated-risk effect chain invalid", lineage: undefined};
  return {move: "RECOVER_NEGATED_RISK_ESCALATION", reason: "risk classification negated on the authorized item; escalation recovered after base advance", lineage: undefined};
}

function safe<T>(operation: () => T): T | undefined {try {return operation();} catch {return undefined;}}

// Deterministic-CI repair sessions are derived, never persisted ad hoc.
export const deterministicRepairSession = (head: string) => `reviewer:deterministic-ci:${head}`;
export const recoveredBuilderSession = (head: string) => `builder-recovered:${head}`;
export {blockedCiEffectChain, expandableBlockedCiEffectChain, privilegedInstallEffectChain};
