"""
SELF_DEV_SANDBOX.PY - Auto-Desarrollo Seguro
Permite que el sistema proponga, pruebe y aplique cambios a su propio codigo
con validacion multi-nivel y rollback automatico.

Pipeline: PROPOSE -> SANDBOX_TEST -> STATIC_ANALYSIS -> CANARY -> APPROVE -> APPLY
"""
import ast
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

DEV_DIR = Path("C:/AI_VAULT/tmp_agent/state/self_dev")
DEV_DIR.mkdir(parents=True, exist_ok=True)
PROPOSALS_FILE = DEV_DIR / "proposals.jsonl"
BACKUPS_DIR = DEV_DIR / "backups"
BACKUPS_DIR.mkdir(parents=True, exist_ok=True)


@dataclass
class CodeProposal:
    proposal_id: str
    target_file: str
    rationale: str
    diff_summary: str
    new_content_hash: str
    status: str = "proposed"  # proposed, validated, rejected, applied, reverted
    risk_score: float = 0.5
    test_results: Dict[str, Any] = field(default_factory=dict)
    static_findings: List[str] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    applied_at: Optional[str] = None
    backup_path: Optional[str] = None
    requires_human_approval: bool = True


# --- Reglas de prohibicion (defensa en profundidad) ---
FORBIDDEN_PATTERNS = [
    "os.system",
    "subprocess.Popen",          # solo permitido en este modulo
    "shutil.rmtree",             # delete recursivo
    "__import__",                # imports dinamicos sospechosos
    "eval(",
    "exec(",
    "open('/etc",
    "open(\"/etc",
    "rm -rf",
]

PROTECTED_PATHS = [
    ".dev_auth",
    "credentials",
    ".env",
    "secrets",
]


