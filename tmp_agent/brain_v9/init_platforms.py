#!/usr/bin/env python3
"""
Brain V9 - Inicializador de Plataformas Separadas
Inicia el sistema de plataformas independientes con U scores separados
"""
import asyncio
import sys
from pathlib import Path

# Asegurar path
sys.path.insert(0, str(Path(__file__).parent))

from brain_v9.autonomy.platform_accumulators import get_multi_platform_accumulator
from brain_v9.trading.platform_manager import get_platform_manager

async def initialize_platforms():
    """Inicializa el sistema de plataformas separadas"""
    print("=" * 70)
    print("  BRAIN V9 - PLATFORMAS SEPARADAS")
    print("  Sistema de análisis independiente con U scores propios")
    print("=" * 70)
    print()
    
    # Inicializar Platform Manager
    print("[1/3] Inicializando Platform Manager...")
    platform_manager = get_platform_manager()
    
    # Verificar plataformas
    platforms = platform_manager.get_all_platforms_status()
    print(f"      ✓ {len(platforms)} plataformas configuradas:")
    for name in platforms.keys():
        print(f"        • {name}")
    print()
    
    # Inicializar Multi-Platform Accumulator
    print("[2/3] Inicializando acumuladores por plataforma...")
    accumulators = get_multi_platform_accumulator()
    
    status = accumulators.get_all_status()
    print(f"      ✓ {len(status)} acumuladores listos:")
    for name, data in status.items():
        print(f"        • {name}: {data.get('running', False)}")
    print()
    
    # Iniciar todos los acumuladores
    print("[3/3] Iniciando acumulación de muestras...")
    print("      Cada plataforma acumula independientemente:")
    print("      • PocketOption: Revisando cada 1 minuto")
    print("      • IBKR: Revisando cada 5 minutos")
    print("      • Internal: Revisando cada 2 minutos")
    print()
    
    print("=" * 70)
    print("  SISTEMA INICIADO")
    print("=" * 70)
    print()
    print("Endpoints disponibles:")
    print("  • /api/platforms/summary - Resumen de todas")
    print("  • /api/platforms/{name} - Detalle de una plataforma")
    print("  • /api/platforms/{name}/u-history - Historial de U")
    print("  • /api/platforms/{name}/signals-analysis - Análisis de señales")
    print("  • /api/platforms/compare - Comparación entre plataformas")
    print()
    print("Cada plataforma tiene:")
    print("  ✓ U score independiente")
    print("  ✓ Métricas propias (win rate, profit, drawdown)")
    print("  ✓ Acumulador de muestras separado")
    print("  ✓ Historial de trades aislado")
    print("  ✓ Análisis de señales específico")
    print()
    
    # Iniciar acumuladores
    await accumulators.start_all()

if __name__ == "__main__":
    try:
        asyncio.run(initialize_platforms())
    except KeyboardInterrupt:
        print("\n\nDeteniendo sistema de plataformas...")
        accumulators = get_multi_platform_accumulator()
        accumulators.stop_all()
        print("Sistema detenido.")
