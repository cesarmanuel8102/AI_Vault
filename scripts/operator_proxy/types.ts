export type Risk = "LOW"|"MEDIUM"|"HIGH"|"CRITICAL";
export type Review = "PASS"|"CHANGES_REQUESTED"|"BLOCKED";
export type DeploymentMode = "NO_DEPLOY"|"INSTALL_ONLY"|"INSTALL_AND_RUNTIME_PILOT"|"DOCUMENTATION_CLOSEOUT";
export type InstallTarget = "agent_loop_worker";
export type LifecycleState =
  | "DISCOVERED" | "ADMITTED" | "ISSUE_CREATED" | "BUILDING" | "PR_CREATED"
  | "CI_PENDING" | "REVIEWING" | "REPAIRING" | "READY_TO_MERGE" | "MERGING"
  | "MERGED" | "INSTALL_PENDING" | "INSTALLING" | "RUNTIME_PILOT_PENDING"
  | "RUNTIME_PILOT_RUNNING" | "RUNTIME_VERIFIED" | "CLOSEOUT_PENDING"
  | "CLOSEOUT_MERGED" | "TERMINAL_COMPLETED" | "BLOCKED" | "OWNER_REPAIR_AUTHORIZED" | "ESCALATED";
export interface ReviewerOutput {verdict:Review;head_sha:string;summary:string;findings:{severity:"P0"|"P1"|"P2";title:string;evidence:string;required_correction:string}[]}
export type PolicyDecision = "APPROVE"|"REPAIR"|"BLOCK"|"ESCALATE_TO_OWNER";
export interface CampaignAuthorization {authorization_id:string;repository:string;owner_principal:string}
export interface RepositoryAuthorization {repository:string;owner_principal:string}
export interface OwnerAuthoritySources {campaign_candidates:readonly CampaignAuthorization[];repository_candidates:readonly RepositoryAuthorization[]}
export interface CorrectionPayloadV1 {schema_version:1;requirements:ReadonlyArray<{requirement_id:string;instruction:string}>;preserved_invariants:ReadonlyArray<string>;evidence_references?:ReadonlyArray<{kind:"issue_comment"|"commit"|"ci_run";value:string}>}
export interface OwnerAuthorizedPayloadRepairGrant {schema_version:1;authorization_id:string;grant_key:string;owner_principal:string;repository:string;roadmap_id:string;roadmap_item_id:string;front_id:string;issue:number;pr:number;work_branch:string;canonical_base_sha:string;failed_head_sha:string;eligible_failure_class:"CI_FAILED";max_extra_builds:1;correction_payload:CorrectionPayloadV1;correction_payload_sha256:string;owner_comment_id:string;authorization_body_sha256:string}
export interface OwnerAuthorizedCriticalMerge {schema_version:1;authorization_id:string;critical_merge_key:string;owner_principal:string;owner_comment_id:string;repository:string;issue:number;front_id:string;pr:number;base_branch:string;base_sha:string;head_branch:string;head_sha:string;policy_decision_id:string;policy_decision_key:string;policy_sha256:string;policy_outcome:"ESCALATE_TO_OWNER";ci_evidence_id:string;ci_evidence_sha256:string;review_receipt_id:string;review_receipt_sha256:string;reviewer_model:string;review_verdict:"PASS";review_findings_count:0;risk:"CRITICAL";action:"OWNER_AUTHORIZED_CRITICAL_MERGE";max_uses:1;authorization_body_sha256:string}
export interface CloseoutMetadata {front_id:string;objective:string;work_branch:string;executor:"agent_loop"|"codex_control_plane";risk:"LOW"|"MEDIUM";allowed_paths:string[];forbidden_paths:string[];acceptance:string[];test_commands:string[];test_profile?:"roadmap-doc"|"test-only";max_executor_cycles?:number}
export interface ProxySpec {schema_version:1;authorization_id:string;repository:string;roadmap_id:string;roadmap_version:string;roadmap_item_id:string;expected_base_sha:string;executor:"agent_loop"|"codex_control_plane";risk:Risk;allowed_paths:string[];forbidden_paths:string[];acceptance:string[];test_commands:string[];deployment_allowed:false;objective?:string;work_branch?:string;dependencies?:string[];deployment_mode?:DeploymentMode;install_target?:InstallTarget;front_id?:string;roadmap_sha256?:string;manifest_sha256?:string;test_profile?:"pilot"|"roadmap-doc"|"test-only";max_executor_cycles?:number;closeout?:CloseoutMetadata;closeout_only?:boolean;semantic_completion?:SemanticCompletionBindingV1}
export interface Evidence {issue:number;pr:number;base_sha:string;head_sha:string;head_branch:string;base_branch:string;author:string;state:string;draft:boolean;from_fork:boolean;mergeable:boolean;checks_terminal:boolean;checks_green:boolean;deterministic_gate:"PASS"|"FAIL";changed_files:string[];sensitive_files:string[];review:Review;review_session:string;builder_session:string;item_authorized:boolean;review_p0:boolean;review_p1:boolean;review_findings_count:number;review_consistent:boolean;repair_cycles:number}
export interface LegacyDecisionV1 {schema_version:1;decision_id:string;authorization_id:string;repository:string;issue:number;pr:number;base_sha:string;head_sha:string;roadmap_id:string;roadmap_item_id:string;risk:Risk;deterministic_gate:"PASS"|"FAIL";codex_review:Review;policy_decision:PolicyDecision;allowed_action:"NONE"|"MARK_READY"|"MERGE"|"REQUEST_REPAIR"|"DEPLOY";policy_sha256:string;evidence_sha256:string;created_utc:string}
export interface TransitionalKeyedDecisionV1 extends LegacyDecisionV1 {decision_key:string;review_findings_count:number;review_consistent:boolean}
export interface Decision extends Omit<TransitionalKeyedDecisionV1,"schema_version"> {schema_version:2}
export type NormalizedDecision = Decision | TransitionalKeyedDecisionV1 | (LegacyDecisionV1 & {decision_key:string;legacy_source_sha256:string});

