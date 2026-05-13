#!/usr/bin/env python3
"""
Script para análisis completo de degradación del QC Live deployment
Utiliza el qc_live_analyzer.py existente del ecosistema AI_VAULT
"""

import sys
import os
sys.path.append(r'C:\AI_VAULT\brain_v9')

try:
    from trading.qc_live_analyzer import QCLiveDegradationAnalyzer
    from trading.qc_live_monitor import QCLiveMonitor
    import json
    from datetime import datetime, timedelta
    
    print("=== QC Live Degradation Analysis ===")
    print(f"Timestamp: {datetime.now().isoformat()}")
    print()
    
    # Inicializar el analizador
    analyzer = QCLiveDegradationAnalyzer()
    monitor = QCLiveMonitor()
    
    print("1. ESTADO ACTUAL DEL MONITOR")
    print("-" * 40)
    
    # Verificar si hay snapshots recientes
    snapshots_dir = r'C:\AI_VAULT\data\qc_live_snapshots'
    if os.path.exists(snapshots_dir):
        snapshots = [f for f in os.listdir(snapshots_dir) if f.endswith('.json')]
        print(f"Snapshots disponibles: {len(snapshots)}")
        if snapshots:
            latest = max(snapshots)
            print(f"Último snapshot: {latest}")
        else:
            print("⚠️  No hay snapshots disponibles")
    else:
        print("⚠️  Directorio de snapshots no existe")
    
    print()
    print("2. ANÁLISIS DE DEGRADACIÓN")
    print("-" * 40)
    
    # Ejecutar análisis de degradación
    try:
        degradation_report = analyzer.analyze_degradation(days_back=7)
        
        if degradation_report:
            print("✅ Análisis de degradación completado")
            print(json.dumps(degradation_report, indent=2, ensure_ascii=False))
        else:
            print("⚠️  No se pudo generar reporte de degradación")
            
    except Exception as e:
        print(f"❌ Error en análisis de degradación: {str(e)}")
    
    print()
    print("3. PATRONES DETECTADOS")
    print("-" * 40)
    
    try:
        patterns = analyzer.detect_patterns()
        if patterns:
            print("Patrones de degradación detectados:")
            for pattern in patterns:
                print(f"- {pattern}")
        else:
            print("No se detectaron patrones de degradación")
    except Exception as e:
        print(f"Error detectando patrones: {str(e)}")
    
    print()
    print("4. RECOMENDACIONES AUTO-AJUSTE")
    print("-" * 40)
    
    try:
        recommendations = analyzer.get_auto_adjustment_recommendations()
        if recommendations:
            print("Recomendaciones de auto-ajuste:")
            for rec in recommendations:
                print(f"- {rec}")
        else:
            print("No hay recomendaciones de ajuste en este momento")
    except Exception as e:
        print(f"Error obteniendo recomendaciones: {str(e)}")
    
    print()
    print("5. RESUMEN EJECUTIVO")
    print("-" * 40)
    
    try:
        summary = analyzer.get_executive_summary()
        if summary:
            print(summary)
        else:
            print("No se pudo generar resumen ejecutivo")
    except Exception as e:
        print(f"Error generando resumen: {str(e)}")
        
except ImportError as e:
    print(f"❌ Error importando módulos: {str(e)}")
    print("Verificando estructura del proyecto...")
    
    # Verificar archivos clave
    key_files = [
        r'C:\AI_VAULT\brain_v9\trading\qc_live_analyzer.py',
        r'C:\AI_VAULT\brain_v9\trading\qc_live_monitor.py'
    ]
    
    for file_path in key_files:
        if os.path.exists(file_path):
            print(f"✅ {file_path} existe")
        else:
            print(f"❌ {file_path} no encontrado")
            
except Exception as e:
    print(f"❌ Error inesperado: {str(e)}")
    import traceback
    traceback.print_exc()

print("\n=== Análisis completado ===")