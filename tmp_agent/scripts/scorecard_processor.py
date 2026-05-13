#!/usr/bin/env python3
"""
Scorecard Processor - Brain V9
Transforma resultados de backtests/trading en formato scorecard estándar

Created: 2026-04-03
Author: Brain V9 Agent
"""

import json
import os
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
import logging

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

@dataclass
class ScorecardEntry:
    """Entrada estándar de scorecard"""
    strategy_name: str
    venue: str
    symbol: str
    timeframe: str
    total_trades: int
    win_rate: float
    profit_factor: float
    max_drawdown: float
    sharpe_ratio: float
    total_return: float
    avg_trade_duration: float
    last_updated: str
    metadata: Dict[str, Any]

class ScorecardProcessor:
    """Procesador de resultados a formato scorecard"""
    
    def __init__(self, output_dir: str = "C:\\AI_VAULT\\tmp_agent\\scorecards"):
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)
        
    def process_quantconnect_results(self, qc_data: Dict) -> List[ScorecardEntry]:
        """Procesa resultados de QuantConnect a formato scorecard"""
        scorecards = []
        
        for backtest in qc_data.get('backtests', []):
            try:
                # Extraer métricas principales
                statistics = backtest.get('statistics', {})
                
                scorecard = ScorecardEntry(
                    strategy_name=backtest.get('name', 'Unknown'),
                    venue='QuantConnect',
                    symbol=self._extract_symbol(backtest),
                    timeframe=self._extract_timeframe(backtest),
                    total_trades=statistics.get('Total Trades', 0),
                    win_rate=self._safe_float(statistics.get('Win Rate', '0%').replace('%', '')) / 100,
                    profit_factor=self._safe_float(statistics.get('Profit-Loss Ratio', 0)),
                    max_drawdown=abs(self._safe_float(statistics.get('Drawdown', '0%').replace('%', '')) / 100),
                    sharpe_ratio=self._safe_float(statistics.get('Sharpe Ratio', 0)),
                    total_return=self._safe_float(statistics.get('Total Return', '0%').replace('%', '')) / 100,
                    avg_trade_duration=self._calculate_avg_duration(backtest),
                    last_updated=datetime.now().isoformat(),
                    metadata={
                        'backtest_id': backtest.get('backtestId', ''),
                        'start_date': backtest.get('launched', ''),
                        'end_date': backtest.get('completed', ''),
                        'initial_capital': statistics.get('Starting Equity', 0),
                        'final_equity': statistics.get('Ending Equity', 0),
                        'raw_statistics': statistics
                    }
                )
                
                scorecards.append(scorecard)
                logger.info(f"Processed scorecard for {scorecard.strategy_name}")
                
            except Exception as e:
                logger.error(f"Error processing backtest {backtest.get('name', 'Unknown')}: {e}")
                continue
                
        return scorecards
    
    def process_pocket_option_results(self, po_data: Dict) -> List[ScorecardEntry]:
        """Procesa resultados de PocketOption a formato scorecard"""
        scorecards = []
        
        for strategy_data in po_data.get('strategies', []):
            try:
                scorecard = ScorecardEntry(
                    strategy_name=strategy_data.get('name', 'Unknown'),
                    venue='PocketOption',
                    symbol=strategy_data.get('symbol', 'MIXED'),
                    timeframe=strategy_data.get('timeframe', '1m'),
                    total_trades=strategy_data.get('total_trades', 0),
                    win_rate=strategy_data.get('win_rate', 0),
                    profit_factor=strategy_data.get('profit_factor', 0),
                    max_drawdown=strategy_data.get('max_drawdown', 0),
                    sharpe_ratio=strategy_data.get('sharpe_ratio', 0),
                    total_return=strategy_data.get('total_return', 0),
                    avg_trade_duration=strategy_data.get('avg_duration_minutes', 1),
                    last_updated=datetime.now().isoformat(),
                    metadata={
                        'payout_ratio': strategy_data.get('payout_ratio', 0.8),
                        'avg_trade_amount': strategy_data.get('avg_amount', 0),
                        'currency': strategy_data.get('currency', 'USD')
                    }
                )
                
                scorecards.append(scorecard)
                logger.info(f"Processed PO scorecard for {scorecard.strategy_name}")
                
            except Exception as e:
                logger.error(f"Error processing PO strategy: {e}")
                continue
                
        return scorecards
    
    def process_generic_results(self, data: Dict, venue: str = 'Generic') -> List[ScorecardEntry]:
        """Procesa resultados genéricos a formato scorecard"""
        scorecards = []
        
        # Intenta detectar el formato automáticamente
        if 'backtests' in data:
            return self.process_quantconnect_results(data)
        elif 'strategies' in data:
            return self.process_pocket_option_results(data)
        
        # Formato genérico
        for key, strategy_data in data.items():
            if isinstance(strategy_data, dict):
                try:
                    scorecard = ScorecardEntry(
                        strategy_name=key,
                        venue=venue,
                        symbol=strategy_data.get('symbol', 'UNKNOWN'),
                        timeframe=strategy_data.get('timeframe', '1h'),
                        total_trades=strategy_data.get('trades', 0),
                        win_rate=strategy_data.get('win_rate', 0),
                        profit_factor=strategy_data.get('profit_factor', 0),
                        max_drawdown=strategy_data.get('drawdown', 0),
                        sharpe_ratio=strategy_data.get('sharpe', 0),
                        total_return=strategy_data.get('return', 0),
                        avg_trade_duration=strategy_data.get('duration', 60),
                        last_updated=datetime.now().isoformat(),
                        metadata=strategy_data
                    )
                    
                    scorecards.append(scorecard)
                    
                except Exception as e:
                    logger.error(f"Error processing generic strategy {key}: {e}")
                    continue
        
        return scorecards
    
    def save_scorecards(self, scorecards: List[ScorecardEntry], filename: str = None) -> str:
        """Guarda scorecards en formato JSON"""
        if not filename:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"scorecards_{timestamp}.json"
        
        filepath = os.path.join(self.output_dir, filename)
        
        # Convertir a dict para serialización
        data = {
            'generated_at': datetime.now().isoformat(),
            'total_scorecards': len(scorecards),
            'scorecards': [self._scorecard_to_dict(sc) for sc in scorecards]
        }
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        
        logger.info(f"Saved {len(scorecards)} scorecards to {filepath}")
        return filepath
    
    def load_and_process_file(self, input_file: str, venue: str = 'Auto') -> List[ScorecardEntry]:
        """Carga archivo y procesa a scorecards"""
        try:
            with open(input_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            if venue == 'Auto':
                return self.process_generic_results(data)
            elif venue.lower() == 'quantconnect':
                return self.process_quantconnect_results(data)
            elif venue.lower() == 'pocketoption':
                return self.process_pocket_option_results(data)
            else:
                return self.process_generic_results(data, venue)
                
        except Exception as e:
            logger.error(f"Error loading file {input_file}: {e}")
            return []
    
    def generate_summary_report(self, scorecards: List[ScorecardEntry]) -> Dict:
        """Genera reporte resumen de scorecards"""
        if not scorecards:
            return {'error': 'No scorecards to analyze'}
        
        # Métricas agregadas
        total_trades = sum(sc.total_trades for sc in scorecards)
        avg_win_rate = sum(sc.win_rate for sc in scorecards) / len(scorecards)
        avg_sharpe = sum(sc.sharpe_ratio for sc in scorecards) / len(scorecards)
        
        # Top performers
        top_by_return = sorted(scorecards, key=lambda x: x.total_return, reverse=True)[:5]
        top_by_sharpe = sorted(scorecards, key=lambda x: x.sharpe_ratio, reverse=True)[:5]
        
        return {
            'summary': {
                'total_strategies': len(scorecards),
                'total_trades': total_trades,
                'avg_win_rate': avg_win_rate,
                'avg_sharpe_ratio': avg_sharpe,
                'venues': list(set(sc.venue for sc in scorecards))
            },
            'top_performers': {
                'by_return': [{'name': sc.strategy_name, 'return': sc.total_return} for sc in top_by_return],
                'by_sharpe': [{'name': sc.strategy_name, 'sharpe': sc.sharpe_ratio} for sc in top_by_sharpe]
            }
        }
    
    def _extract_symbol(self, backtest: Dict) -> str:
        """Extrae símbolo del backtest"""
        # Buscar en diferentes lugares
        if 'symbol' in backtest:
            return backtest['symbol']
        if 'assets' in backtest and backtest['assets']:
            return backtest['assets'][0] if isinstance(backtest['assets'], list) else str(backtest['assets'])
        return 'MIXED'
    
    def _extract_timeframe(self, backtest: Dict) -> str:
        """Extrae timeframe del backtest"""
        if 'resolution' in backtest:
            return backtest['resolution']
        if 'timeframe' in backtest:
            return backtest['timeframe']
        return '1h'
    
    def _safe_float(self, value) -> float:
        """Conversión segura a float"""
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            try:
                return float(value.replace('%', '').replace(',', ''))
            except:
                return 0.0
        return 0.0
    
    def _calculate_avg_duration(self, backtest: Dict) -> float:
        """Calcula duración promedio de trades en minutos"""
        # Placeholder - necesitaría datos de trades individuales
        return 60.0  # Default 1 hora
    
    def _scorecard_to_dict(self, scorecard: ScorecardEntry) -> Dict:
        """Convierte scorecard a diccionario"""
        return {
            'strategy_name': scorecard.strategy_name,
            'venue': scorecard.venue,
            'symbol': scorecard.symbol,
            'timeframe': scorecard.timeframe,
            'metrics': {
                'total_trades': scorecard.total_trades,
                'win_rate': scorecard.win_rate,
                'profit_factor': scorecard.profit_factor,
                'max_drawdown': scorecard.max_drawdown,
                'sharpe_ratio': scorecard.sharpe_ratio,
                'total_return': scorecard.total_return,
                'avg_trade_duration_minutes': scorecard.avg_trade_duration
            },
            'last_updated': scorecard.last_updated,
            'metadata': scorecard.metadata
        }

def main():
    """Función principal para uso standalone"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Procesa resultados a formato scorecard')
    parser.add_argument('input_file', help='Archivo JSON con resultados')
    parser.add_argument('--venue', default='Auto', help='Venue específico (Auto, QuantConnect, PocketOption)')
    parser.add_argument('--output', help='Archivo de salida (opcional)')
    parser.add_argument('--summary', action='store_true', help='Genera reporte resumen')
    
    args = parser.parse_args()
    
    processor = ScorecardProcessor()
    
    # Procesar archivo
    scorecards = processor.load_and_process_file(args.input_file, args.venue)
    
    if not scorecards:
        logger.error("No se pudieron procesar scorecards")
        return
    
    # Guardar scorecards
    output_file = processor.save_scorecards(scorecards, args.output)
    print(f"Scorecards guardados en: {output_file}")
    
    # Reporte resumen
    if args.summary:
        summary = processor.generate_summary_report(scorecards)
        print("\n=== REPORTE RESUMEN ===")
        print(json.dumps(summary, indent=2))

if __name__ == '__main__':
    main()
