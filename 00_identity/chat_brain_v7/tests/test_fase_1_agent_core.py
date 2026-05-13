#!/usr/bin/env python3
"""
Tests Fase 1: Núcleo del Agente
Verifica que el AgentLoop funciona correctamente
"""

import asyncio
import json
import sys
from pathlib import Path

# Añadir path
sys.path.insert(0, str(Path(__file__).parent.parent))

from agent_core import AgentLoop, Plan, Step, StepStatus, ExecutionMemory


class TestFase1:
    """Tests de verificación de Fase 1"""
    
    def __init__(self):
        self.results = []
        self.passed = 0
        self.failed = 0
    
    async def test_agent_loop_initialization(self):
        """Test 1: AgentLoop se inicializa correctamente"""
        try:
            agent = AgentLoop("test_session")
            assert agent.session_id == "test_session"
            assert agent.memory is not None
            assert agent.reasoner is not None
            self.log_pass("Test 1", "AgentLoop inicializado correctamente")
            return True
        except Exception as e:
            self.log_fail("Test 1", f"Error inicializando AgentLoop: {e}")
            return False
    
    async def test_observation_creation(self):
        """Test 2: Sistema de observación funciona"""
        try:
            agent = AgentLoop("test_obs")
            context = {"message": "test message", "user_id": "test"}
            observation = await agent.observe(context)
            
            # Verificar que la observación tiene los campos necesarios
            assert observation.timestamp is not None, "timestamp es None"
            assert observation.user_input == "test message", f"user_input es: {observation.user_input}"
            assert observation.system_state is not None, "system_state es None"
            
            # Verificar contenido de system_state
            assert "session_id" in observation.system_state or isinstance(observation.system_state, dict), "system_state no tiene estructura válida"
            
            self.log_pass("Test 2", f"Observación creada: {len(str(observation.system_state))} caracteres")
            return True
        except AssertionError as e:
            self.log_fail("Test 2", f"Assertion falló: {e}")
            return False
        except Exception as e:
            self.log_fail("Test 2", f"Error en observación: {type(e).__name__}: {e}")
            return False
    
    async def test_plan_generation(self):
        """Test 3: Planificación funciona (con fallback)"""
        try:
            agent = AgentLoop("test_plan")
            context = {"message": "Crear archivo test.txt"}
            observation = await agent.observe(context)
            plan = await agent.reason(observation)
            
            assert plan is not None
            assert plan.objective is not None
            assert len(plan.steps) > 0
            assert plan.created_at is not None
            
            self.log_pass("Test 3", f"Plan generado: {len(plan.steps)} pasos")
            return True
        except Exception as e:
            self.log_fail("Test 3", f"Error generando plan: {e}")
            return False
    
    async def test_step_execution(self):
        """Test 4: Ejecución de pasos funciona"""
        try:
            agent = AgentLoop("test_exec")
            
            # Crear un paso simple
            step = Step(
                id=1,
                action="execute_command",
                params={"command": "echo 'test'"},
                description="Test command"
            )
            
            success, result = await agent.act(step)
            
            assert success is True
            assert result is not None
            assert result.get("success") is True
            assert step.status == StepStatus.COMPLETED
            
            self.log_pass("Test 4", f"Paso ejecutado: {result.get('stdout', '').strip()}")
            return True
        except Exception as e:
            self.log_fail("Test 4", f"Error ejecutando paso: {e}")
            return False
    
    async def test_verification(self):
        """Test 5: Verificación de pasos funciona"""
        try:
            agent = AgentLoop("test_verify")
            
            # Crear paso completado
            step = Step(
                id=1,
                action="execute_command",
                params={},
                description="Test"
            )
            step.status = StepStatus.COMPLETED
            step.result = {"success": True, "returncode": 0}
            
            verified = await agent.verify(step)
            
            assert verified is True
            
            self.log_pass("Test 5", "Verificación funciona correctamente")
            return True
        except Exception as e:
            self.log_fail("Test 5", f"Error en verificación: {e}")
            return False
    
    async def test_memory_persistence(self):
        """Test 6: Memoria persiste entre operaciones"""
        try:
            memory = ExecutionMemory("test_mem")
            
            # Guardar variable
            memory.set("test_key", "test_value")
            
            # Recuperar
            value = memory.get("test_key")
            assert value == "test_value"
            
            # Guardar a disco
            memory.save_to_disk()
            
            # Verificar que archivo existe
            import os
            path = f"C:\\AI_VAULT\\tmp_agent\\state\\memory\\agent_test_mem.json"
            assert os.path.exists(path), f"Archivo no creado: {path}"
            
            self.log_pass("Test 6", "Memoria persistente funciona")
            return True
        except Exception as e:
            self.log_fail("Test 6", f"Error en memoria: {e}")
            return False
    
    async def test_full_cycle(self):
        """Test 7: Ciclo completo del agente"""
        try:
            agent = AgentLoop("test_cycle")
            
            result = await agent.run_cycle(
                "Ejecuta comando echo 'Hello from Agent'",
                {"user_id": "test"}
            )
            
            assert result is not None
            assert result.get("success") is True
            assert "plan" in result
            assert "results" in result
            
            self.log_pass("Test 7", f"Ciclo completo: {result.get('completed_steps', 0)} pasos completados")
            return True
        except Exception as e:
            self.log_fail("Test 7", f"Error en ciclo completo: {e}")
            return False
    
    async def test_error_handling(self):
        """Test 8: Manejo de errores"""
        try:
            agent = AgentLoop("test_error")
            
            # Crear paso que fallará
            step = Step(
                id=1,
                action="execute_command",
                params={"command": "comando_inexistente_12345"},
                description="Invalid command"
            )
            
            success, result = await agent.act(step)
            
            # Debe fallar pero no crashear
            assert success is False or result.get("success") is False
            assert step.status == StepStatus.FAILED or step.error is not None
            
            self.log_pass("Test 8", "Manejo de errores funciona")
            return True
        except Exception as e:
            self.log_fail("Test 8", f"Error en manejo de errores: {e}")
            return False
    
    def log_pass(self, test_name, message):
        self.results.append(f"[PASS] {test_name}: {message}")
        self.passed += 1
    
    def log_fail(self, test_name, message):
        self.results.append(f"[FAIL] {test_name}: {message}")
        self.failed += 1
    
    async def run_all(self):
        """Ejecutar todos los tests"""
        print("=" * 70)
        print("FASE 1: TESTS DE NÚCLEO DEL AGENTE")
        print("=" * 70)
        print()
        
        await self.test_agent_loop_initialization()
        await self.test_observation_creation()
        await self.test_plan_generation()
        await self.test_step_execution()
        await self.test_verification()
        await self.test_memory_persistence()
        await self.test_full_cycle()
        await self.test_error_handling()
        
        print()
        print("=" * 70)
        print("RESULTADOS")
        print("=" * 70)
        for result in self.results:
            print(result)
        print()
        print(f"Total: {self.passed + self.failed} tests")
        print(f"Passed: {self.passed}")
        print(f"Failed: {self.failed}")
        print(f"Success Rate: {self.passed/(self.passed + self.failed)*100:.1f}%")
        print()
        
        if self.failed == 0:
            print("FASE 1 COMPLETADA - Núcleo del agente operativo")
            return 0
        else:
            print("FASE 1 INCOMPLETA - Revisar errores")
            return 1


if __name__ == "__main__":
    tester = TestFase1()
    exit_code = asyncio.run(tester.run_all())
    sys.exit(exit_code)
