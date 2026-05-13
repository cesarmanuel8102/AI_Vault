#!/usr/bin/env python3
"""
Brain Chat V8.0 - Launcher Simplificado
Inicia el servidor HTTP primero, luego inicializa sistemas en background
"""

import uvicorn
import asyncio
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

if __name__ == "__main__":
    logger.info("Iniciando Brain Chat V8.0 en puerto 8090...")
    uvicorn.run(
        "brain_chat_v8:app",
        host="127.0.0.1",
        port=8090,
        log_level="info",
        reload=False
    )
