#!/usr/bin/env python3
"""
Script de Ingesta y Actualización de Scorecards
Procesa resultados obtenidos y actualiza las scorecards del sistema AI_VAULT

Creado: 2026-04-03
Versión: 1.0
"""

import json
import os
import sys
from pathlib import Path
from datetime import datetime, timezone
import logging

# Agregar el directorio raíz al path para importar módulos del sistema
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from core.state_io import read_json_state, write_json_state
from trading.pipeline_integrity import get_pipeline_integrity, update_strategy_ranking

# Configuración de logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('C:\\AI_VAULT\\logs\\ingest_scorecard_update.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class ScoreCardUpdater:
    """Actualizador de scorecards del sistema"""
    
    def __init__(self):
        self.base_path = Path("C:\\AI_VAULT")
        self.state_path = self.base_path / "state"
        self.results_path = self.base_path / "tmp_agent" / "results"
        self.timestamp = datetime.now(timezone.utc).isoformat()
        
    def load_existing_scorecards(self):
        """Carga scorecards existentes del sistema"""
        try:
            scorecard_files = [
                self.state_path / "strategy_engine" / "strategy_scorecards_latest.json",
                self.state_path / "strategy_engine" / "pipeline_integrity_latest.json",
                self.state_path / "strategy_engine" / "strategy_ranking_v2_latest.json"
            ]
            
            scorecards = {}
            for file_path in scorecard_files:
                if file_path.exists():
                    data = read_json_state(str(file_path))
                    scorecards[file_path.stem] = data
                    logger.info(f"Cargado scorecard: {file_path.name}")
                else:
                    logger.warning(f"Scorecard no encontrado: {file_path.name}")
                    
            return scorecards
            
        except Exception as e:
            logger.error(f"Error cargando scorecards existentes: {e}")
            return {}
    
    def process_qc_results(self):
        """Procesa resultados de QuantConnect si están disponibles"""
        qc_results_path = self.results_path / "qc_backtests"
        
        if not qc_results_path.exists():
            logger.info("No se encontraron resultados de QuantConnect")
            return {}
            
        results = {}
        try:
            for result_file in qc_results_path.glob("*.json"):
                with open(result_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    results[result_file.stem] = data
                    logger.info(f"Procesado resultado QC: {result_file.name}")
                    
        except Exception as e:
            logger.error(f"Error procesando resultados QC: {e}")
            
        return results
    
    def update_strategy_scorecards(self, qc_results, existing_scorecards):
        """Actualiza scorecards de estrategias con nuevos resultados"""
        try:
            # Estructura base del scorecard actualizado
            updated_scorecard = {
                "last_updated": self.timestamp,
                "version": "v2.1",
                "strategies": {},
                "summary": {
                    "total_strategies": 0,
                    "active_strategies": 0,
                    "avg_performance": 0.0,
                    "last_ingestion": self.timestamp
                }
            }
            
            # Integrar datos existentes si los hay
            if "strategy_scorecards_latest" in existing_scorecards:
                existing = existing_scorecards["strategy_scorecards_latest"]
                if "strategies" in existing:
                    updated_scorecard["strategies"] = existing["strategies"].copy()
            
            # Procesar resultados de QC y actualizar scorecards
            for strategy_name, qc_data in qc_results.items():
                if strategy_name not in updated_scorecard["strategies"]:
                    updated_scorecard["strategies"][strategy_name] = {
                        "created": self.timestamp,
                        "performance_history": [],
                        "status": "active"
                    }
                
                strategy = updated_scorecard["strategies"][strategy_name]
                
                # Extraer métricas relevantes del backtest
                if "Statistics" in qc_data:
                    stats = qc_data["Statistics"]
                    performance_entry = {
                        "timestamp": self.timestamp,
                        "total_return": stats.get("Total Return", 0.0),
                        "sharpe_ratio": stats.get("Sharpe Ratio", 0.0),
                        "max_drawdown": stats.get("Maximum Drawdown", 0.0),
                        "win_rate": stats.get("Win Rate", 0.0),
                        "profit_loss_ratio": stats.get("Profit-Loss Ratio", 0.0)
                    }
                    
                    strategy["performance_history"].append(performance_entry)
                    strategy["last_updated"] = self.timestamp
                    strategy["latest_performance"] = performance_entry
                    
                    logger.info(f"Actualizado scorecard para estrategia: {strategy_name}")
            
            # Actualizar resumen
            strategies = updated_scorecard["strategies"]
            updated_scorecard["summary"]["total_strategies"] = len(strategies)
            updated_scorecard["summary"]["active_strategies"] = sum(
                1 for s in strategies.values() if s.get("status") == "active"
            )
            
            # Calcular performance promedio
            if strategies:
                total_returns = []
                for strategy in strategies.values():
                    if "latest_performance" in strategy:
                        total_returns.append(strategy["latest_performance"].get("total_return", 0.0))
                
                if total_returns:
                    updated_scorecard["summary"]["avg_performance"] = sum(total_returns) / len(total_returns)
            
            return updated_scorecard
            
        except Exception as e:
            logger.error(f"Error actualizando strategy scorecards: {e}")
            return None
    
    def save_updated_scorecards(self, updated_scorecard):
        """Guarda los scorecards actualizados"""
        if not updated_scorecard:
            logger.error("No hay scorecards para guardar")
            return False
            
        try:
            output_path = self.state_path / "strategy_engine" / "strategy_scorecards_latest.json"
            
            # Crear directorio si no existe
            output_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Guardar usando el sistema de state_io para consistencia
            success = write_json_state(str(output_path), updated_scorecard)
            
            if success:
                logger.info(f"Scorecards actualizados guardados en: {output_path}")
                return True
            else:
                logger.error("Error guardando scorecards actualizados")
                return False
                
        except Exception as e:
            logger.error(f"Error guardando scorecards: {e}")
            return False
    
    def run_ingestion(self):
        """Ejecuta el proceso completo de ingesta y actualización"""
        logger.info("=== INICIANDO INGESTA Y ACTUALIZACIÓN DE SCORECARDS ===")
        
        try:
            # 1. Cargar scorecards existentes
            logger.info("Paso 1: Cargando scorecards existentes...")
            existing_scorecards = self.load_existing_scorecards()
            
            # 2. Procesar resultados de QuantConnect
            logger.info("Paso 2: Procesando resultados de QuantConnect...")
            qc_results = self.process_qc_results()
            
            # 3. Actualizar scorecards de estrategias
            logger.info("Paso 3: Actualizando scorecards de estrategias...")
            updated_scorecard = self.update_strategy_scorecards(qc_results, existing_scorecards)
            
            # 4. Guardar scorecards actualizados
            logger.info("Paso 4: Guardando scorecards actualizados...")
            success = self.save_updated_scorecards(updated_scorecard)
            
            if success:
                logger.info("=== INGESTA COMPLETADA EXITOSAMENTE ===")
                
                # Mostrar resumen
                if updated_scorecard:
                    summary = updated_scorecard["summary"]
                    logger.info(f"Resumen:")
                    logger.info(f"  - Total estrategias: {summary['total_strategies']}")
                    logger.info(f"  - Estrategias activas: {summary['active_strategies']}")
                    logger.info(f"  - Performance promedio: {summary['avg_performance']:.2%}")
                    
                return True
            else:
                logger.error("=== INGESTA FALLÓ ===")
                return False
                
        except Exception as e:
            logger.error(f"Error en proceso de ingesta: {e}")
            return False

def main():
    """Función principal"""
    updater = ScoreCardUpdater()
    success = updater.run_ingestion()
    
    if success:
        print("✅ Ingesta y actualización de scorecards completada exitosamente")
        sys.exit(0)
    else:
        print("❌ Error en la ingesta y actualización de scorecards")
        sys.exit(1)

if __name__ == "__main__":
    main()
