"""
P2-E Commit 4A: Smoke Test del Memory Semantic Backup Contract

Smoke test que valida el contrato de backup/snapshot
usando directorios temporales (NO memory/semantic real).

Valida:
1. Crear snapshot sobre directorio temporal
2. Verificar snapshot
3. Simular backup (sin escribir)
4. Simular restore (sin modificar)
5. Bloquear restore real
6. dry_run_only=True, allow_real_write=False
"""

import sys
from pathlib import Path

# Agregar raíz del proyecto al path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from brain.memory_semantic_backup import (
    MemorySemanticBackupContract,
    MemorySemanticBackupStatus,
)


def assert_true(condition, message):
    """Assert con mensaje claro."""
    if not condition:
        print(f"[FAIL] {message}")
        sys.exit(1)
    print(f"[PASS] {message}")


def run_smoke_test():
    """Ejecutar smoke test completo del backup contract."""
    print("=" * 70)
    print("P2-E Commit 4A: Smoke Test Memory Semantic Backup Contract")
    print("=" * 70)
    print("\nEste smoke usa directorios temporales (NO memory/semantic real)")
    
    # Crear directorio temporal
    import tempfile
    import os
    
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        
        # 1. Crear archivos temporales
        print("\n=== Paso 1: Crear archivos temporales ===")
        (tmp_path / "file1.txt").write_text("Content of file 1")
        (tmp_path / "file2.txt").write_text("Content of file 2")
        (tmp_path / "subdir").mkdir()
        (tmp_path / "subdir" / "file3.txt").write_text("Content of file 3")
        print("[INFO] Creados 3 archivos temporales")
        
        # 2. Crear contract y snapshot
        print("\n=== Paso 2: Crear snapshot ===")
        contract = MemorySemanticBackupContract(
            source_root=tmp_path,
            backup_root=tmp_path / "backup",  # Solo referencia
        )
        
        snapshot = contract.create_snapshot()
        
        assert_true(
            snapshot.snapshot_id.startswith("snapshot_"),
            "Snapshot tiene ID válido"
        )
        assert_true(
            snapshot.file_count == 3,
            f"Snapshot contiene 3 archivos (encontrados: {snapshot.file_count})"
        )
        assert_true(
            snapshot.total_bytes > 0,
            f"Snapshot tiene bytes totales > 0 ({snapshot.total_bytes})"
        )
        assert_true(
            len(snapshot.fingerprints) == 3,
            "Snapshot tiene 3 fingerprints"
        )
        assert_true(
            snapshot.dry_run_only is True,
            "snapshot.dry_run_only es True"
        )
        assert_true(
            snapshot.allow_real_write is False,
            "snapshot.allow_real_write es False"
        )
        print(f"[INFO] Snapshot ID: {snapshot.snapshot_id}")
        print(f"[INFO] File count: {snapshot.file_count}")
        print(f"[INFO] Total bytes: {snapshot.total_bytes}")
        
        # 3. Verificar snapshot
        print("\n=== Paso 3: Verificar snapshot ===")
        result_verify = contract.verify_snapshot(snapshot)
        
        assert_true(
            result_verify.status == MemorySemanticBackupStatus.VERIFIED,
            f"Snapshot verificado exitosamente (status: {result_verify.status})"
        )
        assert_true(
            len(result_verify.validation_errors) == 0,
            "Sin errores de validación"
        )
        assert_true(
            result_verify.dry_run_only is True,
            "verify result dry_run_only es True"
        )
        assert_true(
            result_verify.allow_real_write is False,
            "verify result allow_real_write es False"
        )
        print(f"[INFO] Verification ID: {result_verify.backup_id}")
        
        # 4. Simular backup
        print("\n=== Paso 4: Simular backup ===")
        result_backup = contract.simulate_backup(snapshot)
        
        assert_true(
            result_backup.status == MemorySemanticBackupStatus.CREATED,
            f"Backup simulado creado (status: {result_backup.status})"
        )
        assert_true(
            "SIMULATED" in result_backup.warnings[0],
            "Backup es simulación (no real)"
        )
        assert_true(
            result_backup.dry_run_only is True,
            "backup dry_run_only es True"
        )
        assert_true(
            result_backup.allow_real_write is False,
            "backup allow_real_write es False"
        )
        assert_true(
            result_backup.metadata.get("actual_write") is False,
            "Backup NO escribió archivos reales"
        )
        print(f"[INFO] Backup ID: {result_backup.backup_id}")
        print(f"[INFO] Warnings: {result_backup.warnings}")
        
        # 5. Simular restore
        print("\n=== Paso 5: Simular restore ===")
        
        # Modificar un archivo para simular necesidad de restore
        original_content = (tmp_path / "file1.txt").read_text()
        (tmp_path / "file1.txt").write_text("MODIFIED")
        
        result_restore = contract.simulate_restore(snapshot)
        
        assert_true(
            result_restore.status == MemorySemanticBackupStatus.RESTORE_SIMULATED,
            f"Restore simulado ejecutado (status: {result_restore.status})"
        )
        assert_true(
            "SIMULATED" in result_restore.warnings[0],
            "Restore es simulación (no real)"
        )
        assert_true(
            result_restore.dry_run_only is True,
            "restore dry_run_only es True"
        )
        assert_true(
            result_restore.allow_real_write is False,
            "restore allow_real_write es False"
        )
        assert_true(
            result_restore.metadata.get("actual_write") is False,
            "Restore NO modificó archivos reales"
        )
        
        # Verificar que archivo sigue modificado (no fue restaurado realmente)
        current_content = (tmp_path / "file1.txt").read_text()
        assert_true(
            current_content == "MODIFIED",
            "Archivo sigue modificado (no restore real)"
        )
        print(f"[INFO] Restore ID: {result_restore.backup_id}")
        print(f"[INFO] Warnings: {result_restore.warnings}")
        
        # 6. Bloquear restore real
        print("\n=== Paso 6: Bloquear restore real ===")
        result_block = contract.block_real_restore("Security gate P2-E Commit 4A")
        
        assert_true(
            result_block.status == MemorySemanticBackupStatus.REAL_RESTORE_BLOCKED,
            f"Restore real bloqueado (status: {result_block.status})"
        )
        assert_true(
            result_block.dry_run_only is True,
            "block dry_run_only es True"
        )
        assert_true(
            result_block.allow_real_write is False,
            "block allow_real_write es False"
        )
        assert_true(
            "REAL_RESTORE_BLOCKED" in result_block.warnings[0],
            "Warning indica bloqueo"
        )
        print(f"[INFO] Block ID: {result_block.backup_id}")
        print(f"[INFO] Status: {result_block.status}")
        
        # 7. Verificar contrato
        print("\n=== Paso 7: Resumen del contrato ===")
        summary = contract.summarize_contract()
        
        assert_true(
            summary["contract_version"] == "P2-E-Commit-4A",
            "Contract version correcta"
        )
        assert_true(
            summary["dry_run_only"] is True,
            "Contract dry_run_only es True"
        )
        assert_true(
            summary["allow_real_write"] is False,
            "Contract allow_real_write es False"
        )
        assert_true(
            "create_snapshot" in summary["capabilities"],
            "Contract soporta create_snapshot"
        )
        assert_true(
            "NO real backup writes" in summary["limitations"],
            "Contract tiene limitación de no-escritura"
        )
        print(f"[INFO] Capabilities: {summary['capabilities']}")
        print(f"[INFO] Limitations: {summary['limitations']}")
    
    # Resultado final
    print("\n" + "=" * 70)
    print("SMOKE_MEMORY_SEMANTIC_BACKUP_CONTRACT_OK")
    print("=" * 70)
    print("\nBackup contract validado exitosamente.")
    print("NO se escribieron backups reales.")
    print("NO se modificó memory/semantic.")
    print("Escritura real BLOQUEADA hasta Commit 4D.")


if __name__ == "__main__":
    try:
        run_smoke_test()
    except Exception as e:
        print(f"\n[ERROR] Smoke test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