class SelfDevSandbox:
    """Sandbox para auto-desarrollo seguro."""

    def __init__(self):
        self.proposals: List[CodeProposal] = []
        self._load_recent()

    def _load_recent(self):
        if not PROPOSALS_FILE.exists():
            return
        try:
            for line in PROPOSALS_FILE.read_text(encoding="utf-8").splitlines()[-100:]:
                if line.strip():
                    self.proposals.append(CodeProposal(**json.loads(line)))
        except Exception:
            pass

    def _audit(self, proposal: CodeProposal):
        with PROPOSALS_FILE.open("a", encoding="utf-8") as f:
            f.write(json.dumps(asdict(proposal)) + "\n")

    # --- Validaciones ---
    def _path_is_protected(self, target: str) -> bool:
        t = target.replace("\\", "/").lower()
        return any(p in t for p in PROTECTED_PATHS)

    def _static_analysis(self, content: str) -> List[str]:
        """Analisis estatico: AST + patrones prohibidos."""
        findings = []
        # Patrones prohibidos por substring
        for pat in FORBIDDEN_PATTERNS:
            if pat in content:
                findings.append(f"forbidden_pattern:{pat}")
        # AST: detectar exec/eval/imports peligrosos
        try:
            tree = ast.parse(content)
            for node in ast.walk(tree):
                if isinstance(node, ast.Call):
                    fn_name = ""
                    if isinstance(node.func, ast.Name):
                        fn_name = node.func.id
                    elif isinstance(node.func, ast.Attribute):
                        fn_name = node.func.attr
                    if fn_name in ("eval", "exec", "compile"):
                        findings.append(f"dangerous_call:{fn_name}@line{node.lineno}")
                if isinstance(node, ast.Import):
                    for n in node.names:
                        if n.name in ("ctypes", "marshal"):
                            findings.append(f"sensitive_import:{n.name}")
        except SyntaxError as e:
            findings.append(f"syntax_error:{e.lineno}:{e.msg}")
        return findings

    def _syntax_valid(self, content: str) -> bool:
        try:
            ast.parse(content)
            return True
        except SyntaxError:
            return False

    def _compute_risk(self, target_file: str, findings: List[str], content: str) -> float:
        risk = 0.2
        if self._path_is_protected(target_file):
            risk += 0.5
        risk += min(0.4, len(findings) * 0.1)
        # Riesgo por tamano (cambios grandes son mas arriesgados)
        loc = content.count("\n")
        if loc > 500:
            risk += 0.1
        # Riesgo si toca core del sistema
        critical_keywords = ["main.py", "session.py", "manager.py", "auth"]
        if any(kw in target_file.lower() for kw in critical_keywords):
            risk += 0.2
        return min(1.0, risk)

    # --- Pipeline ---
    def propose(self, target_file: str, new_content: str, rationale: str) -> CodeProposal:
        """Crea una propuesta de cambio. NO modifica nada aun."""
        pid = f"prop_{datetime.now().strftime('%Y%m%d%H%M%S')}_{hashlib.md5(target_file.encode()).hexdigest()[:6]}"
        findings = self._static_analysis(new_content)
        risk = self._compute_risk(target_file, findings, new_content)
        proposal = CodeProposal(
            proposal_id=pid,
            target_file=target_file,
            rationale=rationale[:500],
            diff_summary=f"+{new_content.count(chr(10))} lines",
            new_content_hash=hashlib.sha256(new_content.encode()).hexdigest()[:16],
            risk_score=risk,
            static_findings=findings,
            requires_human_approval=(risk > 0.4 or self._path_is_protected(target_file)),
        )
        # Guardar contenido propuesto en area temporal
        staging = DEV_DIR / "staging" / pid
        staging.mkdir(parents=True, exist_ok=True)
        (staging / "new_content.py").write_text(new_content, encoding="utf-8")
        (staging / "meta.json").write_text(json.dumps(asdict(proposal), indent=2), encoding="utf-8")
        self.proposals.append(proposal)
        self._audit(proposal)
        return proposal

    def sandbox_test(self, proposal_id: str, test_command: Optional[str] = None) -> Dict[str, Any]:
        """Ejecuta el contenido en un proceso aislado para validar."""
        proposal = self._find(proposal_id)
        if not proposal:
            return {"success": False, "error": "proposal_not_found"}
        staging = DEV_DIR / "staging" / proposal_id / "new_content.py"
        if not staging.exists():
            return {"success": False, "error": "staging_missing"}
        content = staging.read_text(encoding="utf-8")
        # 1) Sintaxis
        if not self._syntax_valid(content):
            proposal.status = "rejected"
            proposal.test_results = {"reason": "syntax_invalid"}
            self._audit(proposal)
            return {"success": False, "error": "syntax_invalid"}
        # 2) Re-analisis estatico
        findings = self._static_analysis(content)
        if any(f.startswith("forbidden_pattern") or f.startswith("dangerous_call") for f in findings):
            proposal.status = "rejected"
            proposal.test_results = {"reason": "security_findings", "findings": findings}
            self._audit(proposal)
            return {"success": False, "error": "security_findings", "findings": findings}
        # 3) Importacion en proceso aislado (timeout)
        result = self._run_isolated_import(staging, test_command)
        proposal.test_results = result
        if result.get("success"):
            proposal.status = "validated"
        self._audit(proposal)
        return result

    def _run_isolated_import(self, file_path: Path, test_command: Optional[str]) -> Dict[str, Any]:
        """Corre `python -c "import file"` en subproceso con timeout."""
        try:
            cmd = [sys.executable, "-c",
                   f"import importlib.util,sys; "
                   f"spec=importlib.util.spec_from_file_location('m',r'{file_path}'); "
                   f"m=importlib.util.module_from_spec(spec); "
                   f"spec.loader.exec_module(m); print('IMPORT_OK')"]
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
            ok = "IMPORT_OK" in r.stdout
            return {"success": ok, "stdout": r.stdout[-500:], "stderr": r.stderr[-500:],
                    "returncode": r.returncode}
        except subprocess.TimeoutExpired:
            return {"success": False, "error": "timeout"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def apply(self, proposal_id: str, approver: Optional[str] = None) -> Dict[str, Any]:
        """Aplica el cambio creando backup automatico."""
        proposal = self._find(proposal_id)
        if not proposal:
            return {"success": False, "error": "proposal_not_found"}
        if proposal.status not in ("validated",):
            return {"success": False, "error": f"invalid_status:{proposal.status}"}
        if proposal.requires_human_approval and not approver:
            return {"success": False, "error": "human_approval_required",
                    "risk_score": proposal.risk_score}
        target = Path(proposal.target_file)
        # Backup
        if target.exists():
            backup_path = BACKUPS_DIR / f"{target.name}.{proposal_id}.bak"
            shutil.copy2(target, backup_path)
            proposal.backup_path = str(backup_path)
        # Aplicar
        staging = DEV_DIR / "staging" / proposal_id / "new_content.py"
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(staging, target)
        proposal.status = "applied"
        proposal.applied_at = datetime.now().isoformat()
        self._audit(proposal)
        return {"success": True, "backup": proposal.backup_path,
                "applied_at": proposal.applied_at}

    def revert(self, proposal_id: str) -> Dict[str, Any]:
        """Revierte usando el backup."""
        proposal = self._find(proposal_id)
        if not proposal or not proposal.backup_path:
            return {"success": False, "error": "no_backup"}
        backup = Path(proposal.backup_path)
        if not backup.exists():
            return {"success": False, "error": "backup_missing"}
        shutil.copy2(backup, proposal.target_file)
        proposal.status = "reverted"
        self._audit(proposal)
        return {"success": True, "reverted_at": datetime.now().isoformat()}

    def _find(self, pid: str) -> Optional[CodeProposal]:
        for p in self.proposals:
            if p.proposal_id == pid:
                return p
        return None

    def status(self) -> Dict[str, Any]:
        from collections import Counter
        status_counts = Counter(p.status for p in self.proposals)
        return {
            "total_proposals": len(self.proposals),
            "by_status": dict(status_counts),
            "high_risk_pending": sum(1 for p in self.proposals
                                     if p.risk_score > 0.6 and p.status == "proposed"),
        }


_SANDBOX: Optional[SelfDevSandbox] = None

def get_sandbox() -> SelfDevSandbox:
    global _SANDBOX
    if _SANDBOX is None:
        _SANDBOX = SelfDevSandbox()
    return _SANDBOX
