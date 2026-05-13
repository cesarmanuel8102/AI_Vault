#!/usr/bin/env python3
"""
Exportación de Métricas - CSV y JSON
Permite exportar datos del agente para análisis externo
"""

import json
import csv
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any


class MetricsExporter:
    """Exportador de métricas del agente"""
    
    def __init__(self, export_dir: str = None):
        if export_dir is None:
            export_dir = "C:/AI_VAULT/tmp_agent/exports"
        self.export_dir = Path(export_dir)
        self.export_dir.mkdir(parents=True, exist_ok=True)
    
    def export_to_json(self, data: Dict, filename: str = None) -> str:
        """Exporta datos a JSON"""
        if filename is None:
            filename = f"metrics_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        
        filepath = self.export_dir / filename
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        
        return str(filepath)
    
    def export_to_csv(self, data: List[Dict], filename: str = None) -> str:
        """Exporta datos a CSV"""
        if filename is None:
            filename = f"metrics_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        
        filepath = self.export_dir / filename
        
        if not data:
            return str(filepath)
        
        with open(filepath, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=data[0].keys())
            writer.writeheader()
            writer.writerows(data)
        
        return str(filepath)
    
    def export_conversations(self, conversations: List[Dict]) -> str:
        """Exporta historial de conversaciones"""
        return self.export_to_json({
            "export_type": "conversations",
            "timestamp": datetime.now().isoformat(),
            "count": len(conversations),
            "data": conversations
        }, "conversations_export.json")
    
    def export_metrics_summary(self, metrics: Dict) -> str:
        """Exporta resumen de métricas"""
        return self.export_to_json({
            "export_type": "metrics_summary",
            "timestamp": datetime.now().isoformat(),
            "metrics": metrics
        }, "metrics_summary.json")


if __name__ == "__main__":
    # Test
    exporter = MetricsExporter()
    
    # Test JSON
    data = {"test": True, "value": 123}
    path = exporter.export_to_json(data)
    print(f"Exportado JSON: {path}")
    
    # Test CSV
    csv_data = [
        {"name": "test1", "value": 1},
        {"name": "test2", "value": 2}
    ]
    path = exporter.export_to_csv(csv_data)
    print(f"Exportado CSV: {path}")
