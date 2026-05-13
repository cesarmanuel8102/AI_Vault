# integrate_custom.py - Integración basada en estructura real
import re

def integrate_financial_custom():
    with open(r"C:\AI_VAULT\00_identity\brain_server.py", "r", encoding="utf-8") as f:
        content = f.read()
    
    # Verificar estructura
    lines = content.split('\n')
    
    print("Analizando estructura real del brain_server...")
    
    # Buscar dónde están los imports
    import_indices = []
    for i, line in enumerate(lines):
        if re.match(r'^(import|from)\s+', line.strip()):
            import_indices.append(i)
    
    print(f"Encontrados {len(import_indices)} imports")
    
    if import_indices:
        last_import = max(import_indices)
        print(f"Último import en línea {last_import}")
        
        # Añadir nuestro import después del último import
        financial_import = "from 30_financial_autonomy.api.financial_endpoints import router as financial_autonomy_router"
        lines.insert(last_import + 1, financial_import)
        
        # Buscar donde definir la app (puede ser cualquier variable)
        app_patterns = [
            r'app\s*=\s*FastAPI',
            r'application\s*=\s*FastAPI',
            r'FastAPI\(\)'
        ]
        
        app_line = -1
        for i, line in enumerate(lines):
            for pattern in app_patterns:
                if re.search(pattern, line):
                    app_line = i
                    print(f"Encontrado FastAPI en línea {i}: {line.strip()}")
                    break
            if app_line != -1:
                break
        
        if app_line != -1:
            # Buscar línea adecuada para insertar router (después de la creación de la app)
            insert_line = app_line + 1
            for i in range(app_line + 1, min(app_line + 20, len(lines))):
                if lines[i].strip() and not lines[i].strip().startswith('#'):
                    insert_line = i
                    break
            
            router_line = "app.include_router(financial_autonomy_router)"
            lines.insert(insert_line, router_line)
            print(f"Router insertado en línea {insert_line}")
            
            # Escribir archivo actualizado
            updated_content = '\n'.join(lines)
            with open(r"C:\AI_VAULT\00_identity\brain_server.py", "w", encoding="utf-8") as f:
                f.write(updated_content)
            
            print("✅ Integración personalizada completada")
            return True
        else:
            print("❌ No se encontró creación de FastAPI")
            return False
    else:
        print("❌ No se encontraron imports")
        return False

if __name__ == "__main__":
    integrate_financial_custom()