export interface OwnerPayloadRepairEffectiveBaseAnchors {
  frozen_base_sha:string;
  failed_head_sha:string;
  effective_base_sha:string;
  effective_base_binding_sha256:string;
  synchronized_head_sha:string;
  runtime_support_sha:string;
  runtime_support_event_sha256:string;
}

export interface LifecycleRecord {
  schema_version: 1;
  front_id: string;
  roadmap_item_id: string;
  state: LifecycleState;
  issue?: number;
  pr?: number;
  base_sha: string;
  head_sha?: string;
  builder_session?: string;
  builder_receipt_head_sha?: string;
  builder_receipt_base_sha?: string;
  reviewer_session?: string;
  decision_id?: string;
  repair_cycles: number;
  deployment_mode: DeploymentMode;
  completed_effects: string[];
  last_error?: string;
  // Redacted, bounded evidence for diagnosis only; never used for lifecycle control.
  last_error_detail?: string;
  builder_retry_reason?: "BUILDER_FAILURE";
  owner_payload_repair?: {grant_key:string;consumed_event_sha256:string;build_attempt_id:string}&Partial<OwnerPayloadRepairEffectiveBaseAnchors>;
  owner_critical_merge?: {critical_merge_key:string;consumed_event_sha256:string};
  merge_reconciliation?: {
    source: "GITHUB_EXTERNALLY_MERGED_PR";
    issue: number;
    pr: number;
    original_base_sha: string;
    original_state_head_sha: string;
    candidate_head_sha: string;
    merge_commit_sha: string;
    reviewer_check: "review";
  };
  // Control plane that last wrote this record. Absent on records persisted before
  // the consolidation front and normalized to 1 on load. A writer-version change
  // is an explicit modeled reconciliation input, never accidental reinterpretation.
  state_writer_control_plane_version?: number;
  updated_utc: string;
}

export interface HistoricalAttemptRefV1 {
  schema_version: 1;
  front_id: string;
  roadmap_item_id: string;
  lifecycle_state: LifecycleState;
  issue: number;
  pr: number;
  base_sha: string;
  failed_head_sha: string;
  repair_cycles: 2;
  grant_key: string;
  consumed_event_sha256: string;
  build_attempt_id: string;
  historical_sha256: string;
}

