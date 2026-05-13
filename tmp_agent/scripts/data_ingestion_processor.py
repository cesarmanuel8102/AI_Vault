#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Data Ingestion Processor - AI_VAULT Brain V9
Procesa datos obtenidos y actualiza scorecards del sistema

Created: 2026-04-03
Author: Brain V9 Agent
"""

import json
import os
import sys
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional

# Configuración de rutas
AI_VAULT_BASE = Path(r'C:\AI_VAULT')
STATE_PATH = AI_VAULT_BASE / 'state'
SCORECARDS_PATH = STATE_PATH / 'strategy_engine' / 'scorecards'
PIPELINE_INTEGRITY_PATH = STATE_PATH / 'strategy_engine' / 'pipeline_integrity_latest.json'
RANKING_V2_PATH = STATE_PATH / 'strategy_engine' / 'strategy_ranking_v2_latest.json'

class DataIngestionProcessor:
    """Procesador de ingesta de datos para actualización de scorecards"""
    
    def __init__(self):
        self.timestamp = datetime.now(timezone.utc)
        self.processed_count = 0
        self.error_count = 0
        self.log_entries = []
        
    def log(self, message: str, level: str = 'INFO'):
        """Registra mensaje con timestamp"""
        entry = f"[{self.timestamp.strftime('%Y-%m-%d %H:%M:%S')}] {level}: {message}"
        self.log_entries.append(entry)
        print(entry)
        
    def load_existing_scorecard(self, strategy_name: str) -> Dict[str, Any]:
        """Carga scorecard existente o crea uno nuevo"""
        scorecard_file = SCORECARDS_PATH / f"{strategy_name}_scorecard.json"
        
        if scorecard_file.exists():
            try:
                with open(scorecard_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                self.log(f"Error cargando scorecard {strategy_name}: {e}", 'ERROR')
                self.error_count += 1
                
        # Scorecard base si no existe
        return {
            'strategy_name': strategy_name,
            'created_at': self.timestamp.isoformat(),
            'last_updated': self.timestamp.isoformat(),
            'performance_metrics': {
                'total_trades': 0,
                'win_rate': 0.0,
                'profit_factor': 0.0,
                'sharpe_ratio': 0.0,
                'max_drawdown': 0.0,
                'total_return': 0.0
            },
            'backtest_results': [],
            'live_performance': {},
            'risk_metrics': {},
            'governance': {
                'status': 'active',
                'last_review': self.timestamp.isoformat(),
                'confidence_score': 0.0
            }
        }
        
    def update_scorecard_with_data(self, scorecard: Dict[str, Any], new_data: Dict[str, Any]) -> Dict[str, Any]:
        """Actualiza scorecard con nuevos datos"""
        try:
            # Actualizar timestamp
            scorecard['last_updated'] = self.timestamp.isoformat()
            
            # Procesar métricas de performance si están disponibles
            if 'performance' in new_data:
                perf = new_data['performance']
                metrics = scorecard['performance_metrics']
                
                # Actualizar métricas clave
                if 'total_trades' in perf:
                    metrics['total_trades'] = perf['total_trades']
                if 'win_rate' in perf:
                    metrics['win_rate'] = perf['win_rate']
                if 'profit_factor' in perf:
                    metrics['profit_factor'] = perf['profit_factor']
                if 'sharpe_ratio' in perf:
                    metrics['sharpe_ratio'] = perf['sharpe_ratio']
                if 'max_drawdown' in perf:
                    metrics['max_drawdown'] = perf['max_drawdown']
                if 'total_return' in perf:
                    metrics['total_return'] = perf['total_return']
                    
            # Agregar resultados de backtest si están disponibles
            if 'backtest_result' in new_data:
                backtest = new_data['backtest_result']
                backtest['processed_at'] = self.timestamp.isoformat()
                scorecard['backtest_results'].append(backtest)
                
                # Mantener solo los últimos 10 backtests
                if len(scorecard['backtest_results']) > 10:
                    scorecard['backtest_results'] = scorecard['backtest_results'][-10:]
                    
            # Actualizar performance en vivo si está disponible
            if 'live_data' in new_data:
                scorecard['live_performance'].update(new_data['live_data'])
                
            # Actualizar métricas de riesgo
            if 'risk_data' in new_data:
                scorecard['risk_metrics'].update(new_data['risk_data'])
                
            # Calcular confidence score basado en datos disponibles
            confidence = self.calculate_confidence_score(scorecard)
            scorecard['governance']['confidence_score'] = confidence
            
            return scorecard
            
        except Exception as e:
            self.log(f"Error actualizando scorecard: {e}", 'ERROR')
            self.error_count += 1
            return scorecard
            
    def calculate_confidence_score(self, scorecard: Dict[str, Any]) -> float:
        """Calcula score de confianza basado en datos disponibles"""
        try:
            score = 0.0
            
            # Puntos por métricas de performance válidas
            metrics = scorecard['performance_metrics']
            if metrics['total_trades'] > 0:
                score += 0.2
            if metrics['win_rate'] > 0:
                score += 0.2
            if metrics['sharpe_ratio'] != 0:
                score += 0.2
                
            # Puntos por resultados de backtest
            if len(scorecard['backtest_results']) > 0:
                score += 0.2
                
            # Puntos por datos en vivo
            if scorecard['live_performance']:
                score += 0.2
                
            return min(score, 1.0)
            
        except Exception:
            return 0.0
            
    def save_scorecard(self, scorecard: Dict[str, Any]) -> bool:
        """Guarda scorecard actualizado"""
        try:
            strategy_name = scorecard['strategy_name']
            scorecard_file = SCORECARDS_PATH / f"{strategy_name}_scorecard.json"
            
            # Crear directorio si no existe
            SCORECARDS_PATH.mkdir(parents=True, exist_ok=True)
            
            # Guardar con formato legible
            with open(scorecard_file, 'w', encoding='utf-8') as f:
                json.dump(scorecard, f, indent=2, ensure_ascii=False)
                
            self.log(f"Scorecard guardado: {scorecard_file}")
            return True
            
        except Exception as e:
            self.log(f"Error guardando scorecard: {e}", 'ERROR')
            self.error_count += 1
            return False
            
    def process_data_batch(self, data_batch: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Procesa lote de datos y actualiza scorecards"""
        results = {
            'processed': 0,
            'errors': 0,
            'updated_strategies': [],
            'timestamp': self.timestamp.isoformat()
        }
        
        for data_item in data_batch:
            try:
                if 'strategy_name' not in data_item:
                    self.log("Data item sin strategy_name, omitiendo", 'WARNING')
                    continue
                    
                strategy_name = data_item['strategy_name']
                
                # Cargar scorecard existente
                scorecard = self.load_existing_scorecard(strategy_name)
                
                # Actualizar con nuevos datos
                updated_scorecard = self.update_scorecard_with_data(scorecard, data_item)
                
                # Guardar scorecard actualizado
                if self.save_scorecard(updated_scorecard):
                    results['processed'] += 1
                    if strategy_name not in results['updated_strategies']:
                        results['updated_strategies'].append(strategy_name)
                else:
                    results['errors'] += 1
                    
            except Exception as e:
                self.log(f"Error procesando item: {e}", 'ERROR')
                results['errors'] += 1
                
        return results
        
    def update_pipeline_integrity(self, processing_results: Dict[str, Any]):
        """Actualiza integridad del pipeline con resultados del procesamiento"""
        try:
            integrity_data = {
                'last_ingestion': self.timestamp.isoformat(),
                'processed_count': processing_results['processed'],
                'error_count': processing_results['errors'],
                'updated_strategies': processing_results['updated_strategies'],
                'status': 'healthy' if processing_results['errors'] == 0 else 'degraded'
            }
            
            # Cargar datos existentes si los hay
            if PIPELINE_INTEGRITY_PATH.exists():
                with open(PIPELINE_INTEGRITY_PATH, 'r', encoding='utf-8') as f:
                    existing_data = json.load(f)
                    
                # Actualizar sección de ingesta
                existing_data['data_ingestion'] = integrity_data
            else:
                existing_data = {'data_ingestion': integrity_data}
                
            # Guardar datos actualizados
            with open(PIPELINE_INTEGRITY_PATH, 'w', encoding='utf-8') as f:
                json.dump(existing_data, f, indent=2, ensure_ascii=False)
                
            self.log(f"Pipeline integrity actualizado: {processing_results['processed']} procesados, {processing_results['errors']} errores")
            
        except Exception as e:
            self.log(f"Error actualizando pipeline integrity: {e}", 'ERROR')
            
