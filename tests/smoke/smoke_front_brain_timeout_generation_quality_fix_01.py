from __future__ import annotations

import asyncio
import hashlib
import inspect
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TMP_AGENT = ROOT / "tmp_agent"
for candidate in (ROOT, TMP_AGENT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def _sha256(path: Path) -> str | None:
    if not path.exists():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_openai_compat_accepts_and_propagates_dry_run() -> None:
    source = _read("tmp_agent/brain_v9/api/openai_compat.py")
    assert "dry_run: bool = False" in source
    assert "metadata: Optional[Dict[str, Any]]" in source
    assert "def _request_dry_run" in source
    assert "dry_run=dry_run" in source
    assert '"read_only": dry_run' in source
    assert '"evaluation": dry_run' in source
    assert "LLMManager" not in source


def test_eval_harness_defaults_to_readonly_dry_run() -> None:
    source = _read("tmp_agent/brain_v9/evaluation/codex_brain_eval_harness.py")
    assert "dry_run: bool = True" in source
    assert '"dry_run": dry_run' in source
    assert '"read_only": dry_run' in source
    assert '"evaluation": True' in source
    assert "--live" in source
    assert "dry_run=not args.live" in source


def test_session_timeout_default_and_timeout_metadata() -> None:
    source = _read("tmp_agent/brain_v9/core/session.py")
    assert 'BRAIN_CHAT_LLM_TIMEOUT", "90"' in source
    assert '"source": "llm_timeout_fallback"' in source
    assert '"fallback_used": True' in source
    assert '"fallback_reason": "llm_timeout"' in source
    assert '"timeout_budget_s": llm_timeout_s' in source
    assert '"model_attempted": chain' in source
    assert '"recovery_suggestion"' in source


def test_timeout_fallback_classifier_marks_not_useful() -> None:
    from brain_v9.evaluation.codex_brain_eval_harness import classify_row

    row = classify_row(
        {
            "content": "El modelo tardó demasiado en responder tras 90s.",
            "brain": {
                "intent": "QUERY",
                "route": "llm",
                "governance_applied": True,
                "no_cot_leak": True,
                "canonical_path": str(ROOT),
            },
            "error": None,
            "latency_ms": 90001,
        }
    )
    assert row["fallback_used"] is True
    assert row["useful_response"] is False
    assert row["fallback_reason"] == "timeout_or_deterministic_fallback"


def test_default_eval_suite_and_status_files_are_valid() -> None:
    suite = ROOT / "tmp_agent/brain_v9/evaluation/default_codex_brain_eval_suite.json"
    roadmap = ROOT / "ROADMAP_STATUS.json"
    ledger = ROOT / "docs/MIGRATION_CONTROL_LEDGER.md"
    assert suite.exists()
    assert json.loads(suite.read_text(encoding="utf-8-sig")).get("prompts")
    assert json.loads(roadmap.read_text(encoding="utf-8"))
    assert ledger.exists()


def test_openai_compat_dry_run_response_shape_without_memory_mutation() -> None:
    from brain_v9.api.openai_compat import OpenAIChatCompletionRequest, OpenAIChatMessage, chat_completions

    semantic_path = ROOT / "memory/semantic/semantic_memory.jsonl"
    before_hash = _sha256(semantic_path)
    before_lines = semantic_path.read_text(encoding="utf-8").count("\n") if semantic_path.exists() else None

    payload = OpenAIChatCompletionRequest(
        model="brain-v9-local",
        messages=[OpenAIChatMessage(role="user", content="dry-run smoke: estado operativo en una frase")],
        dry_run=True,
        metadata={"dry_run": True, "read_only": True, "evaluation": True},
    )
    response = asyncio.run(chat_completions(payload))

    after_hash = _sha256(semantic_path)
    after_lines = semantic_path.read_text(encoding="utf-8").count("\n") if semantic_path.exists() else None

    assert response["object"] == "chat.completion"
    assert response["choices"][0]["message"]["content"]
    assert response["brain"]["adapter"] == "openai_compat"
    assert response["brain"]["dry_run"] is True
    assert response["brain"]["read_only"] is True
    assert before_hash == after_hash
    assert before_lines == after_lines


def test_openai_compat_signature_stays_router_only() -> None:
    from brain_v9.api import openai_compat

    source = inspect.getsource(openai_compat.chat_completions)
    assert "handle_user_message" in source
    assert "dry_run=dry_run" in source
    assert "BrainSession" not in source
    assert "semantic_memory" not in source
