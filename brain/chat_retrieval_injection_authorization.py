"""brain/chat_retrieval_injection_authorization.py
FRONT-CHAT-ROUTE-RETRIEVAL-INJECTION-AUTHORIZATION-01

Pure planning module. No runtime patch. No protected file mutation.
Defines authorization requirements for injecting retrieval context into /chat.
"""

from typing import Any, Dict, List

BATCH_FRONT = "FRONT-CHAT-ROUTE-RETRIEVAL-INJECTION-AUTHORIZATION-01"


def front_id() -> str:
    return BATCH_FRONT


def protected_files_requiring_authorization() -> List[Dict[str, Any]]:
    return [
        {
            "path": "tmp_agent/brain_v9/core/session.py",
            "reason": "_route_to_llm() at line ~2275 is where system prompt is built and LLM is called. Retrieval context must be injected here before llm.query().",
            "min_lines": 1,
            "max_lines": 15,
            "risk": "medium",
        },
        {
            "path": "tmp_agent/brain_v9/core/llm.py",
            "reason": "_ollama() at line ~773 has model-specific timeouts (60-90s). The asyncio.wait_for envelope in _route_to_llm() is 12s. If Ollama embedding adds ~3-5s, we may need to bump envelope to 20s.",
            "min_lines": 0,
            "max_lines": 3,
            "risk": "low",
            "optional": True,
        },
        {
            "path": "tmp_agent/brain_v9/main.py",
            "reason": "main.py line ~1745 has asyncio.wait_for(session.chat(), timeout=30). If session.chat() now includes retrieval + LLM, may need to adjust to 25s.",
            "min_lines": 0,
            "max_lines": 2,
            "risk": "low",
            "optional": True,
        },
    ]


def current_chat_flow() -> List[Dict[str, Any]]:
    return [
        {"file": "tmp_agent/brain_v9/main.py", "line": 1377, "action": "@app.post('/chat')"},
        {"file": "tmp_agent/brain_v9/main.py", "line": 1745, "action": "session.chat() call with 30s asyncio envelope"},
        {"file": "tmp_agent/brain_v9/core/session.py", "line": 341, "action": "session.chat() handles slash commands, routing"},
        {"file": "tmp_agent/brain_v9/core/session.py", "line": 951, "action": "calls _route_to_llm(msg_stripped, intent, history, model_priority)"},
        {"file": "tmp_agent/brain_v9/core/session.py", "line": 2275, "action": "_route_to_llm() builds system prompt and calls llm.query() with 12s envelope"},
        {"file": "tmp_agent/brain_v9/core/llm.py", "line": 773, "action": "_ollama() POST to localhost with per-model timeout (60-90s)"},
    ]


def proposed_insertion_point() -> Dict[str, Any]:
    return {
        "file": "tmp_agent/brain_v9/core/session.py",
        "function": "_route_to_llm",
        "line_approx": 2280,
        "description": "Immediately after entering _route_to_llm(), before building the system prompt, query FAISS for relevant context and compact it into a context string.",
        "protected_file": True,
        "min_change_lines": 8,
        "max_change_lines": 15,
        "why_here": "This is the last point before the LLM call where we can inject external context without affecting routing logic.",
    }


def retrieval_injection_contract() -> Dict[str, Any]:
    return {
        "read_only_memory": True,
        "read_only_faiss": True,
        "max_retrieval_hits": 3,
        "max_context_chars": 2500,
        "retrieval_summary_only": True,
        "no_raw_cot": True,
        "timeout_budget_s": 20,
        "fallback_if_retrieval_fails": True,
        "no_trading": True,
        "no_b8": True,
        "no_connectors": True,
        "no_external_network": True,
        "compact_format": "source=ID score=S: snippet",
        "opt_in_mechanism": "If user message contains 'memory' or 'project knowledge', trigger retrieval. Otherwise skip to preserve latency.",
    }


