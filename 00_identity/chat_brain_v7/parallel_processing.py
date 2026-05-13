#!/usr/bin/env python3
"""
Procesamiento Paralelo para Análisis
Optimiza rendimiento usando concurrent.futures
"""

import concurrent.futures
from pathlib import Path
from typing import List, Dict
import sys

sys.path.insert(0, str(Path(__file__).parent))

try:
    from tools_advanced import ASTAnalyzer
    TOOLS_AVAILABLE = True
except ImportError:
    TOOLS_AVAILABLE = False


class ParallelAnalyzer:
    """Analizador paralelo de archivos"""
    
    def __init__(self, max_workers: int = 4):
        self.max_workers = max_workers
        self.analyzer = ASTAnalyzer() if TOOLS_AVAILABLE else None
    
    def analyze_file_sync(self, file_path: str) -> Dict:
        """Analiza un archivo (versión síncrona para threads)"""
        if not self.analyzer:
            return {"error": "Analyzer not available"}
        
        try:
            return self.analyzer.analyze_file(file_path)
        except Exception as e:
            return {"error": str(e), "file": file_path}
    
    def analyze_directory_parallel(self, directory: str, pattern: str = "*.py") -> List[Dict]:
        """Analiza directorio en paralelo"""
        if not TOOLS_AVAILABLE:
            return [{"error": "Tools not available"}]
        
        path = Path(directory)
        files = list(path.rglob(pattern))
        
        results = []
        
        # Usar ThreadPoolExecutor
        with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # Mapear análisis sobre archivos
            future_to_file = {
                executor.submit(self.analyze_file_sync, str(f)): f 
                for f in files[:20]  # Limitar a 20 archivos
            }
            
            # Recolectar resultados
            for future in concurrent.futures.as_completed(future_to_file):
                file = future_to_file[future]
                try:
                    result = future.result()
                    results.append(result)
                except Exception as e:
                    results.append({"error": str(e), "file": str(file)})
        
        return results


if __name__ == "__main__":
    if TOOLS_AVAILABLE:
        analyzer = ParallelAnalyzer(max_workers=2)
        results = analyzer.analyze_directory_parallel(
            "C:/AI_VAULT/00_identity/chat_brain_v7"
        )
        print(f"Analizados {len(results)} archivos en paralelo")
    else:
        print("Herramientas no disponibles")
