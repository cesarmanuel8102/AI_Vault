# Retrieval Injection Authorization Summary

## Status
AUTHORIZATION_REQUIRED

## Protected Runtime Change Required
True

## Memory Mutated
False

## FAISS Mutated
False

## Proposed Insertion Point
- file: tmp_agent/brain_v9/core/session.py
- function: _route_to_llm
- line_approx: 2280
- protected_file: True

## Retrieval Injection Contract
- read_only_memory: True
- read_only_faiss: True
- max_retrieval_hits: 3
- max_context_chars: 2500
- retrieval_summary_only: True
- no_raw_cot: True
- timeout_budget_s: 20
- fallback_if_retrieval_fails: True

## Next Front if Authorized
FRONT-CHAT-ROUTE-RETRIEVAL-INJECTION-PATCH-01

## Next Front if Denied
FRONT-CHAT-GROUNDED-RESPONSE-EVAL-WITHOUT-INJECTION-01
