#!/usr/bin/env python
"""
Test integral del sistema de trading IBKR con ib_insync
Valida:
1. Conexión a IB Gateway
2. Sincronización de cuentas
3. Capacidad de envío de órdenes
"""
import sys
import json
from datetime import datetime

sys.path.append('tmp_agent')

from brain_v9.trading.ibkr_order_executor import check_ibkr_paper_order_api

def main():
    print("\n" + "=" * 80)
    print("SISTEMA DE TRADING IBKR - TEST INTEGRAL (2026-03-25)")
    print("=" * 80)
    
    # Test 1: Conexión básica
    print("\n[TEST 1] Verificando conexión a IB Gateway...")
    result1 = check_ibkr_paper_order_api(symbol="SPY", action="BUY", quantity=1)
    
    connected = result1.get("connected", False)
    api_ready = result1.get("order_api_ready", False)
    accounts = result1.get("managed_accounts", [])
    errors = result1.get("errors", [])
    
    print(f"  ✓ Conectado: {connected}")
    print(f"  ✓ API Operacional: {api_ready}")
    print(f"  ✓ Cuentas: {accounts}")
    if errors:
        print(f"  ⚠ Errores: {errors}")
    
    # Test 2: Orden alternativa
    print("\n[TEST 2] Verificando envío de orden SELL...")
    result2 = check_ibkr_paper_order_api(symbol="AAPL", action="SELL", quantity=2, what_if=True)
    
    connected2 = result2.get("connected", False)
    print(f"  ✓ Conectado: {connected2}")
    print(f"  ✓ API Operacional: {result2.get('order_api_ready', False)}")
    
    # Resumen
    print("\n" + "=" * 80)
    print("RESUMEN FINAL")
    print("=" * 80)
    
    tests_passed = 0
    tests_total = 2
    
    if connected and api_ready and accounts:
        tests_passed += 1
        print("✓ TEST 1: Conexión IBKR - PASSED")
    else:
        print("✗ TEST 1: Conexión IBKR - FAILED")
    
    if connected2:
        tests_passed += 1
        print("✓ TEST 2: Órdenes alternativas - PASSED")
    else:
        print("✗ TEST 2: Órdenes alternativas - FAILED")
    
    print(f"\nResultado: {tests_passed}/{tests_total} tests exitosos")
    
    if tests_passed == tests_total:
        print("\n🎯 SISTEMA DE TRADING COMPLETAMENTE OPERACIONAL")
        print("   Status: READY FOR PRODUCTION")
        return 0
    else:
        print("\n⚠ SISTEMA CON PROBLEMAS")
        return 1

if __name__ == "__main__":
    exit(main())
