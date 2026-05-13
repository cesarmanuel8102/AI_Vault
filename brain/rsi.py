"""
Brain Chat V9 — RSIManager
Extraído de V8.0 / V7.2 (funcionaba correctamente).
Sistema de Retroalimentación Interna: brechas, fases, progreso.
"""
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List

from brain_v9.config import RSI_PATH


class RSIManager:
    def __init__(self):
        self.logger          = logging.getLogger("RSIManager")
        self.rsi_path        = RSI_PATH
        self.brechas_file    = self.rsi_path / "brechas.json"
        self.fases_file      = self.rsi_path / "fases.json"
        self.progreso_file   = self.rsi_path / "progreso.json"
        self.rsi_path.mkdir(parents=True, exist_ok=True)

    async def run_strategic_analysis(self) -> Dict:
        brechas  = await self.get_brechas()
        fases    = await self.get_phase_status()
        progreso = await self.get_progress_metrics()
        return {
            "timestamp":         datetime.now().isoformat(),
            "brechas_count":     len(brechas),
            "brechas_criticas":  len([b for b in brechas if b.get("prioridad") == "alta"]),
            "fases_activas":     fases.get("fases_activas", 0),
            "fases_completadas": fases.get("fases_completadas", []),
            "progreso_general":  progreso.get("porcentaje_total", 0),
            "recomendaciones":   self._recommendations(brechas, fases, progreso),
        }

    async def get_brechas(self) -> List[Dict]:
        try:
            if self.brechas_file.exists():
                data = json.loads(self.brechas_file.read_text(encoding="utf-8"))
                return self._prioritize(data.get("brechas", []))
            return []
        except Exception as e:
            self.logger.error("Error cargando brechas: %s", e)
            return []

    async def get_phase_status(self) -> Dict:
        try:
            if self.fases_file.exists():
                data = json.loads(self.fases_file.read_text(encoding="utf-8"))
            else:
                data = {"fases": [
                    {"id": "F1", "nombre": "Core Foundation",      "estado": "completada", "progreso": 100},
                    {"id": "F2", "nombre": "Advanced Tools",       "estado": "completada", "progreso": 100},
                    {"id": "F3", "nombre": "Trading Integration",  "estado": "completada", "progreso": 100},
                    {"id": "F4", "nombre": "Brain Integration",    "estado": "activa",     "progreso":  85},
                    {"id": "F5", "nombre": "Agent Loop (V9)",      "estado": "en_progreso","progreso":  40},
                ]}
            fases      = data.get("fases", [])
            activas    = [f for f in fases if f.get("estado") == "activa"]
            completadas= [f for f in fases if f.get("estado") == "completada"]
            return {
                "fases":             fases,
                "fases_activas":     len(activas),
                "fases_completadas": [f["id"] for f in completadas],
                "progreso_promedio": sum(f.get("progreso", 0) for f in fases) / max(len(fases), 1),
            }
        except Exception as e:
            self.logger.error("Error cargando fases: %s", e)
            return {"error": str(e)}

    async def get_progress_metrics(self) -> Dict:
        try:
            if self.progreso_file.exists():
                return json.loads(self.progreso_file.read_text(encoding="utf-8"))
            return {"porcentaje_total": 0, "nota": "Sin datos de progreso aún"}
        except Exception as e:
            return {"error": str(e)}

    def _prioritize(self, brechas: List[Dict]) -> List[Dict]:
        order = {"alta": 0, "media": 1, "baja": 2}
        return sorted(brechas, key=lambda b: order.get(b.get("prioridad", "baja"), 3))

    def _recommendations(self, brechas, fases, progreso) -> List[str]:
        recs = []
        criticas = [b for b in brechas if b.get("prioridad") == "alta"]
        if criticas:
            recs.append(f"Resolver {len(criticas)} brecha(s) crítica(s) de forma inmediata")
        prog = progreso.get("porcentaje_total", 0)
        if prog < 50:
            recs.append("Progreso general bajo — revisar hoja de ruta")
        if fases.get("fases_activas", 0) > 2:
            recs.append("Demasiadas fases activas simultáneamente — enfocarse")
        if not recs:
            recs.append("Sistema en buen estado — continuar plan de desarrollo")
        return recs
