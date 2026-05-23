"""
P2-E Commit 3I: Smoke Test del Pipeline P2-E Dry-Run

Smoke test del pipeline completo P2-E dry-run validando:
1. Pipeline aprobado ejecuta semantic adapter dry-run
2. Pipeline rechazado no ejecuta semantic adapter
3. Bloqueo explícito de escritura real
4. Validaciones de seguridad

REGLAS DURAS:
- NO importar faiss
- NO importar requests/httpx
- NO llamar runtime
- NO escribir memory/semantic
- NO usar tmp_agent/reports
- SÓLO dry-run
"""

import sys
from pathlib import Path

# Agregar raíz del proyecto al path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from brain.curated_memory_dry_run_flow import (
    CuratedMemoryDryRunFlow,
    DryRunFlowStatus,
)
from brain.semantic_memory_adapter_dry_run import (
    SemanticMemoryAdapterDryRun,
    SemanticMemoryAdapterStatus,
)


def assert_true(condition: bool, message: str) -> None:
    """Assert con mensaje claro."""
    if not condition:
        print(f"[FAIL] {message}")
        sys.exit(1)
    print(f"[PASS] {message}")


def run_approved_pipeline_smoke() -> None:
    """
    Smoke test del pipeline aprobado.
    
    Valida que el pipeline completo ejecuta correctamente
    con approve=True y que se integra con SemanticMemoryAdapterDryRun.
    """
    print("\n=== Approved Pipeline Smoke ===")
    
    # Crear adapter y flow
    adapter = SemanticMemoryAdapterDryRun()
    flow = CuratedMemoryDryRunFlow(semantic_adapter=adapter)
    
    # Ejecutar pipeline aprobado
    result = flow.run_approval_flow(
        record_id="smoke_p2e_record_approved",
        content_hash="smoke_hash_approved_001",
        source="smoke_p2e",
        validation_score=0.95,
        actor="smoke_runner",
        approve=True,
    )
    
    # Validar resultado
    assert_true(
        result.status == DryRunFlowStatus.COMPLETED_DRY_RUN,
        f"Expected COMPLETED_DRY_RUN, got {result.status}"
    )
    assert_true(
        result.dry_run_only is True,
        "dry_run_only must be True"
    )
    assert_true(
        result.allow_real_write is False,
        "allow_real_write must be False"
    )
    assert_true(
        result.approval_request_id is not None,
        "approval_request_id must not be None"
    )
    assert_true(
        result.approval_decision_id is not None,
        "approval_decision_id must not be None"
    )
    assert_true(
        len(result.audit_entry_ids) > 0,
        "audit_entry_ids must not be empty"
    )
    assert_true(
        len(result.observability_event_ids) > 0,
        "observability_event_ids must not be empty"
    )
    assert_true(
        result.semantic_adapter_run_id is not None,
        "semantic_adapter_run_id must not be None"
    )
    assert_true(
        result.semantic_adapter_status == "DRY_RUN_READY",
        f"Expected DRY_RUN_READY, got {result.semantic_adapter_status}"
    )
    assert_true(
        result.metadata.get("semantic_adapter_dry_run") is True,
        "semantic_adapter_dry_run must be True in metadata"
    )
    assert_true(
        result.metadata.get("semantic_adapter_would_call_method") == "add_memory",
        f"Expected 'add_memory', got {result.metadata.get('semantic_adapter_would_call_method')}"
    )
    
    # Validar que NO hay escritura real
    assert_true(
        "semantic_adapter_dry_run" in result.metadata,
        "metadata must contain semantic_adapter_dry_run flag"
    )
    assert_true(
        result.metadata.get("semantic_adapter_would_call_method") == "add_memory",
        "would_call_method should be 'add_memory' (text only, not actual call)"
    )
    
    print("[INFO] Approved pipeline smoke completed successfully")
    print(f"[INFO] Flow ID: {result.flow_id}")
    print(f"[INFO] Semantic Adapter Run ID: {result.semantic_adapter_run_id}")
    print(f"[INFO] Semantic Adapter Status: {result.semantic_adapter_status}")


