# financial_endpoints.py - Versión corregida con imports correctos
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Dict, Any, Optional

from financial_autonomy.financial_autonomy_bridge import FinancialAutonomyBridge
from financial_autonomy.trust_score_integration import FinancialTrustIntegration

router = APIRouter(prefix="/financial-autonomy", tags=["financial-autonomy"])

class OptimizationRequest(BaseModel):
    parameters: Dict[str, Any]
    risk_settings: Optional[Dict[str, Any]] = None
    objective_function: str = "U = log_growth - risk_penalty"

class FinancialMetricsResponse(BaseModel):
    portfolio_performance: Dict[str, float]
    risk_metrics: Dict[str, float]
    autonomy_integration: Dict[str, Any]
    timestamp: str

# Instanciar bridge
bridge = FinancialAutonomyBridge("C:\\AI_VAULT")
trust_integrator = FinancialTrustIntegration("C:\\AI_VAULT")

@router.get("/metrics", response_model=FinancialMetricsResponse)
async def get_financial_metrics():
    """Obtener métricas financieras para autonomía"""
    try:
        metrics = bridge.expose_financial_metrics()
        return FinancialMetricsResponse(
            portfolio_performance=metrics.get("portfolio_performance", {}),
            risk_metrics=metrics.get("risk_metrics", {}),
            autonomy_integration={"status": "active", "version": "1.0"},
            timestamp=metrics.get("timestamp", "")
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error obteniendo métricas: {str(e)}")

@router.post("/optimize")
async def apply_autonomy_optimization(request: OptimizationRequest):
    """Aplicar optimizaciones sugeridas por autonomía"""
    try:
        success = bridge.receive_autonomy_feedback({
            "parameters": request.parameters,
            "risk": request.risk_settings,
            "objective": request.objective_function
        })
        
        return {"status": "success" if success else "failed", "action": "optimization_applied"}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error aplicando optimización: {str(e)}")

@router.get("/trust-score")
async def get_financial_trust():
    """Obtener trust score financiero"""
    try:
        trust_data = trust_integrator.calculate_financial_trust_metrics()
        return {"financial_trust": trust_data, "integration_status": "active"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error obteniendo trust score: {str(e)}")
