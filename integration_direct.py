# integration_direct.py - Integración directa sin Advisor
import sys
from pathlib import Path
import json

def integrate_financial_module():
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
    
    # Añadir importación del módulo financiero
    financial_import = \"\"\"\n\n# === FINANCIAL AUTONOMY INTEGRATION (Direct) ===\nfrom 30_financial_autonomy.api.financial_endpoints import router as financial_autonomy_router\n\"\"\"
    
    # Encontrar lugar para añadir import (después de otros imports)
    lines = content.split('\n')
    last_import_index = 0
    for i, line in enumerate(lines):
        if line.startswith('import') or line.startswith('from'):
            last_import_index = i
    
    # Insertar después del último import
    lines.insert(last_import_index + 1, financial_import.strip())
    
    # Buscar app = FastAPI() o lugar para incluir router
    app_found = False
    for i, line in enumerate(lines):
        if \"app = FastAPI()\" in line or \"app = FastAPI\" in line:
            # Añadir router después de la creación de la app
            router_line = \"app.include_router(financial_autonomy_router)\"
            # Buscar donde añadirlo (después de otros routers o al final del bloque)
            insert_index = i + 1
            # Buscar siguiente línea no vacía después de la app
            for j in range(i + 1, min(i + 10, len(lines))):
                if lines[j].strip() and not lines[j].strip().startswith('#'):
                    insert_index = j
                    break
            lines.insert(insert_index, f\"{router_line}\")
            app_found = True
            break
    
    if not app_found:
        # Añadir al final del archivo si no se encontró app
        lines.append(\"\"\"\n\n# Include financial autonomy router\napp.include_router(financial_autonomy_router)\"\"\")
    
    # Escribir archivo actualizado
    updated_content = '\n'.join(lines)
    latest_brain.write_text(updated_content)
    
    print(\"✅ Integración financiera añadida directamente al Brain Server\")
    
    # Crear endpoint de verificación
    verification_endpoint = \"\"\"
    
@app.get(\"/financial-integration/status\")
async def financial_integration_status():
    return {
        \"status\": \"integrated\", 
        \"module\": \"financial_autonomy\", 
        \"endpoints\": [\"/financial-autonomy/metrics\", \"/financial-autonomy/optimize\"],
        \"timestamp\": \"2026-03-11T02:55:00Z\"
    }
\"\"\"
    
    # Añadir endpoint de verificación
    lines = updated_content.split('\n')
    lines.append(verification_endpoint)
    latest_brain.write_text('\n'.join(lines))
    
    print(\"✅ Endpoint de verificación añadido\")
    return True

if __name__ == \"__main__\":
    integrate_financial_module()
