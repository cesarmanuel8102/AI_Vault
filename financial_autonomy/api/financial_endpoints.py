# financial_endpoints.py - read-only/dry-run financial autonomy API surface
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from financial_autonomy.bridge.financial_autonomy_bridge import FinancialAutonomyBridge
from financial_autonomy.bridge.trust_score_integration import FinancialTrustIntegration

router = APIRouter(prefix="/financial-autonomy", tags=["financial-autonomy"])


def _vault_path() -> Path:
    return Path(os.getenv("BRAIN_BASE_PATH", Path(__file__).resolve().parents[2]))


class OptimizationRequest(BaseModel):
    parameters: Dict[str, Any]
    risk_settings: Optional[Dict[str, Any]] = None
    objective_function: str = "U = log_growth - risk_penalty"


class FinancialMetricsResponse(BaseModel):
    portfolio_performance: Dict[str, float]
    risk_metrics: Dict[str, float]
    autonomy_integration: Dict[str, Any]
    timestamp: str


bridge = FinancialAutonomyBridge(str(_vault_path()))
trust_integrator = FinancialTrustIntegration(str(_vault_path()))


@router.get("/metrics", response_model=FinancialMetricsResponse)
async def get_financial_metrics():
    """Obtener metricas financieras locales para autonomia; no usa broker real."""
    try:
        metrics = bridge.expose_financial_metrics()
        return FinancialMetricsResponse(
            portfolio_performance=metrics.get("portfolio_performance", {}),
            risk_metrics=metrics.get("risk_metrics", {}),
            autonomy_integration={
                "status": "dry_run_local",
                "version": "1.0",
                "real_money_enabled": False,
                "broker_execution_enabled": False,
            },
            timestamp=metrics.get("timestamp", ""),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error obteniendo metricas: {str(e)}")


@router.post("/optimize")
async def apply_autonomy_optimization(request: OptimizationRequest):
    """Registrar optimizaciones sugeridas por autonomia sin ejecutar trades."""
    try:
        success = bridge.receive_autonomy_feedback({
            "parameters": request.parameters,
            "risk": request.risk_settings or {},
            "objective": request.objective_function,
        })
        return {
            "status": "success" if success else "failed",
            "action": "optimization_recorded_dry_run",
            "real_money_enabled": False,
            "broker_execution_enabled": False,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error aplicando optimizacion: {str(e)}")


@router.get("/trust-score")
async def get_financial_trust():
    """Obtener trust score financiero calculado localmente."""
    try:
        trust_data = trust_integrator.calculate_financial_trust_metrics()
        return {
            "financial_trust": trust_data,
            "integration_status": "dry_run_local",
            "real_money_enabled": False,
            "broker_execution_enabled": False,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error obteniendo trust score: {str(e)}")