def proposed_patch_plan() -> Dict[str, Any]:
    return {
        "implementation_must_happen_in_later_front": True,
        "later_front_name": "FRONT-CHAT-ROUTE-RETRIEVAL-INJECTION-PATCH-01",
        "requires_user_authorization": True,
        "steps": [
            "1. In session.py _route_to_llm(): detect opt-in trigger ('memory', 'project knowledge', etc.)",
            "2. If triggered, call get_semantic_memory_faiss().search(query, top_k=3, min_score=0.01)",
            "3. Compact top hits into context string (max 2500 chars)",
            "4. Append compact context to system prompt or pass as separate context parameter",
            "5. If retrieval fails or times out, silently continue with empty context (fallback)",
            "6. No modification to memory/semantic/* or FAISS index",
            "7. Adjust asyncio.wait_for envelope from 12s to 20s in _route_to_llm() if needed",
            "8. Adjust asyncio.wait_for envelope from 30s to 25s in main.py if needed",
        ],
        "rollback": "Revert session.py changes. No data mutation.",
        "risks": [
            "Ollama embedding call adds 3-5s latency to chat response",
            "Affects all chat responses if opt-in is too broad",
            "Could cause timeout if Ollama is under load",
        ],
        "mitigations": [
            "Strict opt-in keyword detection before retrieval",
            "Compact context only (no raw JSON dumps)",
            "Fallback to no-retrieval on any error",
            "Short timeout on embedding call (5s max)",
        ],
        "expected_files_modified": [
            "tmp_agent/brain_v9/core/session.py",
            "tmp_agent/brain_v9/core/llm.py (optional, timeout only)",
            "tmp_agent/brain_v9/main.py (optional, timeout only)",
        ],
    }


def future_tests_required() -> List[Dict[str, Any]]:
    return [
        {"name": "test_retrieval_injection_opt_in_trigger", "description": "Verify retrieval only triggers on opt-in keywords"},
        {"name": "test_retrieval_injection_compact_context", "description": "Verify context is compact and ≤2500 chars"},
        {"name": "test_retrieval_injection_no_raw_cot", "description": "Verify no chain-of-thought leakage"},
        {"name": "test_retrieval_injection_fallback", "description": "Verify fallback works when retrieval fails"},
        {"name": "test_retrieval_injection_timeout", "description": "Verify chat completes within 20s even with retrieval"},
        {"name": "test_retrieval_injection_memory_untouched", "description": "Verify semantic_memory.jsonl unchanged after chat"},
        {"name": "test_retrieval_injection_faiss_untouched", "description": "Verify FAISS index unchanged after chat"},
        {"name": "test_retrieval_injection_no_trading", "description": "Verify no trading connector triggered"},
        {"name": "test_retrieval_injection_marker_match", "description": "Verify injected responses contain learned markers"},
        {"name": "test_retrieval_injection_markdown_only", "description": "Verify compact markdown-like context, no raw JSON"},
    ]


def authorization_decision_template() -> Dict[str, Any]:
    return {
        "status": "AUTHORIZATION_REQUIRED",
        "required_user_decision": True,
        "authorized_files": [],
        "denied_files": [],
        "required_files": [
            "tmp_agent/brain_v9/core/session.py",
            "tmp_agent/brain_v9/core/llm.py (optional)",
            "tmp_agent/brain_v9/main.py (optional)",
        ],
        "next_front_if_authorized": "FRONT-CHAT-ROUTE-RETRIEVAL-INJECTION-PATCH-01",
        "next_front_if_denied": "FRONT-CHAT-GROUNDED-RESPONSE-EVAL-WITHOUT-INJECTION-01",
        "contract": retrieval_injection_contract(),
        "patch_plan": proposed_patch_plan(),
    }


def summarize_authorization() -> Dict[str, Any]:
    return {
        "front_id": BATCH_FRONT,
        "status": "AUTHORIZATION_REQUIRED",
        "protected_runtime_change_required": True,
        "memory_mutated": False,
        "faiss_mutated": False,
        "current_chat_flow": current_chat_flow(),
        "proposed_insertion_point": proposed_insertion_point(),
        "retrieval_injection_contract": retrieval_injection_contract(),
        "proposed_patch_plan": proposed_patch_plan(),
        "future_tests": future_tests_required(),
        "authorization_decision": authorization_decision_template(),
        "network_called": False,
        "connector_called": False,
        "trading_executed": False,
        "b8_touched": False,
        "no_raw_cot": True,
    }
