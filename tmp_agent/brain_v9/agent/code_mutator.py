"""C-Sprint: Self-Modifying Code Mutator.

Allows the brain to propose and apply edits to its own Python source files.
Full auto-apply mode with minimal safety gates:
  1. Syntax validation via ast.parse()
  2. Automatic .bak backup before edit
  3. Hot-reload of modified module
  4. Health monitoring post-mutation with auto-rollback

WARNING: This gives the brain ability to modify its own code without approval.
Use with caution in production environments.
"""
from __future__ import annotations

import ast
import asyncio
import hashlib
import importlib
import json
import logging
import os
import re
import shutil
import sys
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any, Dict, List, Optional, Tuple

from brain_v9.core import validator_metrics as _vmetrics

# Paths
_BRAIN_ROOT = Path("C:/AI_VAULT/tmp_agent/brain_v9")
_MUTATION_LOG_DIR = Path("C:/AI_VAULT/tmp_agent/state/mutations")
_MUTATION_LOG_DIR.mkdir(parents=True, exist_ok=True)

# Critical files that require explicit flag to modify
_CRITICAL_FILES = {
    "main.py",
    "execution_gate.py",
    "code_mutator.py",  # self-protection
    "health_gate.py",
}

# Max mutations to keep in memory
_MAX_MUTATION_HISTORY = 50


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _file_hash(path: Path) -> str:
    if not path.exists():
        return ""
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


@dataclass
class Mutation:
    """Record of a code mutation."""
    id: str
    timestamp: str
    file_path: str
    original_hash: str
    new_hash: str
    edit_type: str  # "replace", "insert", "delete"
    description: str
    diff_preview: str  # first 500 chars of change
    success: bool
    error: Optional[str] = None
    rolled_back: bool = False
    rollback_reason: Optional[str] = None
    backup_path: Optional[str] = None
    source: str = "llm_proposed"  # or "manual", "reasoning_corrector"
    model_used: str = ""
    confidence: float = 0.0

    def to_dict(self) -> Dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict) -> "Mutation":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


@dataclass
class EditProposal:
    """Proposed edit to a file."""
    file_path: str
    edit_type: str  # "replace", "insert_after", "insert_before", "delete_lines"
    target: str  # for replace: old string; for insert: anchor string; for delete: line range
    content: str  # new content (empty for delete)
    description: str
    confidence: float = 0.0
    rationale: str = ""


