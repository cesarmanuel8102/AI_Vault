
### Front: SELF-IMPROVEMENT-FIRST-FIVE-REAL-PATCH-MATERIALIZATION-PLAN-DRY-RUN-01
**Commit:** `TBD`
**Scope:** Create detailed materialization plans that describe how inert patch drafts would be turned into actual patches, without creating patch files, applying patches, modifying targets, staging, memory write, FAISS write, or promotion.
**Tests:** `97 passed` `smoke_self_improvement_first_five_real_patch_materialization_plan_dry_run.py`
**Evidence:** `tmp_agent/patch_materialization_plan_01/`
**Python:** `3.11.9`
**py_compile:** PASS for both module and tests

#### Fields
- real_patch_materialization_plan_id: stable generated
- real_patch_materialization_planning_candidate_id: linked to upstream review queue
- front_id: linked
- category: linked
- patch_type: linked
- plan_status: `materialization_plan_dry_run_only`
- dry_run_only: true
- materialization_allowed_now: false
- patch_file_creation_allowed_now: false
- git_apply_allowed_now: false
- target_file_modification_allowed_now: false
- patch_generation_allowed_now: false
- diff_generation_allowed_now: false
- patch_application_allowed_now: false
- real_patch_application_allowed_now: false
- patches_generated_for_application: false
- patches_applied: false
- patches_staged: false
- memory_write_allowed: false
- faiss_write_allowed: false
- real_write_allowed: false
- promotion_allowed: false
- required_tests: preserved from upstream
- acceptance_criteria: preserved from upstream
- operator_approval_packet: required, does not allow patch creation/application/git apply/target modification
- rollback_plan: required, discard artifacts only, preserve preexisting files
- risk_level: preserved or fallback medium
- next_safe_front: `SELF-IMPROVEMENT-FIRST-FIVE-REAL-PATCH-MATERIALIZATION-PLAN-REVIEW-DRY-RUN-01`

### Safety Flags
- materialization_allowed_now: false
- patch_file_creation_allowed_now: false
- git_apply_allowed_now: false
- target_file_modification_allowed_now: false
- patch_generation_allowed_now: false
- diff_generation_allowed_now: false
- patch_application_allowed_now: false
- real_patch_application_allowed_now: false
- patches_generated_for_application: false
- patches_applied: false
- patches_staged: false
- memory_write_allowed: false
- faiss_write_allowed: false
- real_write_allowed: false
- promotion_allowed: false
- must_not_create_patch_files: true
- must_not_run_git_apply: true
- must_not_modify_target_files: true

### Next Recommended
- SELF-IMPROVEMENT-FIRST-FIVE-REAL-PATCH-MATERIALIZATION-PLAN-REVIEW-DRY-RUN-01