def main():
    """Función principal de procesamiento"""
    processor = DataIngestionProcessor()
    processor.log("Iniciando procesamiento de ingesta de datos")
    
    # Ejemplo de datos simulados para prueba
    # En uso real, estos datos vendrían de las fuentes externas (QC, IBKR, etc.)
    sample_data = [
        {
            'strategy_name': 'momentum_v1',
            'performance': {
                'total_trades': 150,
                'win_rate': 0.65,
                'profit_factor': 1.45,
                'sharpe_ratio': 1.2,
                'max_drawdown': -0.08,
                'total_return': 0.23
            },
            'backtest_result': {
                'backtest_id': 'bt_001',
                'period': '2024-01-01_2024-03-31',
                'result': 'profitable'
            }
        },
        {
            'strategy_name': 'mean_reversion_v2',
            'performance': {
                'total_trades': 89,
                'win_rate': 0.58,
                'profit_factor': 1.12,
                'sharpe_ratio': 0.85
            }
        }
    ]
    
    # Procesar datos
    results = processor.process_data_batch(sample_data)
    
    # Actualizar integridad del pipeline
    processor.update_pipeline_integrity(results)
    
    # Reporte final
    processor.log(f"Procesamiento completado: {results['processed']} estrategias actualizadas, {results['errors']} errores")
    
    for log_entry in processor.log_entries:
        print(log_entry)
        
    return results

if __name__ == '__main__':
    results = main()
    sys.exit(0 if results['errors'] == 0 else 1)