class CodeMutator:
    """Singleton class for proposing and applying code mutations."""

    _instance: Optional["CodeMutator"] = None
    _instance_lock = Lock()

    def __init__(self) -> None:
        self.logger = logging.getLogger("CodeMutator")
        self._mutations: List[Mutation] = []
        self._lock = Lock()
        self._suspended = False  # recursion guard
        self._load_history()

    @classmethod
    def get(cls) -> "CodeMutator":
        with cls._instance_lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def _load_history(self) -> None:
        """Load recent mutation history from disk."""
        try:
            log_file = _MUTATION_LOG_DIR / "mutation_log.jsonl"
            if not log_file.exists():
                return
            lines = log_file.read_text(encoding="utf-8").strip().split("\n")
            for line in lines[-_MAX_MUTATION_HISTORY:]:
                if line.strip():
                    try:
                        self._mutations.append(Mutation.from_dict(json.loads(line)))
                    except Exception:
                        pass
            self.logger.info("Loaded %d mutations from history", len(self._mutations))
        except Exception as e:
            self.logger.warning("Failed to load mutation history: %s", e)

    def _persist_mutation(self, mutation: Mutation) -> None:
        """Append mutation to log file."""
        try:
            log_file = _MUTATION_LOG_DIR / "mutation_log.jsonl"
            with log_file.open("a", encoding="utf-8") as f:
                f.write(json.dumps(mutation.to_dict(), default=str) + "\n")
        except Exception as e:
            self.logger.warning("Failed to persist mutation: %s", e)

    # ─────────────────────────────────────────────────────────────────
    # Core API
    # ─────────────────────────────────────────────────────────────────

    async def propose_fix(
        self,
        llm,
        file_path: str,
        error_context: str,
        code_context: str,
        timeout: float = 60.0,
    ) -> Optional[EditProposal]:
        """Ask LLM to propose a code fix for an error.

        Args:
            llm: LLM manager instance
            file_path: Path to the file with the error
            error_context: Error message/traceback
            code_context: Relevant code snippet (surrounding lines)
            timeout: LLM query timeout

        Returns:
            EditProposal if LLM proposes a valid fix, None otherwise
        """
        if self._suspended:
            return None

        self._suspended = True
        try:
            prompt = self._build_fix_prompt(file_path, error_context, code_context)
            try:
                result = await asyncio.wait_for(
                    llm.query(
                        [{"role": "user", "content": prompt}],
                        model_priority="agent_frontier",
                        max_time=int(timeout),
                    ),
                    timeout=timeout + 10,
                )
            except Exception as e:
                self.logger.warning("propose_fix LLM error: %s", e)
                _vmetrics.record("code_mutation_llm_error")
                return None

            if not result or not result.get("success") or not result.get("content"):
                _vmetrics.record("code_mutation_llm_empty")
                return None

            proposal = self._parse_proposal(result["content"], file_path)
            if proposal:
                proposal.confidence = float(result.get("confidence", 0.7))
                _vmetrics.record("code_mutation_proposed")
            return proposal
        finally:
            self._suspended = False

    def apply_edit(
        self,
        proposal: EditProposal,
        allow_critical: bool = False,
        source: str = "llm_proposed",
        model_used: str = "",
    ) -> Tuple[bool, str, Optional[Mutation]]:
        """Apply an edit proposal to the filesystem.

        Returns:
            (success, message, mutation_record)
        """
        file_name = Path(proposal.file_path).name
        if file_name in _CRITICAL_FILES and not allow_critical:
            return (False, f"Cannot modify critical file {file_name} without allow_critical=True", None)

        path = Path(proposal.file_path)
        if not path.exists():
            return (False, f"File not found: {proposal.file_path}", None)

        # Read current content
        try:
            original_content = path.read_text(encoding="utf-8")
        except Exception as e:
            return (False, f"Cannot read file: {e}", None)

        original_hash = _file_hash(path)

        # Apply edit based on type
        if proposal.edit_type == "replace":
            if proposal.target not in original_content:
                return (False, f"Target string not found in file", None)
            new_content = original_content.replace(proposal.target, proposal.content, 1)
        elif proposal.edit_type == "insert_after":
            if proposal.target not in original_content:
                return (False, f"Anchor string not found for insert_after", None)
            idx = original_content.find(proposal.target) + len(proposal.target)
            new_content = original_content[:idx] + "\n" + proposal.content + original_content[idx:]
        elif proposal.edit_type == "insert_before":
            if proposal.target not in original_content:
                return (False, f"Anchor string not found for insert_before", None)
            idx = original_content.find(proposal.target)
            new_content = original_content[:idx] + proposal.content + "\n" + original_content[idx:]
        elif proposal.edit_type == "delete_lines":
            # target format: "start:end" (1-indexed, inclusive)
            try:
                start, end = map(int, proposal.target.split(":"))
                lines = original_content.split("\n")
                new_lines = lines[:start-1] + lines[end:]
                new_content = "\n".join(new_lines)
            except Exception as e:
                return (False, f"Invalid delete_lines target format: {e}", None)
        else:
            return (False, f"Unknown edit_type: {proposal.edit_type}", None)

        # Syntax validation
        try:
            ast.parse(new_content)
        except SyntaxError as e:
            _vmetrics.record("code_mutation_syntax_error")
            return (False, f"Proposed edit creates syntax error: {e}", None)

        # Create backup
        backup_path = path.with_suffix(path.suffix + f".bak.{int(time.time())}")
        try:
            shutil.copy2(path, backup_path)
        except Exception as e:
            return (False, f"Cannot create backup: {e}", None)

        # Apply edit
        try:
            path.write_text(new_content, encoding="utf-8")
        except Exception as e:
            # Restore from backup
            shutil.copy2(backup_path, path)
            return (False, f"Cannot write file: {e}", None)

        new_hash = _file_hash(path)

        # Create mutation record
        mutation_id = f"mut_{hashlib.sha1(f'{path}:{time.time()}'.encode()).hexdigest()[:8]}"
        diff_preview = self._make_diff_preview(proposal.target, proposal.content)

        mutation = Mutation(
            id=mutation_id,
            timestamp=_now_iso(),
            file_path=str(path),
            original_hash=original_hash,
            new_hash=new_hash,
            edit_type=proposal.edit_type,
            description=proposal.description,
            diff_preview=diff_preview,
            success=True,
            backup_path=str(backup_path),
            source=source,
            model_used=model_used,
            confidence=proposal.confidence,
        )

        with self._lock:
            self._mutations.append(mutation)
            if len(self._mutations) > _MAX_MUTATION_HISTORY:
                self._mutations = self._mutations[-_MAX_MUTATION_HISTORY:]

        self._persist_mutation(mutation)
        _vmetrics.record("code_mutation_applied")
        self.logger.info("Applied mutation %s to %s", mutation_id, path.name)

        return (True, f"Mutation {mutation_id} applied successfully", mutation)

    def rollback(self, mutation_id: str, reason: str = "manual") -> Tuple[bool, str]:
        """Rollback a mutation using its backup file."""
        with self._lock:
            mutation = next((m for m in self._mutations if m.id == mutation_id), None)
            if not mutation:
                return (False, f"Mutation {mutation_id} not found")
            if mutation.rolled_back:
                return (False, f"Mutation {mutation_id} already rolled back")
            if not mutation.backup_path:
                return (False, f"No backup available for {mutation_id}")

            backup_path = Path(mutation.backup_path)
            target_path = Path(mutation.file_path)

            if not backup_path.exists():
                return (False, f"Backup file not found: {backup_path}")

            try:
                shutil.copy2(backup_path, target_path)
                mutation.rolled_back = True
                mutation.rollback_reason = reason
                self._persist_mutation(mutation)
                _vmetrics.record("code_mutation_rollback")
                self.logger.info("Rolled back mutation %s: %s", mutation_id, reason)
                return (True, f"Mutation {mutation_id} rolled back")
            except Exception as e:
                return (False, f"Rollback failed: {e}")

    def hot_reload(self, file_path: str) -> Tuple[bool, str]:
        """Hot-reload a Python module after mutation.

        This is tricky and may not work for all modules (especially those
        with global state or circular imports). Use with caution.
        """
        path = Path(file_path)
        if not path.suffix == ".py":
            return (False, "Not a Python file")

        # Convert file path to module name
        try:
            rel_path = path.relative_to(_BRAIN_ROOT.parent)
            module_name = str(rel_path.with_suffix("")).replace("/", ".").replace("\\", ".")
        except ValueError:
            return (False, f"File not in brain directory: {file_path}")

        if module_name not in sys.modules:
            return (True, f"Module {module_name} not loaded, no reload needed")

        try:
            module = sys.modules[module_name]
            importlib.reload(module)
            _vmetrics.record("code_mutation_hot_reload")
            self.logger.info("Hot-reloaded module: %s", module_name)
            return (True, f"Module {module_name} reloaded")
        except Exception as e:
            _vmetrics.record("code_mutation_reload_failed")
            return (False, f"Hot-reload failed: {e}")

    # ─────────────────────────────────────────────────────────────────
    # Helpers
    # ─────────────────────────────────────────────────────────────────

    def _build_fix_prompt(self, file_path: str, error_context: str, code_context: str) -> str:
        return f"""Eres un agente de auto-reparacion de codigo. Un archivo Python tiene un error.
Tu trabajo es proponer un FIX MINIMO y SEGURO.

=== ARCHIVO ===
{file_path}

=== ERROR ===
{error_context[:2000]}

=== CODIGO RELEVANTE ===
{code_context[:3000]}

=== TAREA ===
Propone UN edit para corregir el error. Devuelve SOLO JSON valido:

{{
  "edit_type": "replace",  // o "insert_after", "insert_before", "delete_lines"
  "target": "<string exacto a reemplazar o anchor para insert>",
  "content": "<nuevo contenido>",
  "description": "<que hace este fix>",
  "confidence": 0.0-1.0,
  "rationale": "<por que este fix es correcto y seguro>"
}}

REGLAS:
- edit_type "replace": target es el string exacto a buscar, content es el reemplazo
- edit_type "insert_after"/"insert_before": target es el anchor, content se inserta
- edit_type "delete_lines": target es "start:end" (1-indexed), content se ignora
- El fix DEBE ser sintacticamente valido (Python parseable)
- Prefiere fixes MINIMOS (no reescribas funciones enteras si puedes arreglar una linea)
- Si no puedes proponer un fix seguro, devuelve {{"confidence": 0}}
- confidence >= 0.6 para aplicar
"""

    def _parse_proposal(self, content: str, file_path: str) -> Optional[EditProposal]:
        """Parse LLM response into EditProposal."""
        try:
            # Strip markdown fences
            text = content.strip()
            fence_match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
            if fence_match:
                text = fence_match.group(1).strip()

            # Try parse
            data = None
            try:
                data = json.loads(text)
            except json.JSONDecodeError:
                # Try extract JSON block
                m = re.search(r"\{.*\}", text, re.DOTALL)
                if m:
                    data = json.loads(m.group(0))

            if not data:
                return None

            if float(data.get("confidence", 0)) < 0.6:
                _vmetrics.record("code_mutation_low_confidence")
                return None

            return EditProposal(
                file_path=file_path,
                edit_type=data.get("edit_type", "replace"),
                target=data.get("target", ""),
                content=data.get("content", ""),
                description=data.get("description", ""),
                confidence=float(data.get("confidence", 0.7)),
                rationale=data.get("rationale", ""),
            )
        except Exception as e:
            self.logger.warning("Failed to parse proposal: %s", e)
            _vmetrics.record("code_mutation_parse_failed")
            return None

    def _make_diff_preview(self, old: str, new: str) -> str:
        """Create a simple diff preview."""
        old_preview = old[:200] if old else "(empty)"
        new_preview = new[:200] if new else "(empty)"
        return f"- {old_preview}\n+ {new_preview}"

    # ─────────────────────────────────────────────────────────────────
    # Query API
    # ─────────────────────────────────────────────────────────────────

    def list_mutations(self, limit: int = 20) -> List[Dict]:
        """Return recent mutations."""
        with self._lock:
            return [m.to_dict() for m in self._mutations[-limit:]]

    def get_mutation(self, mutation_id: str) -> Optional[Dict]:
        """Get a specific mutation by ID."""
        with self._lock:
            m = next((m for m in self._mutations if m.id == mutation_id), None)
            return m.to_dict() if m else None
