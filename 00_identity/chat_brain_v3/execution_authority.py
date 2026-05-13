"""
Sistema de Autorización Inteligente para Chat-Brain V3
Autoriza operaciones por niveles de riesgo
"""

from pathlib import Path
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
from enum import Enum
import hashlib
import secrets
import time


class OperationLevel(Enum):
    """Niveles de operación por riesgo"""
    CONSULTA = 0      # Sin autorización
    EJECUCION = 1     # Sin autorización (bajo premisas)
    CRITICO = 2       # Requiere confirmación


@dataclass
class OperationClassification:
    """Clasificación de una operación"""
    level: OperationLevel
    requires_auth: bool
    reason: str
    risk_factors: List[str]


class ExecutionAuthority:
    """
    Autoridad de ejecución que clasifica operaciones
    y determina si requieren autorización
    """
    
    # Paths críticos que requieren autorización
    CRITICAL_PATHS = [
        '00_identity/',
        '10_FINANCIAL/core/',
        '20_INFRASTRUCTURE/security/',
        '.secrets/',
        'policy/',
    ]
    
    # Operaciones que siempre requieren autorización
    CRITICAL_OPERATIONS = [
        'delete', 'remove', 'rm',
        'exec', 'system', 'cmd',
        'chmod', 'chown',
        'modify_core', 'patch_system',
    ]
    
    # Operaciones de solo lectura (nivel 0)
    READ_OPERATIONS = [
        'read', 'list', 'get', 'show', 'display',
        'cat', 'ls', 'find', 'grep',
        'status', 'info', 'query',
    ]
    
    def __init__(self):
        self.pending_authorizations: Dict[str, Dict] = {}
        self.authorization_codes: Dict[str, str] = {}
        self.executed_commands: List[Dict] = []
    
    def classify_operation(self, command: str, target: str, 
                          params: Optional[Dict] = None) -> OperationClassification:
        """
        Clasifica una operación según su nivel de riesgo
        
        Args:
            command: Comando a ejecutar
            target: Objetivo del comando (archivo, path, etc.)
            params: Parámetros adicionales
            
        Returns:
            OperationClassification con nivel y requisitos
        """
        command_lower = command.lower()
        target_lower = str(target).lower() if target else ""
        
        # 1. Verificar si es operación de lectura
        if any(op in command_lower for op in self.READ_OPERATIONS):
            return OperationClassification(
                level=OperationLevel.CONSULTA,
                requires_auth=False,
                reason="Operación de solo lectura",
                risk_factors=[]
            )
        
        # 2. Verificar operaciones críticas explícitas
        if any(op in command_lower for op in self.CRITICAL_OPERATIONS):
            risk_factors = ["Operación destructiva o de sistema"]
            if target:
                risk_factors.append(f"Objetivo: {target}")
            
            return OperationClassification(
                level=OperationLevel.CRITICO,
                requires_auth=True,
                reason="Operación crítica detectada",
                risk_factors=risk_factors
            )
        
        # 3. Verificar paths críticos
        for critical_path in self.CRITICAL_PATHS:
            if critical_path.lower() in target_lower:
                return OperationClassification(
                    level=OperationLevel.CRITICO,
                    requires_auth=True,
                    reason=f"Acceso a path crítico: {critical_path}",
                    risk_factors=[
                        "Modificación de componentes core del sistema",
                        "Requiere confirmación para prevenir daños"
                    ]
                )
        
        # 4. Verificar si es en room (seguro)
        if 'room' in target_lower or 'tmp_agent/state/rooms' in target_lower:
            return OperationClassification(
                level=OperationLevel.EJECUCION,
                requires_auth=False,
                reason="Operación en room (espacio de trabajo seguro)",
                risk_factors=[]
            )
        
        # 5. Por defecto: ejecución estándar
        return OperationClassification(
            level=OperationLevel.EJECUCION,
            requires_auth=False,
            reason="Operación estándar",
            risk_factors=[]
        )
    
    def requires_authorization(self, command: str, target: str) -> bool:
        """Determina rápidamente si requiere autorización"""
        classification = self.classify_operation(command, target)
        return classification.requires_auth
    
    def generate_authorization_code(self, command: str, target: str, 
                                   user_id: Optional[str] = None) -> str:
        """
        Genera código de autorización para operación crítica
        
        Returns:
            Código único de 8 caracteres alfanuméricos
        """
        # Crear hash único
        data = f"{command}:{target}:{user_id}:{time.time()}"
        hash_obj = hashlib.sha256(data.encode())
        
        # Generar código de 8 caracteres
        code = secrets.token_hex(4).upper()  # 8 caracteres hex
        
        # Guardar código pendiente
        self.pending_authorizations[code] = {
            'command': command,
            'target': target,
            'user_id': user_id,
            'timestamp': time.time(),
            'attempts': 0
        }
        
        return code
    
    def verify_authorization_code(self, code: str, 
                                  command: str, target: str) -> Tuple[bool, str]:
        """
        Verifica código de autorización
        
        Returns:
            (bool: válido, str: mensaje)
        """
        code = code.upper().strip()
        
        # Verificar si existe
        if code not in self.pending_authorizations:
            return False, "Código de autorización inválido o expirado"
        
        auth_data = self.pending_authorizations[code]
        
        # Verificar expiración (5 minutos)
        if time.time() - auth_data['timestamp'] > 300:
            del self.pending_authorizations[code]
            return False, "Código de autorización expirado (5 minutos)"
        
        # Verificar intentos (máximo 3)
        if auth_data['attempts'] >= 3:
            del self.pending_authorizations[code]
            return False, "Demasiados intentos fallidos. Genere nuevo código."
        
        # Verificar coincidencia de comando
        if auth_data['command'] != command:
            auth_data['attempts'] += 1
            return False, f"Código no válido para este comando. Intentos restantes: {3 - auth_data['attempts']}"
        
        # Éxito - limpiar
        del self.pending_authorizations[code]
        return True, "Autorización verificada exitosamente"
    
    def log_execution(self, command: str, target: str, user_id: str,
                     authorized: bool, success: bool, result: str):
        """Registra ejecución en auditoría"""
        self.executed_commands.append({
            'timestamp': time.time(),
            'command': command,
            'target': target,
            'user_id': user_id,
            'authorized': authorized,
            'success': success,
            'result': result[:500] if result else None  # Truncar resultados largos
        })
    
    def get_pending_operations(self) -> List[Dict]:
        """Obtiene operaciones pendientes de autorización"""
        current_time = time.time()
        pending = []
        
        for code, data in list(self.pending_authorizations.items()):
            # Limpiar expirados
            if current_time - data['timestamp'] > 300:
                del self.pending_authorizations[code]
                continue
            
            pending.append({
                'code': code,
                'command': data['command'],
                'target': data['target'],
                'time_remaining': int(300 - (current_time - data['timestamp']))
            })
        
        return pending
    
    def cancel_operation(self, code: str) -> bool:
        """Cancela operación pendiente"""
        code = code.upper().strip()
        if code in self.pending_authorizations:
            del self.pending_authorizations[code]
            return True
        return False


# Instancia global
authority = ExecutionAuthority()
