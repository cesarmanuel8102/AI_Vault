from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any, Callable, Dict, List


ROOT = Path(__file__).resolve().parents[2]
TMP_AGENT = ROOT / "tmp_agent"
if str(TMP_AGENT) not in sys.path:
    sys.path.insert(0, str(TMP_AGENT))

from brain_v9.core.scvl_promotion_gate import apply_scvl_promotion_gate
from brain_v9.core.session_scvl_gate import apply_scvl_final_answer_gate


FINAL_FLAG = "BRAIN_SCVL_GATE_ENABLED"
PROMOTION_FLAG = "BRAIN_SCVL_PROMOTION_GATE_ENABLED"


class EnvFlags:
    def __init__(self, **values: str | None):
        self.values = values
        self.previous: Dict[str, str | None] = {}

    def __enter__(self):
        for key, value in self.values.items():
            self.previous[key] = os.environ.get(key)
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def __exit__(self, exc_type, exc, tb):
        for key, value in self.previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def coherent_validator(**kwargs):
    assert kwargs["response_content"]
    return {"passed": True, "coherence_score": 0.91, "contradictions_detected": 0}


def incoherent_validator(**kwargs):
    return {
        "passed": False,
        "coherence_score": 0.08,
        "contradictions_detected": 1,
        "recommended_action": "reject_incoherent_e2e_output",
    }


class MiniSemanticStore:
    """Temp-dir semantic store harness for 11C.

    It intentionally avoids FAISS/Ollama/runtime memory. The goal is to exercise the
    gate contract across promote -> retrieve -> use without mutating canonical data.
    """

    def __init__(self, root: Path):
        self.root = Path(root)
        self.records_path = self.root / "semantic_memory.jsonl"
        self.root.mkdir(parents=True, exist_ok=True)

    def _records(self) -> List[Dict[str, Any]]:
        if not self.records_path.exists():
            return []
        rows: List[Dict[str, Any]] = []
        for line in self.records_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rows.append(json.loads(line))
        return rows

    def promote(self, candidate: Dict[str, Any], *, validator: Callable[..., Dict[str, Any]]) -> Dict[str, Any]:
        gate = apply_scvl_promotion_gate(candidate=candidate, context={"validator": validator, "route": "semantic_promotion"})
        if gate.get("enabled") and not gate.get("allowed"):
            return {"ok": False, "inserted": False, "error": "scvl_promotion_blocked", "scvl": gate.get("scvl", {})}
        payload = dict(candidate)
        payload.setdefault("metadata", {})
        if gate.get("enabled") and isinstance(payload.get("metadata"), dict):
            payload["metadata"]["scvl"] = gate.get("scvl", {})
        with self.records_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")
        return {"ok": True, "inserted": True, "id": payload.get("id"), "records": len(self._records())}

    def retrieve(self, query: str) -> List[Dict[str, Any]]:
        needle = query.lower().strip()
        return [rec for rec in self._records() if needle in str(rec.get("text", "")).lower()]


