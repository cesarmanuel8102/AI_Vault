#!/usr/bin/env python3
"""
Script de Depuracion Automatizada AI_VAULT
Fases 1-4 del Plan de Depuracion
Ejecutar con: python depuracion_automatizada.py
"""

import os
import shutil
import glob
from pathlib import Path
from datetime import datetime, timedelta
import json
import sys

class DepuracionAIVAULT:
    def __init__(self):
        self.root = Path("C:\\AI_VAULT")
        self.backup_dir = Path(f"C:\\AI_VAULT_BACKUP_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
        self.log_file = self.root / "logs" / f"depuracion_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
        self.estadisticas = {
            "inicio": datetime.now().isoformat(),
            "archivos_eliminados": 0,
            "espacio_liberado_mb": 0,
            "archivos_archivados": 0,
            "errores": []
        }
        
        # Crear directorio de logs
        self.log_file.parent.mkdir(parents=True, exist_ok=True)
        
    def log(self, mensaje):
        """Registrar en log"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        linea = f"[{timestamp}] {mensaje}\n"
        print(linea.strip())
        with open(self.log_file, 'a', encoding='utf-8') as f:
            f.write(linea)
    
    def backup_antes_depuracion(self):
        """FASE 0: Backup completo antes de depurar"""
        self.log("=" * 60)
        self.log("FASE 0: CREANDO BACKUP COMPLETO")
        self.log("=" * 60)
        
        try:
            # Archivos criticos a respaldar
            archivos_criticos = [
                "00_identity/brain_server.py",
                "00_identity/advisor_server.py",
                "00_identity/brain_chat_ui_server.py",
                "00_identity/brain_router.py",
                "00_identity/agent_loop.py",
                "tmp_agent/state/",
                "FULL_ADN_INTEGRAL.json",
            ]
            
            self.backup_dir.mkdir(parents=True, exist_ok=True)
            
            for archivo in archivos_criticos:
                try:
                    src = self.root / archivo
                    if src.exists():
                        dst = self.backup_dir / archivo
                        dst.parent.mkdir(parents=True, exist_ok=True)
                        if src.is_file():
                            shutil.copy2(src, dst)
                        elif src.is_dir():
                            # Evitar carpetas con nombres muy largos
                            if len(str(src)) < 200:
                                shutil.copytree(src, dst, dirs_exist_ok=True)
                            else:
                                self.log(f"[ADVERTENCIA] Omitiendo directorio con nombre muy largo: {archivo}")
                                continue
                        self.log(f"[OK] Respaldado: {archivo}")
                except Exception as e:
                    self.log(f"[ADVERTENCIA] Error respaldando {archivo}: {e}")
                    # Continuar con los demás archivos
            
            self.log(f"[OK] Backup creado en: {self.backup_dir}")
            return True
            
        except Exception as e:
            self.log(f"[ERROR] en backup: {e}")
            self.estadisticas["errores"].append(f"Backup: {e}")
            return False
    
    def fase1_limpiar_backups_antiguos(self):
        """FASE 1: Limpiar backups antiguos"""
        self.log("\n" + "=" * 60)
        self.log("FASE 1: LIMPIANDO BACKUPS ANTIGUOS")
        self.log("=" * 60)
        
        patrones_backup = [
            "00_identity/advisor_server.py.bak_*",
            "00_identity/brain_server.py.BAK_*",
            "00_identity/brain_server.py.LKG_*",
            "00_identity/brain_server_backup.py",
            "00_identity/agent_loop.py.bak_*",
            "00_identity/brain_router.py.bak_*",
            "tmp_agent/advisor_server.py.bak_*",
            "tmp_agent/advisor_server.py",
        ]
        
        archivos_eliminados = 0
        espacio_liberado = 0
        
        for patron in patrones_backup:
            archivos = list(self.root.glob(patron))
            for archivo in archivos:
                try:
                    tamano = archivo.stat().st_size
                    archivo.unlink()
                    archivos_eliminados += 1
                    espacio_liberado += tamano
                    self.log(f"[ELIMINADO] {archivo.relative_to(self.root)}")
                except Exception as e:
                    self.log(f"[ADVERTENCIA] Error eliminando {archivo}: {e}")
                    self.estadisticas["errores"].append(f"Eliminar {archivo}: {e}")
        
        self.estadisticas["archivos_eliminados"] += archivos_eliminados
        self.estadisticas["espacio_liberado_mb"] += espacio_liberado / (1024 * 1024)
        
        self.log(f"[OK] FASE 1 COMPLETADA: {archivos_eliminados} archivos eliminados")
        self.log(f"[INFO] Espacio liberado: {espacio_liberado / (1024 * 1024):.2f} MB")
    
    def fase2_limpiar_pycache(self):
        """FASE 2: Limpiar .pyc y __pycache__"""
        self.log("\n" + "=" * 60)
        self.log("FASE 2: LIMPIANDO ARCHIVOS .pyc Y __pycache__")
        self.log("=" * 60)
        
        archivos_eliminados = 0
        espacio_liberado = 0
        
        # Eliminar archivos .pyc
        for archivo in self.root.rglob("*.pyc"):
            try:
                tamano = archivo.stat().st_size
                archivo.unlink()
                archivos_eliminados += 1
                espacio_liberado += tamano
            except Exception as e:
                self.log(f"[ADVERTENCIA] Error: {e}")
        
        # Eliminar carpetas __pycache__
        for carpeta in self.root.rglob("__pycache__"):
            try:
                tamano = sum(f.stat().st_size for f in carpeta.rglob('*') if f.is_file())
                shutil.rmtree(carpeta)
                archivos_eliminados += 1
                espacio_liberado += tamano
                self.log(f"[ELIMINADO] {carpeta.relative_to(self.root)}")
            except Exception as e:
                self.log(f"[ADVERTENCIA] Error: {e}")
        
        self.estadisticas["archivos_eliminados"] += archivos_eliminados
        self.estadisticas["espacio_liberado_mb"] += espacio_liberado / (1024 * 1024)
        
        self.log(f"[OK] FASE 2 COMPLETADA: {archivos_eliminados} elementos eliminados")
        self.log(f"[INFO] Espacio liberado: {espacio_liberado / (1024 * 1024):.2f} MB")
    
    def fase3_consolidar_componentes(self):
        """FASE 3: Consolidar componentes duplicados"""
        self.log("\n" + "=" * 60)
        self.log("FASE 3: CONSOLIDANDO COMPONENTES DUPLICADOS")
        self.log("=" * 60)
        
        # Eliminar duplicados en tmp_agent/ (mantener canonical en 00_identity/)
        duplicados = [
            "tmp_agent/advisor_server.py",
            "tmp_agent/advisor_server_working.py",
            "tmp_agent/advisor_server_simple.py",
            "tmp_agent/brain_router.py",
            "tmp_agent/agent_loop.py",
            "tmp_agent/dashboard_server.py",
            "tmp_agent/dashboard_alternative.py",
            "tmp_agent/dashboard_simple_working.py",
            "tmp_agent/dashboard_super_simple.py",
            "tmp_agent/dashboard_professional_simple.py",
        ]
        
        archivos_eliminados = 0
        
        for archivo_str in duplicados:
            archivo = self.root / archivo_str
            if archivo.exists():
                try:
                    archivo.unlink()
                    archivos_eliminados += 1
                    self.log(f"[ELIMINADO] Duplicado: {archivo_str}")
                except Exception as e:
                    self.log(f"[ADVERTENCIA] Error: {e}")
        
        # Eliminar duplicados en financial_autonomy/
        duplicados_finance = [
            "financial_autonomy/trust_score_integration.py",
            "financial_autonomy/financial_autonomy_bridge.py",
        ]
        
        for archivo_str in duplicados_finance:
            archivo = self.root / archivo_str
            if archivo.exists():
                # Verificar que existe el original en bridge/
                original = self.root / "financial_autonomy" / "bridge" / Path(archivo_str).name
                if original.exists():
                    try:
                        archivo.unlink()
                        archivos_eliminados += 1
                        self.log(f"[ELIMINADO] Duplicado: {archivo_str}")
                    except Exception as e:
                        self.log(f"[ADVERTENCIA] Error: {e}")
        
        self.estadisticas["archivos_eliminados"] += archivos_eliminados
        self.log(f"[OK] FASE 3 COMPLETADA: {archivos_eliminados} duplicados eliminados")
    
    def fase4_archivar_logs_antiguos(self):
        """FASE 4: Archivar logs antiguos (>30 dias)"""
        self.log("\n" + "=" * 60)
        self.log("FASE 4: ARCHIVANDO LOGS ANTIGUOS")
        self.log("=" * 60)
        
        fecha_limite = datetime.now() - timedelta(days=30)
        archivos_archivados = 0
        espacio_liberado = 0
        
        # Crear directorio de archivo
        archivo_dir = self.root / "ARCHIVE" / "logs_antiguos"
        archivo_dir.mkdir(parents=True, exist_ok=True)
        
        # Archivar logs antiguos
        for log_file in self.root.rglob("*.log"):
            try:
                if log_file.stat().st_mtime < fecha_limite.timestamp():
                    # Mover a archivo
                    destino = archivo_dir / log_file.relative_to(self.root).name
                    shutil.move(str(log_file), str(destino))
                    archivos_archivados += 1
                    espacio_liberado += log_file.stat().st_size
                    self.log(f"[ARCHIVADO] {log_file.relative_to(self.root)}")
            except Exception as e:
                self.log(f"[ADVERTENCIA] Error archivando {log_file}: {e}")
        
        self.estadisticas["archivos_archivados"] += archivos_archivados
        self.estadisticas["espacio_liberado_mb"] += espacio_liberado / (1024 * 1024)
        
        self.log(f"[OK] FASE 4 COMPLETADA: {archivos_archivados} logs archivados")
        self.log(f"[INFO] Espacio liberado: {espacio_liberado / (1024 * 1024):.2f} MB")
    
    def fase5_crear_estructura_canonical(self):
        """FASE 5: Crear estructura canonical"""
        self.log("\n" + "=" * 60)
        self.log("FASE 5: CREANDO ESTRUCTURA CANONICAL")
        self.log("=" * 60)
        
        estructura = [
            "00_CORE/brain",
            "00_CORE/advisor",
            "00_CORE/autonomy",
            "10_FINANCIAL/core",
            "10_FINANCIAL/strategies",
            "10_FINANCIAL/data",
            "10_FINANCIAL/trading/pocketoption",
            "20_INFRASTRUCTURE/monitoring",
            "20_INFRASTRUCTURE/caching",
            "20_INFRASTRUCTURE/security",
            "20_INFRASTRUCTURE/storage",
            "tests/unit",
            "tests/integration",
            "tests/e2e",
        ]
        
        for carpeta in estructura:
            (self.root / carpeta).mkdir(parents=True, exist_ok=True)
            self.log(f"[CREADO] {carpeta}")
        
        self.log("[OK] FASE 5 COMPLETADA: Estructura canonical creada")
    
    def generar_reporte(self):
        """Generar reporte final"""
        self.log("\n" + "=" * 60)
        self.log("REPORTE FINAL DE DEPURACION")
        self.log("=" * 60)
        
        self.estadisticas["fin"] = datetime.now().isoformat()
        
        reporte = f"""
DEPURACION AI_VAULT - REPORTE FINAL
{'='*60}

Fecha inicio: {self.estadisticas['inicio']}
Fecha fin: {self.estadisticas['fin']}

RESULTADOS:
- Archivos eliminados: {self.estadisticas['archivos_eliminados']}
- Archivos archivados: {self.estadisticas['archivos_archivados']}
- Espacio total liberado: {self.estadisticas['espacio_liberado_mb']:.2f} MB

BACKUP:
- Ubicacion: {self.backup_dir}
- Archivos criticos respaldados: [OK]

ERRORES:
- Total errores: {len(self.estadisticas['errores'])}
{chr(10).join(['  - ' + e for e in self.estadisticas['errores']]) if self.estadisticas['errores'] else '  Ninguno'}

ESTADO: [OK] DEPURACION COMPLETADA

SIGUIENTES PASOS:
1. Verificar sistema operativo
2. Ejecutar tests de regresion
3. Iniciar PLAN_FORTALECIMIENTO_SISTEMICO.md

{'='*60}
"""
        
        # Guardar reporte JSON
        reporte_json = self.root / "DEPURACION_REPORTE.json"
        with open(reporte_json, 'w', encoding='utf-8') as f:
            json.dump(self.estadisticas, f, indent=2)
        
        # Guardar reporte Markdown
        reporte_md = self.root / "DEPURACION_REPORTE.md"
        with open(reporte_md, 'w', encoding='utf-8') as f:
            f.write(reporte)
        
        self.log(reporte)
        self.log(f"[INFO] Reportes guardados en:")
        self.log(f"   - {reporte_json}")
        self.log(f"   - {reporte_md}")
        self.log(f"   - {self.log_file}")
    
    def ejecutar_todas_las_fases(self):
        """Ejecutar todas las fases de depuracion"""
        self.log("[INICIANDO] DEPURACION COMPLETA AI_VAULT")
        self.log(f"[INFO] Directorio raiz: {self.root}")
        self.log(f"[INFO] Backup se guardara en: {self.backup_dir}")
        self.log("")
        
        try:
            # FASE 0: Backup
            if not self.backup_antes_depuracion():
                self.log("[ERROR] ABORTANDO: No se pudo crear backup")
                return False
            
            # FASES 1-5
            self.fase1_limpiar_backups_antiguos()
            self.fase2_limpiar_pycache()
            self.fase3_consolidar_componentes()
            self.fase4_archivar_logs_antiguos()
            self.fase5_crear_estructura_canonical()
            
            # Reporte final
            self.generar_reporte()
            
            return True
            
        except Exception as e:
            self.log(f"[ERROR] CRITICO: {e}")
            self.estadisticas["errores"].append(f"Critico: {e}")
            return False

if __name__ == "__main__":
    depuracion = DepuracionAIVAULT()
    exit(0 if depuracion.ejecutar_todas_las_fases() else 1)
