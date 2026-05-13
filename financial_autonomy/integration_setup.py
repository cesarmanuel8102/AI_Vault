# integration_setup.py
import sys
from pathlib import Path

def integrate_with_brain_server():
    \"\"\"Integrar módulo financiero con Brain Server existente\"\"\"
    
    # Buscar brain_server.py más reciente
    vault_path = Path(\"C:\\AI_VAULT\")
    brain_files = list(vault_path.rglob(\"brain_server*.py\"))
    
    if not brain_files:
        print(\"❌ No se encontró brain_server.py\")
        return False
    
    latest_brain = max(brain_files, key=lambda x: x.stat().st_mtime)
    print(f\"📄 Integrando con: {latest_brain.name}\")
    
    # Leer contenido actual
    content = latest_brain.read_text()
    
    # Verificar si ya está integrado
    if \"financial_autonomy\" in content:
        print(\"✅ Integración financiera ya existe\")
        return True
    
    # Añadir importación
    integration_import = \"\"\"\n\n# === FINANCIAL AUTONOMY INTEGRATION ===\nfrom financial_autonomy.api.financial_endpoints import router as financial_autonomy_router\n\"\"\"
    
    # Encontrar lugar para añadir import (después de otros imports)
    lines = content.split('\n')
    last_import_index = 0
    for i, line in enumerate(lines):
        if line.startswith('import') or line.startswith('from'):
            last_import_index = i
    
    # Insertar después del último import
    lines.insert(last_import_index + 1, integration_import.strip())
    
    # Buscar lugar para incluir router (en app.include_router)
    if \"app.include_router\" in content:
        # Añadir después de otros routers
        router_line = \"app.include_router(financial_autonomy_router)\"
        lines.append(f\"\n{router_line}\")
    else:
        # Crear sección de routers
        router_section = \"\"\"\n\n# Include routers\napp.include_router(financial_autonomy_router)\"\"\"
        lines.append(router_section)
    
    # Escribir archivo actualizado
    updated_content = '\n'.join(lines)
    latest_brain.write_text(updated_content)
    
    print(\"✅ Integración financiera añadida a Brain Server\")
    return True

if __name__ == \"__main__\":
    integrate_with_brain_server()