export interface RebaselineHardLimitsV1 {
  human_final_authority: true;
  auto_merge: false;
  canonical_local_sync: false;
  live_trading: false;
  real_money: false;
}

export interface RebaselineHardLimitsInputV1 {
  human_final_authority: boolean;
  auto_merge: boolean;
  canonical_local_sync: boolean;
  live_trading: boolean;
  real_money: boolean;
}

export interface FunctionalEvidenceInputV1 {
  item_id: string;
  task_id: string;
  evidence_path: string;
  canonical_ref: string;
  evidence_bytes: Uint8Array;
  required_markers: readonly string[];
  hard_limits: RebaselineHardLimitsInputV1;
}

export interface FunctionalEvidenceAssertionV1 {
  schema_version: 1;
  item_id: string;
  task_id: string;
  evidence_path: string;
  canonical_ref: string;
  evidence_sha256: string;
  required_markers: readonly string[];
  hard_limits: RebaselineHardLimitsV1;
  status: "PASSED";
  assertion_sha256: string;
}

export interface ControllerSupersessionReceiptInputV1 {
  schema_version: 1;
  controller: "CODEX_GOVERNED_CONTROLLER";
  supersession_key: string;
  sequence: number;
  previous_event_sha256: string | null;
  repository: string;
  roadmap_item_id: string;
  canonical_base_sha: string;
  manifest_sha256: string;
  roadmap_sha256: string;
  historical_attempt_sha256: string;
  historical_base_sha: string;
  front_id: string;
  failed_head_sha: string;
  grant_key: string;
  consumed_event_sha256: string;
  build_attempt_id: string;
  functional_evidence_ref: string;
  functional_evidence_path: string;
  functional_evidence_sha256: string;
  functional_evidence_assertion_sha256: string;
  hard_limits: RebaselineHardLimitsV1;
  persistent_agent_loop_enabled: false;
  created_utc: string;
}

export interface ControllerSupersessionReceiptV1 extends ControllerSupersessionReceiptInputV1 {
  event_sha256: string;
}

export interface ControllerRebaselineCanonicalBindingV1 {
  repository: string;
  roadmap_item_id: string;
  canonical_base_sha: string;
  manifest_sha256: string;
  roadmap_sha256: string;
  item_status: "AUTHORIZED_ACTIVE" | "CLOSED_RUNTIME_VERIFIED";
  hard_limits: RebaselineHardLimitsV1;
}

export interface ControllerRebaselinePlanInputV1 {
  canonical: ControllerRebaselineCanonicalBindingV1;
  historical: HistoricalAttemptRefV1;
  evidence: FunctionalEvidenceAssertionV1;
  receipts: readonly ControllerSupersessionReceiptV1[];
}

export interface ControllerRebaselinePlan {
  status: "REBASELINE_REQUIRED" | "CLOSEOUT_ALLOWED" | "ALREADY_SUPERSEDED" | "BLOCKED";
  supersession_key?: string;
  reason?: string;
}

export type EvidenceLevel =
  | "L0_PRESENCE" | "L1_STATIC" | "L2_UNIT" | "L3_CONTRACT"
  | "L4_SIMULATED_INTEGRATION" | "L5_LOCAL_E2E" | "L6_RUNTIME"
  | "L7_EXTERNAL_PAPER" | "L8_SOAK" | "L9_ADVERSARIAL_TARGET_ENVIRONMENT";

