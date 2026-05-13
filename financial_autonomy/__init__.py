# __init__.py - Para que Python reconozca el módulo
"""Financial Autonomy Module"""
from .financial_autonomy_bridge import FinancialAutonomyBridge
from .trust_score_integration import FinancialTrustIntegration

__version__ = "1.0.0"
__all__ = ["FinancialAutonomyBridge", "FinancialTrustIntegration"]
