#!/usr/bin/env python3
"""
STRATEGY_ADAPTER.PY
Adapter para estrategias existentes + integración con NIF
"""

import os
import importlib.util
import json
from datetime import datetime, timedelta
import numpy as np
from typing import Dict, List, Any, Callable, Optional

# === ADAPTADOR PARA ESTRATEGIAS EXISTENTES ===

class StrategyAdapter:
    """Interface estandarizada para estrategias pre-existente"""
    
    def __init__(self, strategy_path: str):
        self.strategy_path = strategy_path
        self.strategy = self._load_strategy()
        self.metadata = self._extract_metadata()
        self.risk_profile = self._determine_risk_profile()
        self.neurometric_map = self._initialize_neurometrics()
        
    def _load_strategy(self):
        """Carga una estrategia existente desde su path"""
        module_name = os.path.splitext(os.path.basename(self.strategy_path))[0]
        spec = importlib.util.spec_from_file_location(module_name, self.strategy_path)
        strategy_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(strategy_module)
        return strategy_module

    def _extract_metadata(self) -> Dict:
        """Extrae metadatos clave de la estrategia"""
        return {
            "name": self.strategy.__name__,
            "description": getattr(self.strategy, '__doc__', 'Estrategia sin descripción'),
            "min_capital": getattr(self.strategy, 'MIN_CAPITAL', 50000),
            "expected_daily": getattr(self.strategy, 'EXPECTED_DAILY', 0.5),
            "backtest_period": getattr(self.strategy, 'BACKTEST_PERIOD', '2023-2026'),
            "symbols": getattr(self.strategy, 'SYMBOLS', ['QQQ', 'SPY']),
            "timeframe": getattr(self.strategy, 'TIMEFRAME', 'daily'),
            "version": getattr(self.strategy, 'VERSION', '1.0')
        }

    def _determine_risk_profile(self) -> str:
        """Determina el perfil de riesgo basado en parámetros de la estrategia"""
        # Analiza los parámetros de la estrategia para identificar riesgo
        risk_score = 0.0
        
        # Factores que incrementan el riesgo
        high_risk_indicators = [
            (self.metadata["expected_daily"] > 2.0, 0.8),
            (self.metadata["min_capital"] < 25000, 0.5),
            ('leverage' in self.strategy.__dict__ and self._get_attr('leverage') > 2.0, 0.7),
            ('stop_loss' in self.strategy.__dict__ and self._get_attr('stop_loss') < 0.02, 0.3)
        ]
        
        for indicator in high_risk_indicators:
            if indicator[0]:
                risk_score += indicator[1]
        
        # Ajustar por timeframe
        if self.metadata["timeframe"] == 'intraday':
            risk_score += 0.2
        
        # Mapeo al perfil de riesgo
        if risk_score < 0.3:
            return "LOW"
        elif risk_score < 0.7:
            return "MEDIUM"
        else:
            return "HIGH"

    def _get_attr(self, attr_name: str) -> Any:
        """Obtiene un atributo de la estrategia de manera segura"""
        try:
            return getattr(self.strategy, attr_name)
        except AttributeError:
            return None

    def _initialize_neurometrics(self) -> Dict:
        """Configura métricas neurológicas para esta estrategia"""
        return {
            "stress_threshold": 0.6,
            "frustration_threshold": 0.8,
            "cognitive_load": 0.5,
            "trust": 0.7,
            "bio_signals": {
                "alpha": 0.0,
                "beta": 0.0,
                "theta": 0.0
            }
        }

    def analyze_risk(self, bio_data: Optional[Dict] = None) -> Dict:
        """Analiza el riesgo con datos biológicos"""
        risk_level = self.risk_profile
        
        # Si hay datos biológicos, ajustar el riesgo
        if bio_data:
            bio_risk = {
                "neuro_adapted": False,
                "user_stress": bio_data.get("stress_level", 0.0),
                "risk_adjustment": 0.0
            }
            
            # Ajustar threshold de riesgo según estrés del usuario
            if bio_data["stress_level"] > self.neurometric_map["stress_threshold"]:
                bio_risk["neuro_adapted"] = True
                bio_risk["risk_adjustment"] = -0.2
                
                # Si hay frustración, bloquear ejecución
                if bio_data.get("frustration", 0.0) > self.neurometric_map["frustration_threshold"]:
                    return {
                        "final_risk_level": "BLOCKED",
                        "reason": "Alto estrés y frustración detectados",
                        **bio_risk
                    }
                            
            return {
                "final_risk_level": risk_level,
                "risk_score": self._calculate_risk_score(bio_data),
                **bio_risk
            }

        # Sin datos biológicos, solo reportar perfil estándar
        return {
            "final_risk_level": risk_level,
            "risk_score": self._calculate_risk_score(),
            "neuro_adapted": False
        }

    def _calculate_risk_score(self, bio_data: Optional[Dict] = None) -> float:
        """Calcula un score de riesgo detallado"""
        # Factores base de riesgo
        base_score = 0.0
        
        # Profundidad de backtest
        if '2022' not in self.metadata["backtest_period"]:
            base_score += 0.2
        
        # Tamaño del capital mínimo (menor capital = mayor riesgo)
        if self.metadata["min_capital"] < 10000:
            base_score += 0.3
        
        # Periodo de backtest
        try:
            start, end = map(int, self.metadata["backtest_period"].split('-'))
            if end - start < 3:
                base_score += 0.15
        except:
            pass
        
        # Ajuste por timeframe
        if self.metadata["timeframe"] == 'intraday':
            base_score += 0.2
        
        # Ajuste por volatilidad del símbolo
        if 'QQQ' in self.metadata["symbols"]:
            base_score += 0.1
        
        # Si hay datos biológicos, ajustar score
        if bio_data:
            # Ajustar por estrés del usuario
            if bio_data.get("stress_level", 0) > 0.7:
                base_score += 0.15
            
            # Ajustar por historia de ejecución (simulada)
            if bio_data.get("last_execution_failure", False):
                base_score += 0.1
        
        # Normalizar y devolver
        return min(1.0, max(0.0, base_score))

    def execute(self, capital: float, bio_data: Optional[Dict] = None) -> Dict:
        """Ejecuta la estrategia con gestión de riesgo y neuro-integración"""
        # 1. Análisis de riesgo con datos biológicos
        risk_analysis = self.analyze_risk(bio_data)
        
        # 2. Verificar si debe ejecutarse
        if risk_analysis["final_risk_level"] == "BLOCKED":
            return {
                "status": "CANCELED",
                "reason": risk_analysis["reason"],
                "bio_data": bio_data
            }
        
        # 3. Ejecutar la estrategia
        try:
            # Configurar parámetros
            if hasattr(self.strategy, 'set_parameters'):
                self.strategy.set_parameters(capital=capital)
            
            # Ejecutar estrategia
            if hasattr(self.strategy, 'run'):
                result = self.strategy.run()
            elif hasattr(self.strategy, 'main'):
                result = self.strategy.main()
            else:
                return {"status": "ERROR", "reason": "Método de ejecución no encontrado"}
            
            # 4. Procesar resultado
            return self._process_result(result, capital, risk_analysis)
            
        except Exception as e:
            return {
                "status": "ERROR",
                "reason": str(e),
                "bio_data": bio_data
            }

    def _process_result(self, result: Any, capital: float, risk_analysis: Dict) -> Dict:
        """Procesa el resultado de la estrategia y lo formatea"""
        # Extraer métricas relevantes
        metrics = {
            "capital_initial": capital,
            "capital_final": capital * (1 + risk_analysis.get("expected_return", 0.0)),
            "daily_return": risk_analysis.get("expected_daily", 0.0),
            "trade_count": getattr(result, 'trade_count', 0),
            "win_rate": getattr(result, 'win_rate', 0.0),
            "sharpe_ratio": getattr(result, 'sharpe_ratio', 0.0)
        }
        
        # Calcular resultado financiero
        metrics["profit"] = metrics["capital_final"] - metrics["capital_initial"]
        metrics["profit_pct"] = (metrics["profit"] / metrics["capital_initial"]) * 100
        
        return {
            "status": "SUCCESS",
            "strategy_name": self.metadata["name"],
            "timestamp": datetime.now().isoformat(),
            "metrics": metrics,
            "risk_analysis": {
                "initial_risk": self.risk_profile,
                "final_risk": risk_analysis["final_risk_level"],
                "neuro_adapted": risk_analysis["neuro_adapted"]
            }
        }

    def get_dashboard_info(self) -> Dict:
        """Proporciona información para el dashboard"""
        return {
            "strategy": self.metadata,
            "risk_profile": self.risk_profile,
            "neurometrics": {
                "stress_threshold": self.neurometric_map["stress_threshold"],
                "frustration_threshold": self.neurometric_map["frustration_threshold"]
            }
        }

# === EJEMPLO DE USO ===
if __name__ == "__main__":
    strategy_path = "C:/AI_VAULT/tmp_agent/strategies/mean_reversion_eq/run_phase49_normalized_gate_r015_2026-04-27.py"
    adapter = StrategyAdapter(strategy_path)
    
    # Simular datos biológicos
    bio_data = {
        "stress_level": 0.65,
        "frustration": 0.4,
        "alpha": 0.7,
        "beta": 3.2,
        "theta": 0.3
    }
    
    # Ejecutar y obtener resultado
    result = adapter.execute(capital=100000, bio_data=bio_data)
    print(json.dumps(result, indent=2))