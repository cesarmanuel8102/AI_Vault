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
export interface ProxySpec {schema_version:1;authorization_id:string;repository:string;roadmap_id:string;roadmap_version:string;roadmap_item_id:string;expected_base_sha:string;executor:"agent_loop"|"codex_control_plane";risk:Risk;allowed_paths:string[];forbidden_paths:string[];acceptance:string[];test_commands:string[];deployment_allowed:false;objective?:string;work_branch?:string;dependencies?:string[];deployment_mode?:DeploymentMode;install_target?:InstallTarget;front_id?:string;roadmap_sha256?:string;manifest_sha256?:string;test_profile?:"pilot"|"roadmap-doc"|"test-only";max_executor_cycles?:number;closeout?:CloseoutMetadata;closeout_only?:boolean}
export interface Evidence {issue:number;pr:number;base_sha:string;head_sha:string;head_branch:string;base_branch:string;author:string;state:string;draft:boolean;from_fork:boolean;mergeable:boolean;checks_terminal:boolean;checks_green:boolean;deterministic_gate:"PASS"|"FAIL";changed_files:string[];sensitive_files:string[];review:Review;review_session:string;builder_session:string;item_authorized:boolean;review_p0:boolean;review_p1:boolean;review_findings_count:number;review_consistent:boolean;repair_cycles:number}
export interface LegacyDecisionV1 {schema_version:1;decision_id:string;authorization_id:string;repository:string;issue:number;pr:number;base_sha:string;head_sha:string;roadmap_id:string;roadmap_item_id:string;risk:Risk;deterministic_gate:"PASS"|"FAIL";codex_review:Review;policy_decision:PolicyDecision;allowed_action:"NONE"|"MARK_READY"|"MERGE"|"REQUEST_REPAIR"|"DEPLOY";policy_sha256:string;evidence_sha256:string;created_utc:string}
export interface TransitionalKeyedDecisionV1 extends LegacyDecisionV1 {decision_key:string;review_findings_count:number;review_consistent:boolean}
export interface Decision extends Omit<TransitionalKeyedDecisionV1,"schema_version"> {schema_version:2}
export type NormalizedDecision = Decision | TransitionalKeyedDecisionV1 | (LegacyDecisionV1 & {decision_key:string;legacy_source_sha256:string});

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
  owner_payload_repair?: {grant_key:string;consumed_event_sha256:string;build_attempt_id:string};
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
