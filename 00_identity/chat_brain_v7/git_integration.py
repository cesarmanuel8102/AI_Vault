#!/usr/bin/env python3
"""
Integración Git - Control de Versiones
Permite ejecutar comandos git y analizar repositorios
"""

import subprocess
from pathlib import Path
from typing import Dict, List, Optional


class GitIntegration:
    """Integración con Git"""
    
    def __init__(self, repo_path: str = None):
        if repo_path is None:
            repo_path = "C:/AI_VAULT"
        self.repo_path = Path(repo_path)
    
    def _run_git(self, args: List[str]) -> Dict:
        """Ejecuta comando git"""
        try:
            result = subprocess.run(
                ["git"] + args,
                capture_output=True,
                text=True,
                cwd=str(self.repo_path),
                timeout=10
            )
            
            return {
                "success": result.returncode == 0,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "returncode": result.returncode
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def status(self) -> Dict:
        """Obtiene estado del repositorio"""
        return self._run_git(["status", "--short"])
    
    def diff(self) -> Dict:
        """Obtiene diferencias"""
        return self._run_git(["diff"])
    
    def log(self, n: int = 10) -> Dict:
        """Obtiene historial de commits"""
        return self._run_git(["log", "--oneline", f"-{n}"])
    
    def branch(self) -> Dict:
        """Obtiene rama actual"""
        return self._run_git(["branch", "--show-current"])
    
    def add(self, files: List[str]) -> Dict:
        """Agrega archivos al staging"""
        return self._run_git(["add"] + files)
    
    def commit(self, message: str) -> Dict:
        """Crea un commit"""
        return self._run_git(["commit", "-m", message])


if __name__ == "__main__":
    git = GitIntegration()
    
    # Test
    print("Estado del repositorio:")
    status = git.status()
    print(status.get('stdout', 'No hay cambios'))
    
    print("\nRama actual:")
    branch = git.branch()
    print(branch.get('stdout', 'Unknown'))
    
    print("\nÚltimos commits:")
    log = git.log(5)
    print(log.get('stdout', 'No history'))