export interface SemanticRequirementV1 {
  requirement_id:string; parent_phase:string; original_spec_path:string;
  original_spec_sha256:string; requirement_text_sha256:string;
  minimum_evidence_level:EvidenceLevel; required_evidence_kinds:string[];
  runtime_binding_required:boolean; deferment_policy:"FORBIDDEN"|"EXPLICIT_AUTHORIZATION_REQUIRED";
  parent_requirement_ids:string[]; required_environments:string[];
  independent_verifier_required:boolean; minimum_duration_seconds:number; minimum_sample_size:number;
  /**
   * Governed evidence cohort identity (BR1 Task 3): when two requirements
   * carry the same cohort_group, their evidence MUST bind the identical
   * soak_execution_id — proving properties of ONE governed execution.
   * Absent on non-cohort requirements.
   */
  cohort_group?:string;
}
export interface EvidenceRefV1 {
  evidence_id:string; requirement_id:string; evidence_kind:string; evidence_level:EvidenceLevel;
  source_sha:string; certified_implementation_sha:string; artifact_path:string; artifact_sha256:string;
  environment:string; runtime_binding:string; observed_at_utc:string;
  producer_id:string; assertion_type:"OBSERVATION"|"BOOLEAN";
  observation:{duration_seconds:number;sample_size:number};
  verifier:{verifier_id:string;source_sha:string;independent:boolean};
  /**
   * Governed soak execution identity (BR1 Task 3): the single governed
   * execution/window this observation belongs to. Required for requirements
   * carrying cohort_group; the AUTHORITATIVE value comes from the governed
   * soak execution manifest — evidence strings alone cannot authorize it.
   */
  soak_execution_id?:string;
  /** Regime evidence fields (BR1 Task 3): bound to the governed classifier. */
  observed_regime_ids?:string[];
  classifier_id?:string;
  classifier_version?:string;
  classifier_contract_sha256?:string;
}
/**
 * Governed evidence-kind contract document (BR1 Task 3), resolved from
 * immutable Git. Every kind used by canonical requirements must exist exactly
 * once with deterministic semantics; the decision binds the document bytes.
 */
export interface EvidenceKindContractsV1 {
  schema_version:1; roadmap_id:string;
  calendar_day_policy:"UTC_24H_DAY";
  minimum_regime_count_for_multiple:number;
  kinds:Record<string,{assertion_contract:string;attestation_model:string;zero_condition:boolean;tested_runtime_execution:boolean}>;
  /** SHA-256 of the exact governed document bytes (set by the trusted resolver). */
  evidence_kind_contracts_sha256?:string;
}
/**
 * Governed soak execution manifest (BR1 Task 3): the AUTHORITATIVE identity
 * of the one governed soak execution for an item. Evidence records cannot
 * self-authorize soak identity — they must match this Git-bound manifest.
 * Preregistration state (started/ended null) is a truthful representation
 * of a not-yet-executed soak.
 */
export interface GovernedSoakExecutionManifestV1 {
  schema_version:1; roadmap_id:string; roadmap_item_id:string;
  soak_execution_id:string; source_sha:string; environment:string;
  started_at_utc:string|null; ended_at_utc:string|null;
  calendar_day_policy:"UTC_24H_DAY"; runtime_binding:string;
  regime_classifier_id:string; regime_classifier_version:string;
  regime_classifier_contract_path:string; regime_classifier_contract_sha256:string;
  /** SHA-256 of the exact governed manifest bytes (set by the trusted resolver). */
  soak_execution_manifest_sha256?:string;
}
/**
 * Governed regime classifier contract (BR1 Task 3): preregisters WHICH
 * classifier identity defines regime distinctness for an item, frozen
 * before soak evidence exists. No regime labels are invented here.
 */
