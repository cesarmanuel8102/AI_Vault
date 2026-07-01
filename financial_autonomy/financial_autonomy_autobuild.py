from pathlib import Path
import os
import time
import json
from typing import Dict

from financial_autonomy.bridge.financial_autonomy_bridge import FinancialAutonomyBridge
from financial_autonomy.bridge.trust_score_integration import FinancialTrustIntegration


class FinancialAutonomyAutobuild:
    """Sistema de autoconstruccion para integracion financiero-autonoma."""

    def __init__(self, vault_path: str | Path | None = None):
        self.vault_path = Path(vault_path or os.getenv("BRAIN_BASE_PATH", Path(__file__).resolve().parents[1]))
        self.module_path = self.vault_path / "financial_autonomy"
        self.bridge = FinancialAutonomyBridge(str(self.vault_path))
        self.trust_integrator = FinancialTrustIntegration(str(self.vault_path))

    def run_autobuild_cycle(self):
        """Ejecutar ciclo completo de autoconstruccion."""
        print("Iniciando ciclo de autoconstruccion financiero-autonoma...")

        if not self.verify_integration():
            print("Integracion no verificada; no se aplican reparaciones automaticas.")

        self.optimize_based_on_performance()
        self.update_financial_trust()
        self.generate_improvement_report()

        print("Ciclo de autoconstruccion completado")

    def verify_integration(self) -> bool:
        """Verificar que la integracion puede leer metricas sin broker real."""
        try:
            metrics = self.bridge.expose_financial_metrics()
            if "error" in metrics:
                return False
            return self.trust_integrator.enhance_trust_with_finance()
        except Exception as e:
            print(f"Error en verificacion: {e}")
            return False

    def optimize_based_on_performance(self):
        """Generar feedback de optimizacion sin ejecutar trades reales."""
        try:
            metrics = self.bridge.expose_financial_metrics()
            optimizations = self.generate_auto_optimizations(metrics)
            if optimizations:
                self.bridge.receive_autonomy_feedback(optimizations)
                print("Optimizaciones registradas")
        except Exception as e:
            print(f"Error en optimizacion automatica: {e}")

    def generate_auto_optimizations(self, metrics: Dict) -> Dict:
        """Generar sugerencias conservadoras basadas en metricas."""
        optimizations = {"parameters": {}, "risk": {}}
        sharpe = metrics.get("portfolio_performance", {}).get("sharpe", 0)
        if sharpe < 1.0:
            optimizations["parameters"]["aggressiveness"] = "review_required"
        return optimizations

    def update_financial_trust(self):
        """Actualizar trust score financiero local si el archivo existe/puede crearse."""
        self.trust_integrator.enhance_trust_with_finance()

    def generate_improvement_report(self):
        """Generar reporte local de automejora."""
        report_path = self.module_path / "reports" / f"autobuild_report_{int(time.time())}.json"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report = {
            "timestamp": time.time(),
            "cycle_type": "financial_autonomy",
            "improvements_applied": [],
            "performance_metrics": self.bridge.expose_financial_metrics(),
            "trust_score_updated": True,
            "real_money_enabled": False,
            "broker_execution_enabled": False,
        }
        report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")


if __name__ == "__main__":
    autobuild = FinancialAutonomyAutobuild()
    autobuild.run_autobuild_cycle()
