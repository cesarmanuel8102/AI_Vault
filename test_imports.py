# test_imports.py - Probar que los imports funcionan
try:
    from financial_autonomy.financial_autonomy_bridge import FinancialAutonomyBridge
    from financial_autonomy.trust_score_integration import FinancialTrustIntegration
    
    print("✅ Imports del módulo financiero funcionan")
    
    # Probar instanciación
    bridge = FinancialAutonomyBridge("C:\\AI_VAULT")
    trust = FinancialTrustIntegration("C:\\AI_VAULT")
    
    print("✅ Instanciación de clases funciona")
    print(f"Bridge: {bridge}")
    print(f"Trust: {trust}")
    
except Exception as e:
    print(f"❌ Error en imports: {e}")
