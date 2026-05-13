#!/usr/bin/env python3
"""
Script de Ingesta de Resultados - AI_VAULT
Procesa resultados obtenidos y actualiza scorecards correspondientes
"""

import json
import sys
import os
from pathlib import Path
from datetime import datetime

# Agregar AI_VAULT al path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from core.state_io import read_json, write_json
from trading.pipeline_integrity import update_scorecard_metrics

class ResultsProcessor:
    def __init__(self):
        self.base_path = Path("C:/AI_VAULT")
        self.state_path = self.base_path / "state"
        self.scorecards_path = self.state_path / "strategy_engine" / "scorecards"
        
    def process_backtest_results(self, results_file):
        """Procesa resultados de backtests y actualiza scorecards"""
        try:
            results = read_json(results_file)
            if not results:
                print(f"No se pudieron leer resultados de {results_file}")
                return False
                
            updated_count = 0
            for strategy_name, data in results.items():
                if self.update_strategy_scorecard(strategy_name, data):
                    updated_count += 1
                    
            print(f"Procesados {len(results)} resultados, actualizados {updated_count} scorecards")
            return True
            
        except Exception as e:
            print(f"Error procesando resultados: {e}")
            return False
    
    def update_strategy_scorecard(self, strategy_name, data):
        """Actualiza scorecard individual de estrategia"""
        try:
            scorecard_file = self.scorecards_path / f"{strategy_name}_scorecard.json"
            
            # Leer scorecard existente o crear nuevo
            scorecard = read_json(scorecard_file) or {
                "strategy_name": strategy_name,
                "last_updated": None,
                "metrics": {},
                "performance": {},
                "risk": {}
            }
            
            # Actualizar métricas desde los resultados
            if "performance" in data:
                scorecard["performance"].update(data["performance"])
                
            if "metrics" in data:
                scorecard["metrics"].update(data["metrics"])
                
            if "risk" in data:
                scorecard["risk"].update(data["risk"])
                
            # Timestamp de actualización
            scorecard["last_updated"] = datetime.now().isoformat()
            
            # Guardar scorecard actualizado
            write_json(scorecard_file, scorecard)
            print(f"Actualizado scorecard para {strategy_name}")
            return True
            
        except Exception as e:
            print(f"Error actualizando scorecard {strategy_name}: {e}")
            return False
    
    def process_qc_results(self, qc_data_file):
        """Procesa específicamente resultados de QuantConnect"""
        try:
            qc_data = read_json(qc_data_file)
            if not qc_data:
                return False
                
            # Transformar formato QC a formato interno
            processed_results = {}
            
            for backtest in qc_data.get("backtests", []):
                strategy_name = backtest.get("name", "unknown")
                
                # Extraer métricas clave de QC
                performance = {
                    "total_return": backtest.get("statistics", {}).get("TotalPerformance", {}).get("PortfolioStatistics", {}).get("TotalReturn", 0),
                    "sharpe_ratio": backtest.get("statistics", {}).get("TotalPerformance", {}).get("PortfolioStatistics", {}).get("SharpeRatio", 0),
                    "max_drawdown": backtest.get("statistics", {}).get("TotalPerformance", {}).get("PortfolioStatistics", {}).get("Drawdown", 0)
                }
                
                processed_results[strategy_name] = {
                    "performance": performance,
                    "source": "quantconnect",
                    "backtest_id": backtest.get("backtestId"),
                    "processed_at": datetime.now().isoformat()
                }
            
            # Procesar resultados transformados
            return self.process_results_dict(processed_results)
            
        except Exception as e:
            print(f"Error procesando resultados QC: {e}")
            return False
    
    def process_results_dict(self, results_dict):
        """Procesa diccionario de resultados directamente"""
        updated_count = 0
        for strategy_name, data in results_dict.items():
            if self.update_strategy_scorecard(strategy_name, data):
                updated_count += 1
                
        print(f"Procesados {len(results_dict)} resultados, actualizados {updated_count} scorecards")
        return updated_count > 0
    
    def consolidate_scorecards(self):
        """Consolida todos los scorecards en un resumen general"""
        try:
            all_scorecards = {}
            
            # Leer todos los scorecards
            for scorecard_file in self.scorecards_path.glob("*_scorecard.json"):
                scorecard = read_json(scorecard_file)
                if scorecard:
                    strategy_name = scorecard.get("strategy_name")
                    all_scorecards[strategy_name] = scorecard
            
            # Crear resumen consolidado
            summary = {
                "total_strategies": len(all_scorecards),
                "last_consolidated": datetime.now().isoformat(),
                "strategies": all_scorecards
            }
            
            # Guardar resumen
            summary_file = self.scorecards_path / "consolidated_scorecards.json"
            write_json(summary_file, summary)
            
            print(f"Consolidados {len(all_scorecards)} scorecards")
            return True
            
        except Exception as e:
            print(f"Error consolidando scorecards: {e}")
            return False

def main():
    if len(sys.argv) < 2:
        print("Uso: python ingest_results_processor.py <comando> [archivo]")
        print("Comandos:")
        print("  process <archivo_resultados>  - Procesa archivo de resultados")
        print("  qc <archivo_qc>              - Procesa resultados de QuantConnect")
        print("  consolidate                  - Consolida todos los scorecards")
        return
    
    processor = ResultsProcessor()
    command = sys.argv[1]
    
    if command == "process" and len(sys.argv) > 2:
        success = processor.process_backtest_results(sys.argv[2])
        print(f"Procesamiento {'exitoso' if success else 'falló'}")
        
    elif command == "qc" and len(sys.argv) > 2:
        success = processor.process_qc_results(sys.argv[2])
        print(f"Procesamiento QC {'exitoso' if success else 'falló'}")
        
    elif command == "consolidate":
        success = processor.consolidate_scorecards()
        print(f"Consolidación {'exitosa' if success else 'falló'}")
        
    else:
        print("Comando no reconocido o argumentos faltantes")

if __name__ == "__main__":
    main()
