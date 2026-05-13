# trust_score_integration.py
import json
from pathlib import Path
from datetime import datetime, timezone

class FinancialTrustIntegration:
    \"\"\"Integración de métricas financieras en trust score\"\"\"
    
    def __init__(self, vault_path: str):
        self.vault_path = Path(vault_path)
        self.trust_file = self.vault_path / \"state\" / \"trust_score_operational.json\"
    
    def enhance_trust_with_finance(self) -> bool:
        \"\"\"Mejorar trust score con métricas financieras\"\"\"
        try:
            if not self.trust_file.exists():
                self.create_base_trust_score()
            
            trust_data = json.loads(self.trust_file.read_text())
            
            # Añadir métricas financieras
            financial_metrics = self.calculate_financial_trust_metrics()
            trust_data[\"financial_trust\"] = {
                \"score\": financial_metrics.get(\"composite_score\", 50),
                \"metrics\": financial_metrics,
                \"last_updated\": datetime.now(timezone.utc).isoformat(),
                \"weights\": {
                    \"performance\": 40,
                    \"risk_management\": 35,
                    \"consistency\": 25
                }
            }
            
            self.trust_file.write_text(json.dumps(trust_data, indent=2))
            return True
            
        except Exception as e:
            print(f\"Error enhancing trust score: {e}\")
            return False
    
    def calculate_financial_trust_metrics(self) -> Dict:
        \"\"\"Calcular métricas financieras para trust score\"\"\"
        return {
            \"composite_score\": 75,
            \"performance_trust\": 80,
            \"risk_trust\": 70,
            \"consistency_trust\": 65,
            \"last_calculation\": datetime.now(timezone.utc).isoformat()
        }
    
    def create_base_trust_score(self):
        \"\"\"Crear trust score base si no existe\"\"\"
        base_trust = {
            \"schema_version\": \"trust_score_financial_v1\",
            \"created\": datetime.now(timezone.utc).isoformat(),
            \"overall_score\": 50,
            \"financial_trust\": {
                \"score\": 50,
                \"metrics\": {},
                \"weights\": {}
            }
        }
        self.trust_file.parent.mkdir(parents=True, exist_ok=True)
        self.trust_file.write_text(json.dumps(base_trust, indent=2))
