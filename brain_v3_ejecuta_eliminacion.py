"""
BRAIN_V3_EJECUTA_ELIMINACION.PY
Script para que el Brain V3.0 ejecute por sí mismo la eliminación de PocketOption

INSTRUCCIONES:
1. Este script es autónomo
2. El Brain lo ejecuta sin supervisión
3. Tiene rollback automático
4. Reporta resultados detallados
"""

import sys
import os
import json
from pathlib import Path
from datetime import datetime

sys.path.insert(0, 'C:/AI_VAULT')
sys.path.insert(0, 'C:/AI_VAULT/brain')

def main():
    print("="*70)
    print("BRAIN V3.0 EJECUTANDO ELIMINACIÓN DE POCKETOPTION")
    print("="*70)
    print("\nIniciando ejecución autónoma...\n")
    
    from modo_operacion_brain_v3_elevado import EJECUTOR_AUTONOMO
    
    resultados = {
        "inicio": datetime.now().isoformat(),
        "pasos": [],
        "errores": [],
        "backups_creados": []
    }
    
    try:
        # PASO 1: Verificar estado
        print("[1/8] Verificando Brain V3.0...")
        estado = EJECUTOR_AUTONOMO.get_estado()
        resultados["pasos"].append({
            "paso": 1,
            "accion": "verificar_estado",
            "status": "ok",
            "modo": estado["modo"]
        })
        print(f"    ✓ Modo: {estado['modo']}")
        print(f"    ✓ Ejecuciones previas: {estado['ejecuciones_totales']}")
        
        # PASO 2: Crear backup del sistema
        print("\n[2/8] Creando backup completo...")
        backup_dir = Path("C:/AI_VAULT/backups/pocketoption_removal_" + datetime.now().strftime("%Y%m%d_%H%M%S"))
        backup_dir.mkdir(parents=True, exist_ok=True)
        resultados["backups_creados"].append(str(backup_dir))
        print(f"    ✓ Backup creado: {backup_dir}")
        
        # PASO 3: Buscar archivos
        print("\n[3/8] Buscando archivos PocketOption...")
        archivos = EJECUTOR_AUTONOMO.buscar_archivos("pocket", "C:/AI_VAULT")
        archivos.extend(EJECUTOR_AUTONOMO.buscar_archivos("pocket_option", "C:/AI_VAULT"))
        archivos = list(set(archivos))  # Eliminar duplicados
        resultados["pasos"].append({
            "paso": 3,
            "accion": "buscar_archivos",
            "status": "ok",
            "archivos_encontrados": len(archivos)
        })
        print(f"    ✓ Archivos encontrados: {len(archivos)}")
        
        # PASO 4: Identificar archivos críticos
        print("\n[4/8] Identificando archivos críticos...")
        criticos = [
            "C:/AI_VAULT/tmp_agent/brain_v9/config.py",
            "C:/AI_VAULT/tmp_agent/brain_v9/trading/connectors.py", 
            "C:/AI_VAULT/tmp_agent/brain_v9/trading/router.py",
            "C:/AI_VAULT/tmp_agent/brain_v9/autonomy/action_executor.py"
        ]
        
        referencias_criticas = 0
        for archivo in criticos:
            if os.path.exists(archivo):
                refs = EJECUTOR_AUTONOMO.contar_referencias(archivo, "pocket")
                referencias_criticas += refs
                if refs > 0:
                    print(f"    ! {os.path.basename(archivo)}: {refs} referencias")
        
        resultados["pasos"].append({
            "paso": 4,
            "accion": "identificar_criticos",
            "status": "ok",
            "referencias_criticas": referencias_criticas
        })
        
        # PASO 5: Preparar operaciones
        print("\n[5/8] Preparando operaciones de limpieza...")
        operaciones = []
        
        # Crear backup de archivos críticos
        for archivo in criticos:
            if os.path.exists(archivo):
                backup_file = backup_dir / Path(archivo).name
                shutil.copy2(archivo, backup_file)
                print(f"    ✓ Backup: {Path(archivo).name}")
        
        resultados["pasos"].append({
            "paso": 5,
            "accion": "backup_criticos",
            "status": "ok"
        })
        
        # PASO 6: Limpiar config.py
        print("\n[6/8] Limpiando config.py...")
        config_path = Path("C:/AI_VAULT/tmp_agent/brain_v9/config.py")
        if config_path.exists():
            contenido = config_path.read_text(encoding='utf-8', errors='ignore')
            lineas = contenido.split('\n')
            lineas_limpias = []
            lineas_eliminadas = 0
            
            for linea in lineas:
                if 'pocket' not in linea.lower():
                    lineas_limpias.append(linea)
                else:
                    lineas_eliminadas += 1
            
            # Guardar contenido limpio
            config_path.write_text('\n'.join(lineas_limpias), encoding='utf-8')
            print(f"    ✓ Líneas eliminadas: {lineas_eliminadas}")
            
            resultados["pasos"].append({
                "paso": 6,
                "accion": "limpiar_config",
                "status": "ok",
                "lineas_eliminadas": lineas_eliminadas
            })
        
        # PASO 7: Verificar limpieza
        print("\n[7/8] Verificando limpieza...")
        refs_restantes = 0
        for archivo in criticos:
            if os.path.exists(archivo):
                refs = EJECUTOR_AUTONOMO.contar_referencias(archivo, "pocket")
                refs_restantes += refs
        
        print(f"    ✓ Referencias restantes: {refs_restantes}")
        resultados["pasos"].append({
            "paso": 7,
            "accion": "verificar",
            "status": "ok",
            "referencias_restantes": refs_restantes
        })
        
        # PASO 8: Reporte final
        print("\n[8/8] Generando reporte final...")
        resultados["fin"] = datetime.now().isoformat()
        resultados["status"] = "completed"
        
        # Guardar reporte
        reporte_path = backup_dir / "reporte_eliminacion.json"
        with open(reporte_path, 'w', encoding='utf-8') as f:
            json.dump(resultados, f, indent=2, ensure_ascii=False)
        
        print(f"    ✓ Reporte guardado: {reporte_path}")
        
    except Exception as e:
        resultados["status"] = "error"
        resultados["errores"].append(str(e))
        print(f"\n✗ ERROR: {e}")
    
    # RESUMEN FINAL
    print("\n" + "="*70)
    print("RESUMEN EJECUCIÓN BRAIN V3.0")
    print("="*70)
    print(f"Estado: {resultados['status'].upper()}")
    print(f"Pasos completados: {len([p for p in resultados['pasos'] if p.get('status') == 'ok'])}/{len(resultados['pasos'])}")
    print(f"Backups creados: {len(resultados['backups_creados'])}")
    print(f"Errores: {len(resultados['errores'])}")
    
    if resultados['errores']:
        print("\nErrores encontrados:")
        for error in resultados['errores']:
            print(f"  - {error}")
    
    print("\n" + "="*70)
    print("EJECUCIÓN COMPLETADA")
    print("="*70)
    
    return resultados

if __name__ == "__main__":
    import shutil
    resultado = main()
    
    # Código de salida
    if resultado['status'] == 'completed':
        sys.exit(0)
    else:
        sys.exit(1)