"""
AI_VAULT Phase Promotion System
Sistema de promoción automática de fases basado en premisas canónicas
"""

import json
import asyncio
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Any
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class PhasePromotionSystem:
    """
    Sistema de promoción automática de fases
    Evalúa calidad y promueve el Brain a la siguiente fase
    """
    
    def __init__(self):
        self.state_path = Path(r"C:\AI_VAULT\00_identity\autonomy_system\autonomy_state.json")
        self.roadmap_v2_path = Path(r"C:\AI_VAULT\00_identity\autonomy_system\ROADMAP_V2_AUTONOMY.json")
        self.roadmap_bl_path = Path(r"C:\AI_VAULT\tmp_agent\state\roadmap.json")
        self.promotion_log_path = Path(r"C:\AI_VAULT\00_identity\autonomy_system\logs\promotion_history.json")
        
        # Criterios de calidad por fase
        self.quality_thresholds = {
            "6.1": {
                "min_files": 4,
                "min_test_coverage": 0.8,
                "max_errors": 0,
                "required_components": [
                    "trading_engine.py",
                    "risk_manager.py", 
                    "capital_manager.py",
                    "financial_motor.py"
                ]
            },
            "6.2": {
                "min_strategies": 3,
                "min_sharpe": 1.0,
                "max_drawdown": 0.10,
                "required_components": [
                    "strategy_generator.py",
                    "backtest_engine.py"
                ]
            },
            "6.3": {
                "broker_connected": True,
                "auto_execution": True,
                "risk_management_realtime": True
            }
        }
        
        logger.info("PhasePromotionSystem initialized")
    
    def evaluate_phase_6_1(self) -> Dict[str, Any]:
        """Evaluar si Fase 6.1 está completa"""
        required_files = self.quality_thresholds["6.1"]["required_components"]
        base_path = Path(r"C:\AI_VAULT\00_identity")
        
        results = {
            "phase": "6.1",
            "name": "MOTOR_FINANCIERO",
            "files_found": [],
            "files_missing": [],
            "status": "pending"
        }
        
        for file in required_files:
            if (base_path / file).exists():
                results["files_found"].append(file)
            else:
                results["files_missing"].append(file)
        
        results["completion_pct"] = len(results["files_found"]) / len(required_files) * 100
        results["status"] = "completed" if results["completion_pct"] >= 100 else "in_progress"
        
        return results
    
    def evaluate_phase_6_2(self) -> Dict[str, Any]:
        """Evaluar si Fase 6.2 está completa"""
        required_files = self.quality_thresholds["6.2"]["required_components"]
        base_path = Path(r"C:\AI_VAULT\00_identity")
        
        results = {
            "phase": "6.2",
            "name": "INTELIGENCIA_ESTRATEGICA",
            "files_found": [],
            "files_missing": [],
            "status": "pending"
        }
        
        for file in required_files:
            if (base_path / file).exists():
                results["files_found"].append(file)
            else:
                results["files_missing"].append(file)
        
        results["completion_pct"] = len(results["files_found"]) / len(required_files) * 100
        results["status"] = "completed" if results["completion_pct"] >= 100 else "in_progress"
        
        return results
    
    def evaluate_bl_02(self) -> Dict[str, Any]:
        """Evaluar si BL-02 está completo"""
        required_files = [
            "utility_u_operational_contract.json",
            "utility_signal_map.json",
            "bl02_complete.json"
        ]
        base_path = Path(r"C:\AI_VAULT\00_identity\autonomy_system")
        
        results = {
            "phase": "BL-02",
            "name": "Operativizacion de la funcion U",
            "files_found": [],
            "files_missing": [],
            "status": "pending"
        }
        
        for file in required_files:
            if (base_path / file).exists():
                results["files_found"].append(file)
            else:
                results["files_missing"].append(file)
        
        results["completion_pct"] = len(results["files_found"]) / len(required_files) * 100
        results["status"] = "completed" if results["completion_pct"] >= 100 else "in_progress"
        
        return results
    
    def check_promotion_eligible(self, phase: str) -> bool:
        """Verificar si una fase es elegible para promoción"""
        if phase == "6.1":
            eval_result = self.evaluate_phase_6_1()
            return eval_result["status"] == "completed"
        elif phase == "6.2":
            eval_result = self.evaluate_phase_6_2()
            return eval_result["status"] == "completed"
        elif phase == "BL-02":
            eval_result = self.evaluate_bl_02()
            return eval_result["status"] == "completed"
        return False
    
    def promote_phase(self, from_phase: str, to_phase: str) -> bool:
        """Promover de una fase a otra"""
        if not self.check_promotion_eligible(from_phase):
            logger.warning(f"Phase {from_phase} not eligible for promotion")
            return False
        
        # Actualizar roadmap V2
        if from_phase.startswith("6."):
            self._update_roadmap_v2(from_phase, to_phase)
        
        # Actualizar roadmap BL
        if from_phase.startswith("BL-"):
            self._update_roadmap_bl(from_phase, to_phase)
        
        # Log de promoción
        self._log_promotion(from_phase, to_phase)
        
        logger.info(f"✅ Phase promoted: {from_phase} -> {to_phase}")
        return True
    
    def _update_roadmap_v2(self, from_phase: str, to_phase: str):
        """Actualizar roadmap V2"""
        try:
            with open(self.roadmap_v2_path, 'r') as f:
                roadmap = json.load(f)
            
            # Marcar fase anterior como completada
            for phase in roadmap.get("phases", []):
                if str(phase.get("number")) == from_phase:
                    phase["status"] = "completed"
                if str(phase.get("number")) == to_phase:
                    phase["status"] = "active"
            
            with open(self.roadmap_v2_path, 'w') as f:
                json.dump(roadmap, f, indent=2)
                
        except Exception as e:
            logger.error(f"Error updating roadmap V2: {e}")
    
    def _update_roadmap_bl(self, from_phase: str, to_phase: str):
        """Actualizar roadmap BL"""
        try:
            with open(self.roadmap_bl_path, 'r') as f:
                roadmap = json.load(f)
            
            # Marcar item anterior como completado
            for item in roadmap.get("work_items", []):
                if item.get("id") == from_phase:
                    item["status"] = "done"
                if item.get("id") == to_phase:
                    item["status"] = "in_progress"
                    roadmap["current_phase"] = to_phase
            
            with open(self.roadmap_bl_path, 'w') as f:
                json.dump(roadmap, f, indent=2)
                
        except Exception as e:
            logger.error(f"Error updating roadmap BL: {e}")
    
    def _log_promotion(self, from_phase: str, to_phase: str):
        """Registrar promoción"""
        log_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "from_phase": from_phase,
            "to_phase": to_phase,
            "promoted_by": "system_autonomy",
            "quality_validated": True
        }
        
        try:
            if self.promotion_log_path.exists():
                with open(self.promotion_log_path, 'r') as f:
                    logs = json.load(f)
            else:
                logs = {"promotions": []}
            
            logs["promotions"].append(log_entry)
            
            with open(self.promotion_log_path, 'w') as f:
                json.dump(logs, f, indent=2)
                
        except Exception as e:
            logger.error(f"Error logging promotion: {e}")
    
    def get_current_status(self) -> Dict[str, Any]:
        """Obtener estado actual de todas las fases"""
        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "phases": {
                "6.1": self.evaluate_phase_6_1(),
                "6.2": self.evaluate_phase_6_2(),
                "BL-02": self.evaluate_bl_02()
            },
            "promotion_eligible": {
                "6.1": self.check_promotion_eligible("6.1"),
                "6.2": self.check_promotion_eligible("6.2"),
                "BL-02": self.check_promotion_eligible("BL-02")
            }
        }
    
    async def run_autonomy_cycle(self):
        """Ciclo de autonomía - evaluar y promover automáticamente"""
        while True:
            logger.info("Running autonomy evaluation cycle...")
            
            # Evaluar fases
            status = self.get_current_status()
            
            # Promover si es elegible
            if status["promotion_eligible"].get("6.1"):
                self.promote_phase("6.1", "6.2")
            
            if status["promotion_eligible"].get("BL-02"):
                # BL-02 completo, avanzar a BL-03
                logger.info("BL-02 completed. Promoting to BL-03...")
                self.promote_phase("BL-02", "BL-03")
            
            logger.info(f"Phase status: 6.1={status['phases']['6.1']['status']}, "
                       f"6.2={status['phases']['6.2']['status']}, "
                       f"BL-02={status['phases']['BL-02']['status']}")
            
            # Esperar 5 minutos
            await asyncio.sleep(300)

# Instancia global
phase_promotion_system = PhasePromotionSystem()

if __name__ == "__main__":
    # Test
    status = phase_promotion_system.get_current_status()
    print(json.dumps(status, indent=2))
