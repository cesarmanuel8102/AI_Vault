from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_provider_metadata_aliases_are_exposed() -> None:
    llm = _read("tmp_agent/brain_v9/core/llm.py")
    adapter = _read("tmp_agent/brain_v9/api/openai_compat.py")
    for field in ("cloud_provider_available", "codex_provider_available"):
        assert field in llm
        assert field in adapter


def test_provider_health_module_is_pure_and_classifies_kimi() -> None:
    source = _read("tmp_agent/brain_v9/provider_health/provider_health.py")
    forbidden = ("requests", "httpx", "urllib", "subprocess", "open(", "write_text", "semantic_memory", "faiss")
    assert not any(token in source for token in forbidden)

    from tmp_agent.brain_v9.provider_health.provider_health import build_provider_health_snapshot

    snapshot = build_provider_health_snapshot(
        ["kimi-k2.5:cloud", "llama3.1:8b"],
        k2_5_probe={"non_empty": False, "latency_ms": 1000},
        codex_available=True,
        local_llama_available=True,
        checked_utc="2026-06-12T00:00:00+00:00",
    )
    assert snapshot["cloud_provider_available"] is False
    assert snapshot["codex_provider_available"] is True
    records = {record["provider_id"]: record for record in snapshot["records"]}
    assert records["kimi_k2_6_cloud"]["status"] == "TAG_MISSING"
    assert records["kimi_k2_5_cloud"]["status"] == "PARTIAL_UNRELIABLE"


def test_training_artifacts_are_declared_without_semantic_writes() -> None:
    curriculum = ROOT / "docs" / "BRAIN_TRAINING_CURRICULUM.md"
    if curriculum.exists():
        text = curriculum.read_text(encoding="utf-8")
        assert "No semantic memory writes" in text
        assert "governed autonomy" in text.lower()
