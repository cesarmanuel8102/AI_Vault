from typing import Dict
import json
from datetime import datetime, timezone
from pathlib import Path


class FinancialAutonomyBridge:
    """Puente local entre sistema financiero y autonomia, sin broker real."""

    def __init__(self, vault_path: str):
        self.vault_path = Path(vault_path)
        self.financial_path = self.vault_path / "20_TRADING"
        self.brain_path = self.vault_path / "00_identity"
        self.integration_config = self.load_integration_config()

    def load_integration_config(self) -> Dict:
        """Cargar configuracion de integracion."""
        config_path = self.vault_path / "financial_autonomy" / "config" / "integration_config.json"
        if config_path.exists():
            raw = config_path.read_text(encoding="utf-8")
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                try:
                    data = json.loads(raw.replace('\\"', '"'))
                except json.JSONDecodeError:
                    data = {}
            if isinstance(data, dict):
                data["real_money_enabled"] = False
                data["broker_execution_enabled"] = False
                return data
        return {
            "auto_optimize": False,
            "risk_tolerance": "medium",
            "real_money_enabled": False,
            "broker_execution_enabled": False,
        }

    def expose_financial_metrics(self) -> Dict:
        """Exponer metricas financieras locales; no usa broker real."""
        try:
            return {
                "portfolio_performance": self.get_portfolio_performance(),
                "risk_metrics": self.get_risk_metrics(),
                "strategy_results": self.get_strategy_results(),
                "real_money_enabled": False,
                "broker_execution_enabled": False,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        except Exception as e:
            return {"error": str(e), "status": "financial_module_not_connected"}

    def get_portfolio_performance(self) -> Dict:
        """Obtener performance del portfolio desde artefactos locales cuando existan."""
        return {"sharpe": 0.0, "returns": 0.0, "drawdown": 0.0}

    def get_risk_metrics(self) -> Dict:
        """Obtener metricas de riesgo locales."""
        return {"var": 0.0, "volatility": 0.0, "max_drawdown": 0.0}

    def get_strategy_results(self) -> Dict:
        """Obtener resultados agregados de estrategias locales."""
        return {"status": "not_connected", "strategies": []}

    def receive_autonomy_feedback(self, optimization_suggestions: Dict) -> bool:
        """Registrar feedback autonomo sin ejecutar operaciones reales."""
        try:
            self.apply_parameter_optimization(optimization_suggestions.get("parameters", {}))
            self.adjust_risk_settings(optimization_suggestions.get("risk", {}))
            self.update_financial_trust_score(optimization_suggestions)
            return True
        except Exception as e:
            print(f"Error aplicando optimizacion: {e}")
            return False

    def apply_parameter_optimization(self, parameters: Dict):
        """Placeholder seguro: no modifica estrategias ni ejecuta trades."""
        return {"applied": False, "parameters": parameters, "reason": "dry_run_only"}

    def adjust_risk_settings(self, risk: Dict):
        """Placeholder seguro: no modifica riesgo operativo real."""
        return {"applied": False, "risk": risk, "reason": "dry_run_only"}

    def update_financial_trust_score(self, data: Dict):
        """Actualizar trust score local si existe; no toca broker ni trading."""
        trust_path = self.vault_path / "state" / "trust_score_operational.json"
        if trust_path.exists():
            trust_data = json.loads(trust_path.read_text(encoding="utf-8"))
            trust_data["financial_metrics"] = data.get("metrics", {})
            trust_path.write_text(json.dumps(trust_data, indent=2), encoding="utf-8")
