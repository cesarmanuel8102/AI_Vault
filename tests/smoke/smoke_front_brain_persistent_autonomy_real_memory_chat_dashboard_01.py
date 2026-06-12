from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[2]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_persistent_supervisor_watchdog_and_control_exist():
    for path in [
        "tmp_agent/brain_v9/autonomy/persistent_supervisor.py",
        "tmp_agent/brain_v9/autonomy/autonomy_watchdog.py",
        "tmp_agent/brain_v9/autonomy/autonomy_heartbeat.py",
        "tmp_agent/brain_v9/autonomy/autonomy_control.py",
        "tmp_agent/brain_v9/autonomy/autonomy_scheduler.py",
    ]:
        assert (ROOT / path).exists()
    control = read("tmp_agent/brain_v9/autonomy/autonomy_control.py")
    assert "STOP_AUTONOMY" in control
    assert "PAUSE_AUTONOMY" in control
    assert "RUN_ONCE" in control


def test_cli_tools_exist():
    for path in [
        "tools/brain_autonomy_run_once.ps1",
        "tools/brain_autonomy_status.ps1",
        "tools/brain_autonomy_pause.ps1",
        "tools/brain_autonomy_resume.ps1",
        "tools/brain_autonomy_stop.ps1",
        "tools/brain_autonomy_install_scheduled_task.ps1",
        "tools/brain_autonomy_uninstall_scheduled_task.ps1",
    ]:
        assert (ROOT / path).exists()
    installer = read("tools/brain_autonomy_install_scheduled_task.ps1")
    assert "BrainGovernedAutonomy" in installer
    assert "brain_autonomy_run_once.ps1" in installer


def test_real_memory_architecture_files_exist():
    for path in [
        "tmp_agent/brain_v9/memory/autonomous_memory_writer.py",
        "tmp_agent/brain_v9/memory/semantic_promotion_queue.py",
        "tmp_agent/brain_v9/memory/memory_snapshot.py",
        "tmp_agent/brain_v9/memory/memory_rollback.py",
        "tmp_agent/brain_v9/memory/shadow_faiss_builder.py",
        "tmp_agent/brain_v9/memory/memory_auditor.py",
    ]:
        assert (ROOT / path).exists()
    assert (ROOT / "memory/autonomous_journal.jsonl").exists()
    assert (ROOT / "memory/promotion_queue").exists()
    assert (ROOT / "memory/semantic_staging/semantic_memory_candidate.jsonl").exists()


def test_memory_journal_and_promotion_queue_have_real_records():
    journal = [json.loads(line) for line in read("memory/autonomous_journal.jsonl").splitlines() if line.strip()]
    assert len(journal) >= 5
    for rec in journal[:5]:
        for key in ["event_id", "created_utc", "source_cycle", "category", "confidence", "evidence_path", "retention_class", "promotion_status"]:
            assert key in rec
    queue_files = list((ROOT / "memory/promotion_queue").glob("*.json"))
    assert len(queue_files) >= 5


def test_promotion_validator_blocks_cot_secrets_and_limits_canonical_batch():
    source = read("tmp_agent/brain_v9/memory/semantic_promotion_queue.py")
    assert "MAX_CANONICAL_BATCH = 5" in source
    assert "chain[- ]of[- ]thought" in source
    assert "sk-[A-Za-z0-9]" in source
    from tmp_agent.brain_v9.memory.semantic_promotion_queue import SemanticPromotionCandidate, validate_promotion_candidate

    bad = SemanticPromotionCandidate(text="contains chain-of-thought", source_event_id="e", source_cycle="c", category="autonomy_lesson", confidence=0.9, evidence_path="x")
    assert validate_promotion_candidate(bad)


def test_shadow_faiss_builder_does_not_overwrite_canonical():
    source = read("tmp_agent/brain_v9/memory/shadow_faiss_builder.py")
    assert "canonical_overwritten" in source
    assert "memory/semantic_staging" in source
    assert "memory/semantic/semantic_memory_faiss.index" not in source
    manifest = ROOT / "memory/semantic_staging/shadow_faiss/shadow_manifest.json"
    assert manifest.exists()
    data = json.loads(manifest.read_text(encoding="utf-8"))
    assert data["canonical_overwritten"] is False


def test_rollback_modules_and_audit_exist():
    assert (ROOT / "memory/rollback_snapshots/README.md").exists()
    assert (ROOT / "memory/semantic/promotion_audit.jsonl").exists()
    audit = read("memory/semantic/promotion_audit.jsonl")
    assert "canonical_semantic_promoted" in audit


def test_dashboard_app_chat_route_and_status_endpoint_exist():
    for path in [
        "tmp_agent/brain_v9/dashboard/dashboard_app.py",
        "tmp_agent/brain_v9/dashboard/dashboard_routes.py",
        "tmp_agent/brain_v9/dashboard/static/index.html",
        "tmp_agent/brain_v9/dashboard/static/app.js",
        "tmp_agent/brain_v9/dashboard/static/styles.css",
    ]:
        assert (ROOT / path).exists()
    routes = read("tmp_agent/brain_v9/dashboard/dashboard_routes.py")
    assert '@router.get("/status")' in routes
    assert '@router.post("/chat")' in routes
    assert "provider_selected" in routes
    assert "fallback_used" in routes
    assert "no_cot_leak" in routes


def test_monitoring_outputs_and_alert_rules_exist():
    for path in [
        "tmp_agent/brain_v9/monitoring/health_monitor.py",
        "tmp_agent/brain_v9/monitoring/correction_queue.py",
        "tmp_agent/brain_v9/monitoring/alert_rules.py",
        "tmp_agent/brain_v9/monitoring/status_snapshot.py",
    ]:
        assert (ROOT / path).exists()
    assert (ROOT / "tmp_agent/runtime/brain_status.json").exists()
    assert (ROOT / "tmp_agent/runtime/autonomy_heartbeat.json").exists()
    assert (ROOT / "tmp_agent/runtime/autonomy_last_run.json").exists()
    assert (ROOT / "tmp_agent/runtime/memory_promotion_status.json").exists()
    assert (ROOT / "tmp_agent/runtime/dashboard_status.json").exists()


def test_no_trading_b8_or_strategy_in_runtime_sources_and_memory_blocks_trading():
    checked = [
        "tmp_agent/brain_v9/autonomy/persistent_supervisor.py",
        "tmp_agent/brain_v9/dashboard/dashboard_routes.py",
    ]
    for path in checked:
        text = read(path).lower()
        assert "place order" not in text
        assert "broker api" not in text
        assert "tmp_agent/strategies" not in text
        assert "b8/" not in text
    memory_writer = read("tmp_agent/brain_v9/memory/autonomous_memory_writer.py").lower()
    assert "place order" in memory_writer
    assert "broker api" in memory_writer
    assert "prohibited_patterns" in memory_writer


def test_roadmap_valid_and_ledger_exists():
    json.loads(read("ROADMAP_STATUS.json"))
    assert (ROOT / "docs/MIGRATION_CONTROL_LEDGER.md").exists()


def test_no_protected_paths_or_env_staged():
    import subprocess
    staged = subprocess.check_output(["git", "diff", "--cached", "--name-status"], cwd=ROOT, text=True)
    for token in [".env", "trading/", "B8/", "tmp_agent/strategies"]:
        assert token not in staged
