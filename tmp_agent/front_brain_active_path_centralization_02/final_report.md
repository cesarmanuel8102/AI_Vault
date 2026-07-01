# FRONT-BRAIN-HARDCODED-PATHS-ACTIVE-MODULES-02

Status: IMPLEMENTED_VALIDATED

Implemented:
- promotion_candidate_promoter.py: ROOT = BASE_PATH.
- promotion_pipeline_adapter.py: ROOT = BASE_PATH.
- capability_evaluator.py: targeted regression paths, cwd and PYTHONPATH now derive from BASE_PATH.
- Added 	ests/smoke/test_front_brain_active_path_centralization_02.py.

Validation:
- python -m py_compile passed for modified modules and smoke.
- pytest tests/smoke/test_front_brain_active_path_centralization_02.py tests/smoke/test_front_brain_provider_centralization_01.py -q: 5 passed.

Safety:
- No broker, no real money.
- No memory/semantic mutation.
- No FAISS mutation.
- No trading mutation.
- No .env mutation.

Next recommended front: FRONT-BRAIN-MEMORY-OWNERSHIP-CONTRACT-TESTS-01.
