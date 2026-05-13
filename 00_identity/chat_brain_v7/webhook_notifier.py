#!/usr/bin/env python3
"""
Sistema de Webhooks
Envía notificaciones a URLs externas
"""

import json
import urllib.request
from datetime import datetime
from typing import Dict


class WebhookNotifier:
    """Envía notificaciones vía webhooks"""
    
    def __init__(self):
        self.webhooks: Dict[str, str] = {}
    
    def register(self, name: str, url: str):
        """Registra un webhook"""
        self.webhooks[name] = url
    
    def notify(self, webhook_name: str, event_type: str, data: Dict) -> bool:
        """Envía notificación"""
        if webhook_name not in self.webhooks:
            return False
        
        url = self.webhooks[webhook_name]
        
        payload = {
            "event": event_type,
            "timestamp": datetime.now().isoformat(),
            "data": data
        }
        
        try:
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode(),
                headers={"Content-Type": "application/json"},
                method="POST"
            )
            
            with urllib.request.urlopen(req, timeout=5) as response:
                return response.status == 200
        except Exception as e:
            print(f"[Webhook] Error enviando a {webhook_name}: {e}")
            return False
    
    def notify_task_completed(self, task_id: str, success: bool, result: Dict):
        """Notifica tarea completada"""
        self.notify("default", "task_completed", {
            "task_id": task_id,
            "success": success,
            "result": result
        })


if __name__ == "__main__":
    notifier = WebhookNotifier()
    
    # Ejemplo (no enviará nada sin webhook configurado)
    notifier.register("default", "http://example.com/webhook")
    print("Webhook registrado")