export interface GovernedRegimeClassifierContractV1 {
  schema_version:1; classifier_id:string; classifier_version:string;
  roadmap_id:string; roadmap_item_id:string;
  definition_path:string|null; definition_sha256:string|null;
  output_identity_semantics:string; minimum_distinct_regimes:number;
  frozen_source_sha:string; state:"PREREGISTERED_NOT_YET_OBSERVED"|"OBSERVED";
  /** SHA-256 of the exact governed contract bytes (set by the trusted resolver). */
  regime_classifier_contract_sha256?:string;
}
export interface DefermentV1 {
  deferment_id:string; requirement_id:string; authorization_source:string; reason:string;
  successor_owner:string; scope:string; expiration_or_revisit_condition:string; evidence_refs:string[];
}
export interface DefermentAuthorizationV1 {authorization_id:string;requirement_id:string;authorization_source_sha:string;authorized_by:string;scope:string;authorized_at_utc:string;}
export interface SemanticCompletionInputV1 {
  schema_version:1; phase_or_item_id:string; source_sha:string; evaluated_at_utc:string;
  requirements:SemanticRequirementV1[]; evidence:EvidenceRefV1[]; deferments:DefermentV1[];
  expected_requirement_ids:string[];
  expected_requirements:SemanticRequirementV1[];
  deferment_authorizations:DefermentAuthorizationV1[];
}
export type SemanticCompletionReasonCode =
  | "MISSING_REQUIREMENT" | "REQUIREMENT_IDENTITY_MISMATCH" | "MISSING_EVIDENCE" | "INSUFFICIENT_EVIDENCE_LEVEL"
  | "WRONG_EVIDENCE_KIND" | "STALE_SOURCE_SHA" | "ARTIFACT_HASH_MISMATCH"
  | "RUNTIME_BINDING_MISSING" | "SELF_REFERENTIAL_EVIDENCE" | "NAKED_BOOLEAN_ASSERTION"
  | "SIMULATION_SUBSTITUTION" | "AMBIGUOUS_EVIDENCE" | "EVIDENCE_TIMESTAMP_IN_FUTURE"
  | "INVALID_DEFERMENT" | "PARENT_REQUIREMENT_UNSATISFIED"
  | "INDEPENDENT_AUDIT_MISSING" | "CYCLIC_REQUIREMENT_DEPENDENCY"
  | "EVIDENCE_COHORT_MISMATCH" | "MISSING_EVIDENCE_COHORT_ID" | "EVIDENCE_COHORT_AUTHORITY_MISMATCH"
  | "REGIME_CLASSIFIER_AUTHORITY_MISMATCH" | "REGIME_ID_COUNT_MISMATCH"
  | "SOAK_EXECUTION_NOT_STARTED" | "REGIME_CLASSIFIER_NOT_MATERIALIZED";
export interface SemanticCompletionDecisionV1 {
  readonly schema_version:1; readonly phase_or_item_id:string; readonly original_requirement_refs:readonly string[];
  readonly requirements_total:number; readonly requirements_satisfied:number; readonly requirements_deferred_valid:number; readonly requirements_blocked:number;
  readonly evidence_refs:readonly string[]; readonly decision:"PASS"|"BLOCK"; readonly reason_codes:readonly SemanticCompletionReasonCode[];
  readonly source_sha:string; readonly decision_artifact_sha256:string; readonly evaluated_at_utc:string;
  /** SHA-256 of the governed evidence-kind contract bytes that interpreted the evidence (BR1 Task 3). */
  readonly evidence_kind_contracts_sha256?:string;
  /** SHA-256 of the governed soak execution manifest bytes (BR1 Task 3 execution authority). */
  readonly soak_execution_manifest_sha256?:string;
  /** SHA-256 of the governed regime classifier contract bytes (BR1 Task 3 regime authority). */
  readonly regime_classifier_contract_sha256?:string;
}

/** Declarative pointer telling ProductionEffects this front is semantic-bound. Paths are not trusted content. */
export interface SemanticCompletionBindingV1 {
  requirements_path:string;
  evidence_path:string;
  /** Optional declared kind-contract path; must equal the canonical governed path when present. */
  evidence_kind_contracts_path?:string;
}

/**
 * Trusted canonical source for every byte the semantic evaluator consumes.
 * The closeout caller can name the target item but can never define the
 * authoritative requirement universe, evidence, artifact bytes, or source SHA.
 * Implementations must resolve content from canonical repository/state only.
 */
export interface SemanticSourceV1 {
  /** Authoritative expected requirements for the bound roadmap item. */
  semanticRequirements(item:string):SemanticRequirementV1[];
  /** Evidence records discovered from canonical state for the bound item. */
  semanticEvidence(item:string):EvidenceRefV1[];
  semanticDeferments(item:string):DefermentV1[];
  semanticDefermentAuthorizations(item:string):DefermentAuthorizationV1[];
  /** Trusted canonical artifact bytes for an evidence artifact path. */
  artifactBytes(item:string,artifactPath:string):string|undefined;
  /** The canonical source SHA the item's evidence must be bound to. */
  canonicalSourceSha(item:string):string;
  /** Canonical UTC evaluation time; strict ISO-8601 UTC form required. */
  nowIsoUtc():string;
}
