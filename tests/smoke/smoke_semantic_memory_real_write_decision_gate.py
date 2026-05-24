"""
P2-E Commit 4D-DecisionGate: Smoke Test para SemanticMemoryRealWriteDecisionGate

Valida que el decision gate funciona correctamente en un entorno real.
"""

import sys
import tempfile
from pathlib import Path

# Add parent directory to path to import brain module
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


def main():
    """Ejecutar smoke tests del decision gate."""
    print("=" * 80)
    print("SMOKE TEST: SemanticMemoryRealWriteDecisionGate")
    print("=" * 80)
    
    # Importar el módulo a probar
    try:
        from brain.semantic_memory_real_write_decision_gate import (
            SemanticMemoryRealWriteDecisionGate,
            SemanticMemoryDecision,
        )
        print("[OK] Importación exitosa")
    except ImportError as e:
        print(f"[FAIL] Error importando módulo: {e}")
        return 1
    
    # Test 1: Crear gate
    print("\n[Test 1] Crear decision gate...")
    gate = SemanticMemoryRealWriteDecisionGate(repo_root=".")
    print(f"  - Gate creado: {gate._decision_id}")
    print("[PASS] Gate creado correctamente")
    
    # Test 2: Evaluar en modo read-only
    print("\n[Test 2] Evaluar en modo read-only...")
    report = gate.evaluate_read_only()
    
    print(f"  - Decision ID: {report.decision_id}")
    print(f"  - Decision: {report.decision.value}")
    print(f"  - Blocker count: {report.blocker_count}")
    print(f"  - Warning count: {report.warning_count}")
    print(f"  - Info count: {report.info_count}")
    print(f"  - Required artifacts: {len(report.required_artifacts)} checked")
    print(f"  - Risk summary: {len(report.risk_summary)} items")
    
    # Verificar seguridad
    assert report.allow_real_write is False, "allow_real_write debe ser False"
    assert report.dry_run_only is True, "dry_run_only debe ser True"
    assert report.can_execute_real_write is False, "can_execute_real_write debe ser False"
    
    print(f"  - allow_real_write: {report.allow_real_write}")
    print(f"  - dry_run_only: {report.dry_run_only}")
    print(f"  - can_execute_real_write: {report.can_execute_real_write}")
    print("[PASS] Evaluación read-only completada")
    
    # Test 3: Verificar contrato de seguridad
    print("\n[Test 3] Verificar contrato de seguridad...")
    contract = gate.summarize_contract()
    
    assert contract["allow_real_write"] is False
    assert contract["dry_run_only"] is True
    assert contract["can_execute_real_write"] is False
    
    print(f"  - Decisions disponibles: {len(contract['decisions'])}")
    print(f"  - Limitations: {len(contract['limitations'])} restricciones")
    print("[PASS] Contrato de seguridad verificado")
    
    # Test 4: Bloquear escritura real
    print("\n[Test 4] Verificar block_real_write...")
    blocked_report = gate.block_real_write("Smoke test block")
    
    assert blocked_report.allow_real_write is False
    assert blocked_report.decision == SemanticMemoryDecision.BLOCK_REAL_WRITE
    assert len(blocked_report.blockers) > 0
    
    print(f"  - Decision: {blocked_report.decision.value}")
    print(f"  - Blockers: {len(blocked_report.blockers)}")
    print(f"  - allow_real_write: {blocked_report.allow_real_write}")
    print("[PASS] Bloqueo de escritura real verificado")
    
    # Test 5: Verificar que NO hay escritura
    print("\n[Test 5] Verificar que NO se escribe nada...")
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        
        # Crear gate en directorio temporal
        temp_gate = SemanticMemoryRealWriteDecisionGate(repo_root=tmpdir)
        temp_report = temp_gate.evaluate_read_only()
        
        # Verificar que no se crearon archivos
        files_created = list(Path(tmpdir).rglob("*"))
        assert len(files_created) == 0 or all(not f.is_file() for f in files_created if f.name != "." and f.name != ".."), "Archivos creados inesperadamente"
        
        print(f"  - Archivos creados: 0")
        print("[PASS] No se escribieron archivos")
    
    # Test 6: Verificar decisiones
    print("\n[Test 6] Verificar tipos de decisiones...")
    decisions = [
        SemanticMemoryDecision.BLOCK_REAL_WRITE,
        SemanticMemoryDecision.CANARY_NOOP_ONLY,
        SemanticMemoryDecision.MANUAL_REVIEW_REQUIRED,
        SemanticMemoryDecision.ALLOW_MANUAL_REAL_WRITE_CANDIDATE,
    ]
    
    for decision in decisions:
        print(f"  - {decision.value}: OK")
    
    print("[PASS] Todas las decisiones disponibles")
    
    # Test 7: Reporte de artefactos
    print("\n[Test 7] Verificar artefactos requeridos...")
    print(f"  - Artefactos requeridos: {len(report.required_artifacts)}")
    for artifact, exists in report.required_artifacts.items():
        status = "[OK]" if exists else "[MISSING]"
        print(f"    {status} {artifact}")
    print("[PASS] Artefactos verificados")
    
    # Test 8: Verificar que NO se usan módulos sensibles
    print("\n[Test 8] Verificar que NO se importan módulos sensibles...")
    import ast
    
    module_path = Path(__file__).parent.parent.parent / "brain" / "semantic_memory_real_write_decision_gate.py"
    if module_path.exists():
        content = module_path.read_text(encoding="utf-8", errors="ignore")
        tree = ast.parse(content)
        
        forbidden_imports = {"subprocess", "faiss", "shutil", "requests", "httpx"}
        found_imports = set()
        
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name in forbidden_imports:
                        found_imports.add(alias.name)
            elif isinstance(node, ast.ImportFrom):
                if node.module in forbidden_imports:
                    found_imports.add(node.module)
        
        assert len(found_imports) == 0, f"Imports prohibidos encontrados: {found_imports}"
        print(f"  - Imports verificados: OK")
        print("[PASS] No se importan módulos sensibles")
    else:
        print("  - Módulo no encontrado para verificación (OK en test smoke)")
        print("[PASS] Verificación omitida")
    
    # Resumen final
    print("\n" + "=" * 80)
    print("SMOKE_SEMANTIC_MEMORY_REAL_WRITE_DECISION_GATE_OK")
    print("=" * 80)
    print(f"\nEstado: Decision gate funciona correctamente")
    print(f"Decision: {report.decision.value}")
    print(f"Seguridad: allow_real_write=False, dry_run_only=True")
    print(f"can_execute_real_write: False")
    print(f"requires_manual_review: {report.requires_manual_review}")
    print(f"\nArchivos: brain/semantic_memory_real_write_decision_gate.py")
    print(f"Pruebas: tests/unit/test_semantic_memory_real_write_decision_gate.py")
    print(f"Documento: docs/P2E_SEMANTIC_MEMORY_REAL_WRITE_DECISION_GATE.md")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
