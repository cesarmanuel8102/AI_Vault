# __init__.py - Financial Autonomy package
"""Financial Autonomy Module."""

from .bridge.financial_autonomy_bridge import FinancialAutonomyBridge
from .bridge.trust_score_integration import FinancialTrustIntegration

__version__ = "1.0.0"
__all__ = ["FinancialAutonomyBridge", "FinancialTrustIntegration"]
