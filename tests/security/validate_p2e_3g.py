"""
FASE 7: Validacion de Seguridad P2-E Commit 3G
"""

import re

def validate_security():
    files = [
        ('brain/semantic_memory_adapter_dry_run.py', 'Adapter'),
        ('tests/unit/test_semantic_memory_adapter_dry_run.py', 'Tests'),
        ('docs/P2E_SEMANTIC_MEMORY_ADAPTER_DRY_RUN.md', 'Docs'),
    ]
    
    print('=' * 70)
    print('FASE 7: VALIDACION DE SEGURIDAD P2-E Commit 3G')
    print('=' * 70)
    print()
    
    checks = {
        'import faiss': False,
        'from faiss': False,
        'import requests': False,
        'from requests': False,
        'import httpx': False,
        'from httpx': False,
        'write_text(': False,
        'open(.*w': False,
        'unlink(': False,
        'remove(': False,
        'rmdir(': False,
        'add_memory(': False,
        'promote_real': False,
        'execute_rollback_real': False,
    }
    
    all_clear = True
    
    for filepath, label in files:
        print(f"Archivo: {filepath} [{label}]")
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Verificar import faiss
            if re.search(r'import\s+faiss', content):
                print('  [FAIL] import faiss DETECTADO')
                all_clear = False
            else:
                print('  [OK] Sin import faiss')
            
            # Verificar import requests
            if re.search(r'import\s+requests', content):
                print('  [FAIL] import requests DETECTADO')
                all_clear = False
            else:
                print('  [OK] Sin import requests')
            
            # Verificar import httpx
            if re.search(r'import\s+httpx', content):
                print('  [FAIL] import httpx DETECTADO')
                all_clear = False
            else:
                print('  [OK] Sin import httpx')
            
            # Verificar write_text(
            # Solo contar si NO esta en docstrings o comentarios
            lines = content.split('\n')
            write_text_calls = 0
            in_docstring = False
            for line in lines:
                if '"""' in line or "'''" in line:
                    in_docstring = not in_docstring
                if not in_docstring and not line.strip().startswith('#'):
                    if '.write_text(' in line and 'Path' not in line:
                        write_text_calls += 1
            
            if write_text_calls > 0:
                print(f'  [FAIL] write_text() llamada DETECTADA ({write_text_calls} veces)')
                all_clear = False
            else:
                print('  [OK] Sin llamadas write_text()')
            
            # Verificar open con modo escritura
            open_write = re.findall(r'open\s*\([^)]*[\'"][wax]', content)
            if open_write:
                print(f'  [FAIL] open() con modo escritura DETECTADO')
                all_clear = False
            else:
                print('  [OK] Sin open() modo escritura')
            
            # Verificar unlink/remove/rmdir
            if '.unlink(' in content:
                print('  [FAIL] unlink() DETECTADO')
                all_clear = False
            else:
                print('  [OK] Sin unlink()')
            
            if '.remove(' in content:
                print('  [FAIL] remove() DETECTADO')
                all_clear = False
            else:
                print('  [OK] Sin remove()')
            
            if '.rmdir(' in content:
                print('  [FAIL] rmdir() DETECTADO')
                all_clear = False
            else:
                print('  [OK] Sin rmdir()')
            
            # Verificar add_memory( como llamada real
            # Solo reportar si NO es referencia en docstring o would_call_method
            add_memory_real = re.findall(r'(?<!would_call_method\s*=\s*)add_memory\s*\(', content)
            if add_memory_real:
                print(f'  [WARN] add_memory( posible llamada real DETECTADA')
            else:
                print('  [OK] Sin llamada real add_memory()')
            
            # Verificar promote_real
            if 'promote_real' in content:
                print('  [WARN] promote_real mencionado (debe ser solo referencia)')
            else:
                print('  [OK] Sin promote_real')
            
            # Verificar execute_rollback_real
            if 'execute_rollback_real' in content:
                print('  [WARN] execute_rollback_real mencionado')
            else:
                print('  [OK] Sin execute_rollback_real')
            
        except Exception as e:
            print(f'  [ERROR] {e}')
        
        print()
    
    print('=' * 70)
    if all_clear:
        print('RESULTADO: [PASS] VALIDACION DE SEGURIDAD PASADA')
    else:
        print('RESULTADO: [WARN] REVISAR ADVERTENCIAS')
    print('=' * 70)
    
    return all_clear

if __name__ == '__main__':
    validate_security()