class FakeToolGateway:
    def execute(self, tool_name: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        if tool_name != "memory_lookup":
            return {"success": False, "content": "unsupported tool", "tool_name": tool_name}
        hits = payload.get("hits") or []
        snippet = str(hits[0].get("text")) if hits else "no memory hit"
        return {"success": True, "content": f"Tool result: {snippet}", "tool_name": tool_name}


class RuntimeFallbackHarness:
    def __init__(self):
        self.calls: List[str] = []

    def native(self, context: Dict[str, Any]) -> Dict[str, Any]:
        self.calls.append("native")
        raise RuntimeError("native unavailable")

    def langgraph(self, context: Dict[str, Any]) -> Dict[str, Any]:
        self.calls.append("langgraph")
        return {
            "success": True,
            "content": f"Fallback preserved context: {context['request_id']} / {context['memory_hint']}",
            "route": "langgraph_fallback",
            "context": dict(context),
        }

    def run(self, context: Dict[str, Any]) -> Dict[str, Any]:
        try:
            return self.native(context)
        except Exception:
            return self.langgraph(context)


def test_promote_retrieve_use_with_scvl_gates_enabled():
    with EnvFlags(**{FINAL_FLAG: "true", PROMOTION_FLAG: "true"}):
        with tempfile.TemporaryDirectory() as tmp:
            store = MiniSemanticStore(Path(tmp) / "semantic")
            promoted = store.promote(
                {"id": "m1", "text": "Kimi agent must validate semantic outputs before persistence."},
                validator=coherent_validator,
            )
            assert promoted["ok"] is True

            hits = store.retrieve("kimi agent")
            assert len(hits) == 1
            assert hits[0]["metadata"]["scvl"]["passed"] is True

            tool = FakeToolGateway().execute("memory_lookup", {"hits": hits})
            final = apply_scvl_final_answer_gate(
                message="Use persisted memory about Kimi agent validation.",
                result={"success": True, "content": tool["content"], "tool_name": tool["tool_name"], "route": "tool_gateway"},
                context={"validator": coherent_validator, "route": "tool_gateway", "tools_used": ["memory_lookup"]},
            )
            assert final["success"] is True
            assert final["scvl"]["passed"] is True
            assert "Kimi agent" in final["content"]


def test_scvl_rejection_prevents_promotion_and_memory_mutation():
    with EnvFlags(**{PROMOTION_FLAG: "true"}):
        with tempfile.TemporaryDirectory() as tmp:
            store = MiniSemanticStore(Path(tmp) / "semantic")
            before = store._records()
            rejected = store.promote({"id": "bad", "text": "contradictory candidate"}, validator=incoherent_validator)
            after = store._records()

            assert rejected["ok"] is False
            assert rejected["error"] == "scvl_promotion_blocked"
            assert rejected["scvl"]["passed"] is False
            assert before == after == []
            assert not store.records_path.exists()


def test_tool_route_final_answer_blocks_incoherent_output():
    with EnvFlags(**{FINAL_FLAG: "true"}):
        tool = FakeToolGateway().execute("memory_lookup", {"hits": [{"text": "safe fact"}]})
        final = apply_scvl_final_answer_gate(
            message="Return a coherent tool-grounded answer.",
            result={"success": True, "content": tool["content"], "tool_name": tool["tool_name"], "route": "tool_gateway"},
            context={"validator": incoherent_validator, "route": "tool_gateway", "tools_used": ["memory_lookup"]},
        )
        assert final["success"] is False
        assert final["scvl"]["passed"] is False
        assert final["scvl"]["reason"] == "reject_incoherent_e2e_output"


def test_runtime_fallback_preserves_context_and_passes_final_gate():
    with EnvFlags(**{FINAL_FLAG: "true"}):
        harness = RuntimeFallbackHarness()
        context = {"request_id": "req-11c", "memory_hint": "validated-memory"}
        result = harness.run(context)
        final = apply_scvl_final_answer_gate(
            message="Use fallback runtime without losing context.",
            result=result,
            context={"validator": coherent_validator, "route": "langgraph_fallback", "tools_used": []},
        )

        assert harness.calls == ["native", "langgraph"]
        assert final["success"] is True
        assert final["scvl"]["passed"] is True
        assert final["context"] == context
        assert "req-11c" in final["content"]


def test_static_no_runtime_or_regulated_touch_tokens():
    source = Path(__file__).read_text(encoding="utf-8")
    forbidden = [
        "GITHUB" + "_TOKEN",
        "api." + "github.com",
        "place" + "Order",
        "submit" + "_order",
        "dry_run_only" + "=False",
        "dry_run_only " + "= False",
        "faiss." + "write_index",
        "faiss." + "add",
        "rebuild_" + "index(",
        "compact(" + "dry_run=False",
    ]
    for token in forbidden:
        assert token not in source


if __name__ == "__main__":
    test_promote_retrieve_use_with_scvl_gates_enabled()
    test_scvl_rejection_prevents_promotion_and_memory_mutation()
    test_tool_route_final_answer_blocks_incoherent_output()
    test_runtime_fallback_preserves_context_and_passes_final_gate()
    test_static_no_runtime_or_regulated_touch_tokens()
    print("AUTONOMY_E2E_MEMORY_TOOL_FALLBACK_11C_OK")