def run_rejected_pipeline_smoke() -> None:
    """
    Smoke test del pipeline rechazado.
    
    Valida que el pipeline con approve=False:
    - NO ejecuta semantic adapter
    - Marca correctamente como REJECTED_DRY_RUN
    """
    print("\n=== Rejected Pipeline Smoke ===")
    
    # Crear adapter y flow
    adapter = SemanticMemoryAdapterDryRun()
    flow = CuratedMemoryDryRunFlow(semantic_adapter=adapter)
    
    # Ejecutar pipeline rechazado
    result = flow.run_approval_flow(
        record_id="smoke_p2e_record_rejected",
        content_hash="smoke_hash_rejected_001",
        source="smoke_p2e",
        validation_score=0.95,
        actor="smoke_runner",
        approve=False,
    )
    
    # Validar resultado
    assert_true(
        result.status == DryRunFlowStatus.REJECTED_DRY_RUN,
        f"Expected REJECTED_DRY_RUN, got {result.status}"
    )
    assert_true(
        result.dry_run_only is True,
        "dry_run_only must be True"
    )
    assert_true(
        result.allow_real_write is False,
        "allow_real_write must be False"
    )
    assert_true(
        result.semantic_adapter_run_id is None,
        "semantic_adapter_run_id must be None for rejected flow"
    )
    assert_true(
        result.semantic_adapter_status is None,
        "semantic_adapter_status must be None for rejected flow"
    )
    assert_true(
        result.metadata.get("semantic_adapter_skipped") is True,
        "semantic_adapter_skipped must be True in metadata"
    )
    
    print("[INFO] Rejected pipeline smoke completed successfully")
    print(f"[INFO] Flow ID: {result.flow_id}")
    print("[INFO] Semantic Adapter: SKIPPED (correct for rejected flow)")


def run_adapter_block_smoke() -> None:
    """
    Smoke test de bloqueo explícito de escritura real.
    
    Valida que block_real_write funciona correctamente
    y bloquea escritura real.
    """
    print("\n=== Adapter Block Real Write Smoke ===")
    
    # Crear adapter
    adapter = SemanticMemoryAdapterDryRun()
    
    # Crear payload
    payload = adapter.build_payload(
        record_id="smoke_p2e_block_test",
        text="Test content for block smoke",
        source="smoke_p2e",
        content_hash="smoke_hash_block_001",
        metadata={"test": "block"},
        validation_score=0.95,
    )
    
    # Bloquear escritura real
    result = adapter.block_real_write(
        payload=payload,
        reason="Smoke test block real write",
    )
    
    # Validar resultado
    assert_true(
        result.status == SemanticMemoryAdapterStatus.REAL_WRITE_BLOCKED,
        f"Expected REAL_WRITE_BLOCKED, got {result.status}"
    )
    assert_true(
        result.dry_run_only is True,
        "dry_run_only must be True"
    )
    assert_true(
        result.allow_real_write is False,
        "allow_real_write must be False"
    )
    assert_true(
        len(result.warnings) > 0,
        "warnings must not be empty"
    )
    assert_true(
        "WRITE_BLOCKED" in result.warnings[0] or "blocked" in result.warnings[0].lower(),
        "warning should indicate blocked write"
    )
    
    print("[INFO] Adapter block smoke completed successfully")
    print(f"[INFO] Adapter Run ID: {result.adapter_run_id}")
    print(f"[INFO] Status: {result.status}")
    print(f"[INFO] Warning: {result.warnings[0]}")


def run_main() -> None:
    """
    Ejecutar todos los smoke tests.
    """
    print("=" * 70)
    print("P2-E Commit 3I: Smoke Test del Pipeline Dry-Run")
    print("=" * 70)
    
    try:
        # Ejecutar casos de smoke
        run_approved_pipeline_smoke()
        run_rejected_pipeline_smoke()
        run_adapter_block_smoke()
        
        # Todo pasó
        print("\n" + "=" * 70)
        print("SMOKE_P2E_CURATED_MEMORY_PIPELINE_DRY_RUN_OK")
        print("=" * 70)
        
    except Exception as e:
        print(f"\n[ERROR] Smoke test failed with exception: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    run_main()
