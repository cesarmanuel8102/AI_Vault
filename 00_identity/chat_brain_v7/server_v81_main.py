#!/usr/bin/env python3
"""
Brain Chat V8.1 Server - Punto de entrada principal
Inicia el servidor completo con todas las capacidades
"""

import sys
import uvicorn
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

if __name__ == "__main__":
    logger.info("=" * 60)
    logger.info("Brain Chat V8.1 COMPLETO - Iniciando servidor")
    logger.info("Puerto: 8090")
    logger.info("Endpoints: /health, /ui, /api/*")
    logger.info("=" * 60)
    
    uvicorn.run(
        "brain_chat_v8:app",
        host="127.0.0.1",
        port=8090,
        log_level="info",
        reload=False,
        access_log=True
    )
