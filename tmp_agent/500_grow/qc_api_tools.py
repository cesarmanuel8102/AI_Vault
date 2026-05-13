# qc_api_tools.py
from quantconnect import ApiClient
import json

class QCAPIWrapper:
    """
    API wrapper para operar con QC en Paper Live
    """

    def __init__(self, token):
        self.token = token
        self.base_url = "https://www.quantconnect.com/api/v2"
        self.headers = self._create_headers()
    
    def _create_headers(self):
        """
        Crea headers con autenticación SHA-256 para QC API
        """
        timestamp = str(int(time.time()))
        token_hash = hashlib.sha256(f"{self.token}:{timestamp}".encode()).hexdigest()
        b64 = base64.b64encode(f"{USER_ID}:{token_hash}".encode()).decode()
        return {
            "Authorization": f"Basic {b64}",
            "Timestamp": timestamp,
            "Content-Type": "application/json"
        }

    def deploy_live(self, project_id, strategy_name, capital=500):
        """
        Despliega la estrategia en Paper Live
        """
        payload = {
            "projectId": project_id,
            "compileId": "latest",
            "name": strategy_name,
            "parameters": {
                "initial_capital": capital
            }
        }
        response = requests.post(
            f"{self.base_url}/live/create",
            headers=self.headers,
            json=payload
        )
        return response.json()

    def get_live_metrics(self, deployment_id):
        """
        Obtiene métricas en tiempo real del deployment
        """
        response = requests.get(
            f"{self.base_url}/live/read?liveId={deployment_id}",
            headers=self.headers
        )
        return response.json()

    def update_parameters(self, deployment_id, new_params):
        """
        Actualiza parámetros en tiempo real
        """
        payload = {
            "deploymentId": deployment_id,
            "parameters": new_params
        }
        requests.put(
            f"{self.base_url}/live/update",
            headers=self.headers,
            json=payload
        )

    def trigger_alert(self, message):
        """
        Registra alertas del sistema
        """
        payload = {
            "type": "info",
            "message": message
        }
        requests.post(
            f"{self.base_url}/alerts",
            headers=self.headers,
            json=payload
        )

    def reoptimize_parameters(self, deployment_id, new_params):
        """
        Punto de entrada para ajustes automáticos
        """
        return self.update_parameters(deployment_id, new_params)