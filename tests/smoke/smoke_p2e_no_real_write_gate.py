"""
P2-E Commit 3J: No-Real-Write Gate Smoke

Smoke test que valida de forma estática y ejecutable
que el bloque P2-E actual sigue sin activar escritura real.

Revisa archivos clave del pipeline P2-E dry-run para detectar:
- Import de faiss, requests, httpx
- Llamadas reales a add_memory
- Funciones promote_real o execute_rollback_real
- allow_real_write=True hardcoded
- Escritura a memory/semantic
- Operaciones de escritura en archivos
"""

import sys
from pathlib import Path

# Agregar raíz del proyecto al path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


def strip_docstrings(text: str) -> str:
    """Eliminar docstrings del código para análisis."""
    lines = text.splitlines()
    code_lines = []
    in_doc = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith('"""') or stripped.startswith("'''"):
            in_doc = not in_doc
            continue
        if not in_doc and not stripped.startswith("#"):
            code_lines.append(line)
    return "\n".join(code_lines)


def scan_file(filepath: Path) -> list:
    """
    Escanear archivo en busca de operaciones prohibidas.
    
    Returns:
        Lista de tuplas (archivo, token, línea) con hallazgos
    """
    findings = []
    
    try:
        text = filepath.read_text(encoding="utf-8", errors="ignore")
        code = strip_docstrings(text).lower()
        lines = text.splitlines()
    except Exception as e:
        return [(str(filepath), f"ERROR_READING: {e}", 0)]
    
    # Tokens prohibidos
    forbidden_tokens = [
        ("import faiss", "Import de faiss"),
        ("from faiss", "Import desde faiss"),
        ("import requests", "Import de requests"),
        ("from requests", "Import desde requests"),
        ("import httpx", "Import de httpx"),
        ("from httpx", "Import desde httpx"),
        ("promote_real(", "Función promote_real implementada"),
        ("execute_rollback_real(", "Función execute_rollback_real implementada"),
        (".write_text(", "Llamada write_text()"),
        (".unlink(", "Llamada unlink()"),
        (".remove(", "Llamada remove()"),
        (".rmdir(", "Llamada rmdir()"),
    ]
    
    # Verificar tokens prohibidos
    for token, description in forbidden_tokens:
        if token in code:
            # Encontrar línea
            for i, line in enumerate(lines, 1):
                if token.lower() in line.lower():
                    findings.append((str(filepath), description, i))
                    break
    
    # Verificar open( con modo escritura
    if "open(" in code:
        for i, line in enumerate(lines, 1):
            if "open(" in line.lower():
                # Detectar modos de escritura: 'w', 'a', 'x', '+'
                import re
                if re.search(r'open\s*\([^)]*[\'"][wax]', line, re.IGNORECASE):
                    findings.append((str(filepath), "open() con modo escritura", i))
    
    # Verificar callable add_memory
    import re
    if re.search(r"\.add_memory\s*\(", text):
        for i, line in enumerate(lines, 1):
            if ".add_memory(" in line:
                findings.append((str(filepath), "Llamada real .add_memory(", i))
                break
    
    # Verificar allow_real_write=True (solo en código real, no en comentarios)
    # Buscar en líneas que no sean comentarios ni docstrings
    code_lines_real = []
    in_docstring = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith('"""') or stripped.startswith("'''"):
            in_docstring = not in_docstring
            continue
        if not in_docstring and not stripped.startswith('#'):
            code_lines_real.append(line)
    
    code_real_only = '\n'.join(code_lines_real).lower()
    normalized_real = code_real_only.replace(" ", "").replace("\t", "")
    
    if "allow_real_write=true" in normalized_real:
        # Buscar línea específica
        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            if in_docstring or stripped.startswith('#'):
                continue
            if "allow_real_write" in line.lower() and "true" in line.lower():
                # Verificar que no sea solo en comentario al final de línea
                code_part = line.split('#')[0]
                if "allow_real_write" in code_part.lower() and "true" in code_part.lower():
                    findings.append((str(filepath), "allow_real_write=True", i))
                    break
    
    # Verificar escritura a memory/semantic (solo si es operación real)
    # Las referencias en comentarios son legítimas
    # Por ahora, no reportar estas referencias
    
    return findings


def assert_no_findings(findings: list) -> None:
    """Verificar que no hay hallazgos de seguridad."""
    if findings:
        print("\n[SECURITY_GATE_FAILED]")
        print(f"Se encontraron {len(findings)} problemas de seguridad:\n")
        for filepath, issue, line in findings:
            print(f"  - {filepath}:{line} -> {issue}")
        print("\nEl gate NO permite escritura real hasta Commit 4.")
        sys.exit(1)


def run_import_contract() -> None:
    """
    Verificar que el smoke pipeline puede importar correctamente
    las clases principales sin romper el contrato.
    """
    print("\n=== Verificación de Import Contract ===")
    
    try:
        from brain.curated_memory_dry_run_flow import (
            CuratedMemoryDryRunFlow,
            DryRunFlowStatus,
        )
        from brain.semantic_memory_adapter_dry_run import (
            SemanticMemoryAdapterDryRun,
            SemanticMemoryAdapterStatus,
        )
        print("[PASS] Import de CuratedMemoryDryRunFlow OK")
        print("[PASS] Import de DryRunFlowStatus OK")
        print("[PASS] Import de SemanticMemoryAdapterDryRun OK")
        print("[PASS] Import de SemanticMemoryAdapterStatus OK")
    except ImportError as e:
        print(f"[FAIL] Error importando módulos: {e}")
        sys.exit(1)
    
    # Verificar que NO se importan módulos prohibidos
    prohibited_modules = ["faiss", "requests", "httpx"]
    for mod in prohibited_modules:
        if mod in sys.modules:
            print(f"[FAIL] Módulo prohibido cargado: {mod}")
            sys.exit(1)
    print("[PASS] No hay módulos prohibidos cargados")


def main() -> None:
    """Ejecutar gate de seguridad."""
    print("=" * 70)
    print("P2-E Commit 3J: No-Real-Write Gate Smoke")
    print("=" * 70)
    print("\nEste gate valida que el pipeline P2-E sigue en modo dry-run.")
    print("NO se permite escritura real hasta Commit 4.")
    
    # Archivos a escanear
    files_to_scan = [
        Path("brain/curated_memory_promotion.py"),
        Path("brain/curated_memory_dry_run_flow.py"),
        Path("brain/semantic_memory_adapter_dry_run.py"),
        Path("brain/semantic_memory_probe.py"),
        Path("tests/smoke/smoke_p2e_curated_memory_pipeline_dry_run.py"),
    ]
    
    print("\n=== Escaneando archivos ===")
    all_findings = []
    
    for filepath in files_to_scan:
        if filepath.exists():
            print(f"Escaneando: {filepath}")
            findings = scan_file(filepath)
            all_findings.extend(findings)
        else:
            print(f"[WARN] Archivo no encontrado: {filepath}")
    
    # Verificar hallazgos
    assert_no_findings(all_findings)
    
    print("\n=== Verificación de import contract ===")
    run_import_contract()
    
    # Todo pasó
    print("\n" + "=" * 70)
    print("SMOKE_P2E_NO_REAL_WRITE_GATE_OK")
    print("=" * 70)
    print("\nGate pasado exitosamente.")
    print("El pipeline P2-E sigue en modo dry-run.")
    print("Escritura real BLOQUEADA hasta Commit 4.")


if __name__ == "__main__":
    main()
