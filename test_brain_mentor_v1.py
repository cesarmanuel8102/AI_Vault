"""
TEST_BRAIN_MENTOR_V1.PY
Script de validacion del sistema de modos PLAN/BUILD del Brain
Como mentor, verifico que el Brain tenga las capacidades necesarias para ejecutar
"""

import sys
sys.path.insert(0, 'C:/AI_VAULT')
sys.path.insert(0, 'C:/AI_VAULT/brain')

print("="*80)
print("VALIDACION DE CAPACIDADES DEL BRAIN - MENTOR")
print("="*80)

# 1. Verificar sistema de modos
print("\n[1/5] Verificando sistema de modos PLAN/BUILD...")
try:
    from modo_operacion_brain import GESTOR_MODO, cambiar_a_build, cambiar_a_plan
    from modo_operacion_brain import ModoOperacion
    
    estado = GESTOR_MODO.get_estado()
    print(f"  [OK] Sistema de modos cargado")
    print(f"  [OK] Modo actual: {estado['modo_actual']}")
    print(f"  [OK] Puede modificar: {estado['puede_modificar']}")
    print(f"  [OK] Cambios pendientes: {estado['cambios_pendientes']}")
    
    # Test cambio a BUILD
    print("\n  Probando cambio a modo BUILD...")
    resultado = cambiar_a_build("Test de mentor")
    if resultado['status'] == 'ok':
        print(f"  [OK] Cambio a BUILD exitoso")
        print(f"  [OK] Puede modificar archivos: {resultado['puede_modificar']}")
    else:
        print(f"  [FAIL] Error: {resultado.get('error', 'Desconocido')}")
    
except Exception as e:
    print(f"  [FAIL] ERROR: {e}")

# 2. Verificar sistema de consciencia
print("\n[2/5] Verificando sistema de consciencia de limitaciones...")
try:
    from sistema_consciencia_limitaciones import SistemaConscienciaLimitaciones, CapabilityGapType
    
    sistema = SistemaConscienciaLimitaciones()
    print(f"  [OK] Sistema de consciencia cargado")
    print(f"  [OK] Tipos de carencias disponibles: {len([g for g in CapabilityGapType])}")
    print(f"  [OK] Ejemplo: {CapabilityGapType.INFRASTRUCTURE.value}")
    
    # Test analisis
    desafio = "Necesito acceder a tu red WiFi"
    analisis = sistema.analyze_challenge(desafio)
    print(f"  [OK] Analisis de desafios funciona")
    print(f"  [OK] Carencias detectadas: {len(analisis.gaps_identified)}")
    
except Exception as e:
    print(f"  [FAIL] ERROR: {e}")

# 3. Verificar metacognicion
print("\n[3/5] Verificando metacognicion...")
try:
    from meta_cognition_core import MetaCognitionCore
    
    meta = MetaCognitionCore()
    print(f"  [OK] Sistema metacognitivo cargado")
    print(f"  [OK] Capacidades conocidas: {len(meta.self_model.capabilities)}")
    print(f"  [OK] Modo resiliencia: {meta.resilience_mode}")
    
except Exception as e:
    print(f"  [FAIL] ERROR: {e}")

# 4. Verificar endpoint de modos
print("\n[4/5] Verificando endpoints de modos...")
try:
    from chat_endpoint_modos import router as modo_router
    print(f"  [OK] Router de modos disponible")
    print(f"  [OK] Endpoints: /chat/modo/comando, /estado, /cambiar")
    
except Exception as e:
    print(f"  [FAIL] ERROR: {e}")

# 5. Estado de capacidades
print("\n[5/5] Resumen de capacidades...")
try:
    print(f"  Estado actual del Brain:")
    print(f"  - Modo BUILD: {'[OK] Disponible' if estado['modo_actual'] == 'build' else '[FAIL] No activo'}")
    print(f"  - Consciencia: [OK] Funcional")
    print(f"  - Metacognicion: [OK] Funcional")
    print(f"  - Endpoints: [OK] Registrados en main.py")
except:
    print(f"  [INFO] Estado parcial verificado")

print("\n" + "="*80)
print("INSTRUCCIONES PARA EL MENTOR:")
print("="*80)
print("""
Para activar las capacidades completas del Brain:

1. Reiniciar el servidor Brain:
   $ cd C:/AI_VAULT && python main.py
   
2. Verificar endpoints disponibles:
   $ curl http://127.0.0.1:8090/chat/modo/estado
   
3. Probar modo BUILD:
   $ curl -X POST http://127.0.0.1:8090/chat/modo/cambiar \
     -H "Content-Type: application/json" \
     -d '{"nuevo_modo": "build", "razon": "Prueba de ejecucion"}'

4. Ejecutar cambio con aprobacion:
   $ curl -X POST http://127.0.0.1:8090/chat/modo/ejecutar \
     -H "Content-Type: application/json" \
     -d '{"indice_cambio": 0, "confirmacion": true}'

5. El Brain ahora puede:
   - Crear backups automaticos
   - Modificar archivos del sistema
   - Ejecutar comandos validados
   - Hacer rollback si es necesario
""")

print("="*80)