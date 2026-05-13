#!/usr/bin/env python3
"""
LIMPIAR_EMOJIS.PY
Limpia caracteres Unicode problematicos de archivos Python
"""

import re
import sys

# Mapeo de emojis a reemplazos ASCII
EMOJI_MAP = {
    '✅': '[OK]',
    '✓': '[OK]',
    '❌': '[ERROR]',
    '✗': '[ERROR]',
    '⚠️': '[ADVERTENCIA]',
    '⚠': '[ADVERTENCIA]',
    '🔒': '[CERRADO]',
    '🔓': '[ABIERTO]',
    '🚀': '[EJECUTANDO]',
    '→': '->',
    '🔐': '[SEGURIDAD]',
    '🔑': '[LLAVE]',
}

def limpiar_archivo(filepath):
    """Limpia emojis de un archivo"""
    with open(filepath, 'r', encoding='utf-8') as f:
        contenido = f.read()
    
    # Reemplazar emojis
    for emoji, reemplazo in EMOJI_MAP.items():
        contenido = contenido.replace(emoji, reemplazo)
    
    # Guardar
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(contenido)
    
    print(f"Archivo limpiado: {filepath}")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        limpiar_archivo(sys.argv[1])
    else:
        # Limpiar archivos PAD
        limpiar_archivo('C:/AI_VAULT/brain/protocolo_autenticacion_desarrollador.py')
        limpiar_archivo('C:/AI_VAULT/brain/brain_v3_chat_autenticado.py')