# FRONT-BRAIN-CORE-PATH-CENTRALIZATION-08

Status: IMPLEMENTED_VALIDATED

## Scope
Centralized active non-trading core paths in:
- 	mp_agent/brain_v9/core/governed_action_kernel.py
- 	mp_agent/brain_v9/core/semantic_memory.py

## Changes
- GAK workspace root now derives from BASE_PATH / tmp_agent / workspace.
- GAK relative path policy resolves against BASE_PATH, not C:/AI_VAULT.
- Semantic memory FAISS detection uses SEMANTIC_ROOT / semantic_memory_faiss.index.

## Validation
- py_compile: PASS
- 	ests/smoke/test_front_brain_core_path_centralization_08.py: 2 passed
- Focal Agent/dashboard regression: 16 passed

## Remaining Debt
Other legacy/trading/tools paths remain outside this surgical non-trading core change.

## Safety
No real money, broker/IBKR, trading code, memory/semantic data, FAISS/index, .env, or secrets touched.
