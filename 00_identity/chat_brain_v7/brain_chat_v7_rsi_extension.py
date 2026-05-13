"""
Extension RSI para Brain Chat V7
Integra StrategicRSI con BrainChatV7 existente
"""

import sys
sys.path.insert(0, r'C:\AI_VAULT\00_identity\chat_brain_v7')

# Importar V7 base
from brain_chat_v7 import (
    BrainChatV7, ChatRequest, ChatResponse, 
    RequestMetrics, CONVERSATIONS_DIR, STATE_DIR,
    BRAIN_API, POCKET_BRIDGE, OPENAI_API_KEY,
    logger, time, datetime, asyncio, json, Path
)

# Importar RSI
from brain_chat_v7_2_strategic_rsi_aligned import (
    StrategicRSI, handle_strategic_rsi_query,
    StrategicObjective, OBJECTIVE_WEIGHTS
)

class BrainChatV7_RSI(BrainChatV7):
    """Brain Chat V7 con RSI Estrategico integrado"""
    
    def __init__(self):
        super().__init__()
        # Inicializar RSI
        self.strategic_rsi = StrategicRSI(self)
        logger.info("RSI Estrategico inicializado")
    
    def _analyze_intent(self, message: str):
        """Analisis extendido con comandos RSI"""
        msg_lower = message.lower().strip()
        
        # Comandos RSI
        if any(phrase in msg_lower for phrase in [
            "rsi", "rsi estrategico", "mejora", "improvement", 
            "brechas", "brechas estrategicas", "weaknesses",
            "auto-mejora", "recursive", "como puedes mejorar",
            "fase", "progreso", "objetivo", "camino critico",
            "prioridad", "plan estrategico"
        ]):
            return {"type": "strategic_rsi", "needs_data": False, "risk": "low"}
        
        # Delegar al analisis original
        return super()._analyze_intent(message)
    
    async def process_message(self, request: ChatRequest):
        """Procesa mensajes incluyendo comandos RSI"""
        
        # Detectar comandos RSI
        msg_lower = request.message.lower()
        if any(x in msg_lower for x in ['rsi', 'brechas', 'fase', 'progreso', 'plan estrategico']):
            return await self._handle_rsi_command(request)
        
        # Delegar al procesamiento original
        return await super().process_message(request)
    
    async def _handle_rsi_command(self, request: ChatRequest):
        """Maneja comandos RSI"""
        try:
            # Forzar ciclo RSI
            report = await self.strategic_rsi.run_strategic_rsi_cycle(force=True)
            
            # Generar respuesta
            reply = await self._generate_rsi_response(report)
            
            return ChatResponse(
                success=True,
                reply=reply,
                mode="strategic_rsi",
                data_source="rsi_system",
                verified=True,
                confidence=0.95
            )
        except Exception as e:
            logger.error(f"Error en RSI: {e}")
            return ChatResponse(
                success=False,
                reply=f"Error en analisis RSI: {str(e)}",
                mode="error"
            )
    
    async def _generate_rsi_response(self, report: dict) -> str:
        """Genera respuesta formateada del RSI"""
        
        reply = f"""RSI Estrategico - Ciclo #{report.get('cycle_number', 0)}

Fase Actual: {report.get('fase_actual', 'N/A').upper()}
Dia: {report.get('dias_en_fase', 0)} | Progreso: {report.get('progreso_fase', 0):.1f}%
Deadline: {report.get('time_to_deadline', 'N/A')} dias

PROXIMO GATE:
{report.get('proximo_gate', 'N/A')}

BRECHAS ESTRATEGICAS:
"""
        
        gaps = report.get('strategic_gaps', [])
        for gap in gaps[:4]:
            status = "OK" if gap.get('gap_percentage', 100) < 10 else "!" if gap.get('gap_percentage', 100) < 30 else "X"
            reply += f"""
[{status}] {gap.get('objective', 'N/A').replace('_', ' ').title()}
   Actual: {gap.get('current_capability', 0):.1f}% / Requerido: {gap.get('required_capability', 0):.1f}%
   Brecha: {gap.get('gap_percentage', 0):.1f}% | Impacto: {gap.get('impact_on_objective', 'N/A')}
"""
            if gap.get('blockers'):
                reply += f"   Bloqueantes: {', '.join(gap['blockers'][:2])}\n"
        
        # Riesgos
        risks = report.get('ruina_risks', [])
        if risks:
            reply += f"""

RIESGOS DETECTADOS: {len(risks)}
"""
            for risk in risks[:2]:
                reply += f"""
! {risk.get('type', 'Riesgo').upper()}: {risk.get('description', 'N/A')}
   Accion: {risk.get('action', 'Investigar')}
"""
        
        # Plan
        plan = report.get('strategic_plan', {})
        reply += f"""

PLAN ESTRATEGICO:
Fase: {plan.get('phase', 'N/A')}
Enfoque: {plan.get('primary_focus', 'N/A')}
Timeline: {plan.get('timeline', 'N/A')}

Acciones:
"""
        for action in plan.get('actions', [])[:3]:
            reply += f"\n{action}"
        
        # Recomendaciones
        recs = report.get('recommendations', [])
        if recs:
            reply += f"""

RECOMENDACIONES:
"""
            for rec in recs[:3]:
                reply += f"\n* {rec}"
        
        if report.get('safe_mode_triggered'):
            reply += "\n\n!!! MODO SEGURO ACTIVADO - Requiere atencion"
        
        return reply

# Crear instancia global
chat_v7_rsi = None

print("Modulo RSI cargado. Esperando inicializacion...")
