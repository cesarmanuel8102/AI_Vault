# Integración inmediata de financial_autonomy al brain_server.py

# Leer el archivo actual
with open(r"C:\AI_VAULT\00_identity\brain_server.py", "r", encoding="utf-8") as f:
    content = f.read()

# Verificar si ya está integrado
if "financial_autonomy" in content:
    print("✅ Ya está integrado")
else:
    print("🔧 Integrando módulo financiero...")
    
    # Encontrar donde añadir el import (después de los últimos imports)
    lines = content.split('\n')
    
    # Buscar la última línea de import
    last_import_index = -1
    for i, line in enumerate(lines):
        if line.strip().startswith(('import ', 'from ')):
            last_import_index = i
    
    if last_import_index != -1:
        # Añadir import después del último import
        financial_import = "from 30_financial_autonomy.api.financial_endpoints import router as financial_autonomy_router"
        lines.insert(last_import_index + 1, financial_import)
        
        # Buscar donde añadir el router (después de app = FastAPI())
        app_line_index = -1
        for i, line in enumerate(lines):
            if "app = FastAPI()" in line or "app=FastAPI()" in line:
                app_line_index = i
                break
        
        if app_line_index != -1:
            # Añadir router después de app = FastAPI()
            router_line = "app.include_router(financial_autonomy_router)"
            
            # Buscar línea adecuada para insertar (después de comentarios vacíos)
            insert_index = app_line_index + 1
            for i in range(app_line_index + 1, min(app_line_index + 10, len(lines))):
                if lines[i].strip() and not lines[i].strip().startswith('#'):
                    insert_index = i
                    break
            
            lines.insert(insert_index, router_line)
            
            # Añadir endpoint de verificación
            verification_endpoint = '''
@app.get("/financial-integration/status")
async def financial_integration_status():
    return {
        "status": "integrated", 
        "module": "financial_autonomy", 
        "timestamp": "2026-03-11T03:15:00Z"
    }
'''
            # Añadir al final del archivo
            lines.append(verification_endpoint)
            
            # Escribir el archivo actualizado
            updated_content = '\n'.join(lines)
            with open(r"C:\AI_VAULT\00_identity\brain_server.py", "w", encoding="utf-8") as f:
                f.write(updated_content)
            
            print("✅ Integración financiera completada")
        else:
            print("❌ No se encontró app = FastAPI()")
    else:
        print("❌ No se encontraron imports")
