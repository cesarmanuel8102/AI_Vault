# BR1 Semantic Completion and Evidence Integrity Design

## Decision

BR1 introduces one TypeScript authority, `evaluateSemanticCompletion()`, for
semantic closure decisions. A green contract, reviewer result, lifecycle state,
or producer assertion cannot itself establish semantic completion. The authority
returns an immutable `SemanticCompletionDecisionV1` with `decision: "PASS" |
"BLOCK"`; every consumer projects that same result.

## Goals

- Bind every semantic requirement to immutable requirement identity and source.
- Require evidence whose identity, lineage, environment, verifier, artifact
  hash, source SHA, runtime binding, and duration/sample are valid.
- Prevent a semantic block from producing closeout success, terminal lifecycle,
  successor discovery, successor authorization, or certification.
- Preserve historical BRAIN-101 records as readable history, never as trusted
  evidence for a remediation requirement.
- Prove an L8 soak requirement cannot be satisfied by SIMULATED_30D evidence.

## Non-goals

- No database, network service, generalized policy DSL, scheduler activation,
  Agent Loop activation, HIVE integration, deployment, trading, or real-money
  code.
- No Python evaluator or parallel semantic decision authority.
- No rewrite of R0-R19 receipts, lifecycle records, or historical claims.

## Immutable Taxonomy

`EvidenceLevel` is exactly:
`L0_PRESENCE`, `L1_STATIC`, `L2_UNIT`, `L3_CONTRACT`,
`L4_SIMULATED_INTEGRATION`, `L5_LOCAL_E2E`, `L6_RUNTIME`,
`L7_EXTERNAL_PAPER`, `L8_SOAK`, `L9_ADVERSARIAL_TARGET_ENVIRONMENT`.

L9 means controlled adversarial testing against the actual target operational
environment appropriate to the requirement. It never implies live trading or
real money. Levels are ordered for minimum-level checks but are not mutually
substitutable: a requirement can additionally require evidence kinds.

## Data Contracts

`SemanticRequirementV1` contains exactly:
`requirement_id`, `parent_phase`, `original_spec_path`,
`original_spec_sha256`, `requirement_text_sha256`,
`minimum_evidence_level`, `required_evidence_kinds`,
`runtime_binding_required`, and `deferment_policy`.
Changing wording, source bytes, or any binding creates a new requirement
identity; retained IDs with changed hashes fail closed.

`EvidenceRefV1` binds one requirement to `evidence_id`, `requirement_id`,
`evidence_kind`, `evidence_level`, `source_sha`,
`certified_implementation_sha`, `artifact_path`, `artifact_sha256`,
`environment`, `runtime_binding`, `observed_at_utc`, `observation`, and a
verifier relationship. The verifier has a stable identity, source SHA, and
independence declaration. Bare booleans and self-authored producer claims are
not evidence.

`DefermentV1` requires `deferment_id`, `requirement_id`,
`authorization_source`, `reason`, `successor_owner`, `scope`,
`expiration_or_revisit_condition`, and `evidence_refs`. Informal phrases such
as `NO_DEPLOY`, `future work`, `too risky`, or `not needed now` are invalid.

`SemanticCompletionDecisionV1` contains `schema_version`, `phase_or_item_id`,
`original_requirement_refs`, requirement counters, `evidence_refs`,
`decision`, stable `reason_codes`, `source_sha`, `decision_artifact_sha256`,
and `evaluated_at_utc`. It is computed from canonicalized input by the gate;
lifecycle stores only its hash and decision receipt, never invents a PASS.

## Evaluation Rules

For every requirement, the gate validates exact identity, evidence ownership,
valid SHA-256 fields, source/implementation lineage, accepted environment,
required runtime binding, required evidence kinds, minimum level, observation
duration/sample, verifier relationship, freshness, and artifact hash.

It emits deterministic codes including `MISSING_REQUIREMENT`,
`MISSING_EVIDENCE`, `INSUFFICIENT_EVIDENCE_LEVEL`, `WRONG_EVIDENCE_KIND`,
`STALE_SOURCE_SHA`, `ARTIFACT_HASH_MISMATCH`, `RUNTIME_BINDING_MISSING`,
`SELF_REFERENTIAL_EVIDENCE`, `NAKED_BOOLEAN_ASSERTION`,
`SIMULATION_SUBSTITUTION`, `INVALID_DEFERMENT`,
`PARENT_REQUIREMENT_UNSATISFIED`, and `INDEPENDENT_AUDIT_MISSING`.
Unknown schema/field values, duplicate identifiers, malformed timestamps, and
ambiguous evidence also block.

## Integration

A future/remediation `ProxySpec` can carry `semantic_completion` metadata
pointing to canonical requirements and evidence artifacts. `ProductionEffects`
loads those immutable bytes at the bound merge SHA and calls the pure evaluator.
It records only a `semantic_completion:<decision_artifact_sha256>` effect on
PASS. `AutonomousFlow` cannot advance a semantic-bound parent through closeout
or terminal completion without that effect. The closeout child must bind the
same parent decision hash. `discoverNext()` is unreachable after a semantic
block and validates the same receipt before discovery.

Historical records without explicit semantic metadata remain readable only;
they are never promoted to semantic evidence.

CI invokes the same exported pure evaluator through an explicit semantic suite.
There is no CI-specific evaluator. `AGENTS.md` requires the gate and fresh
verification before COMPLETE/CLOSED/VERIFIED/READY/CERTIFIED claims.

## Tests and Safety

The regression suite SR01-SR16 covers a positive control, missing or wrong
requirements/evidence, level/kind/lineage/runtime/verifier/deferment failures,
wrong environment, stale code, artifact tampering, and successor escape. A
bounded synthetic Agent Loop fixture supplies L4 `SIMULATED_30D` to an L8
requirement while CI/review/contracts are green. It must yield BLOCK, no
closeout success, and no successor authorization. It does not run a worker or
scheduler.

Hard limits remain `HUMAN_FINAL_AUTHORITY=true`, `AUTO_MERGE=false`,
`CANONICAL_LOCAL_SYNC=false`, `LIVE_TRADING=false`, `REAL_MONEY=false`, and
PERSISTENT_AGENT_LOOP=DEFERRED; schedulers disabled.

