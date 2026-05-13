"""C-Sprint: Reasoning Corrector.

Analyzes failures to determine if they're:
  1. PROMPT_ISSUE - Can be fixed by refining system prompts/few-shot examples
  2. LOGIC_ERROR - Requires code mutation to fix
  3. KNOWLEDGE_GAP - Missing data/capability, cannot auto-fix
  4. TRANSIENT - Temporary issue (timeout, rate limit), retry may work

For LOGIC_ERROR, delegates to CodeMutator to propose and apply fixes.
For PROMPT_ISSUE, modifies prompt templates in-memory or on disk.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
import traceback
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from brain_v9.core import validator_metrics as _vmetrics

# Failure classification
class FailureType:
    PROMPT_ISSUE = "prompt_issue"
    LOGIC_ERROR = "logic_error"
    KNOWLEDGE_GAP = "knowledge_gap"
    TRANSIENT = "transient"
    TOOL_MISMATCH = "tool_mismatch"  # handled by B-sprint FailureLearner
    UNKNOWN = "unknown"


# Patterns that suggest specific failure types
_TRANSIENT_PATTERNS = [
    r"timeout|timed out",
    r"rate limit|too many requests|429",
    r"connection refused|connection reset",
    r"temporary|retry",
]

_PROMPT_ISSUE_PATTERNS = [
    r"no se que hacer|no entiendo",
    r"cannot determine|unclear",
    r"missing context|need more information",
    r"hallucin|invent|made up",
    r"wrong format|invalid json|parse error.*response",
]

_LOGIC_ERROR_PATTERNS = [
    r"TypeError|AttributeError|KeyError|IndexError|NameError",
    r"Traceback \(most recent call last\)",
    r"SyntaxError|IndentationError",
    r"AssertionError",
    r"RuntimeError",
    r"ValueError.*expected",
    r"NoneType.*has no attribute",
    r"Error:.*line \d+",
    r"brain_v9.*\.py.*Error",
    r"File.*\.py.*line \d+.*in",
]

_KNOWLEDGE_GAP_PATTERNS = [
    r"unknown tool|tool not found|capability.*missing",
    r"no data|no information|cannot access",
    r"API.*not available|service.*unavailable",
]


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass
class FailureAnalysis:
    """Result of analyzing a failure."""
    failure_type: str
    confidence: float
    source_file: Optional[str] = None
    source_line: Optional[int] = None
    error_message: str = ""
    suggested_fix: Optional[str] = None
    context: Dict[str, Any] = None

    def __post_init__(self):
        if self.context is None:
            self.context = {}


class ReasoningCorrector:
    """Analyzes and corrects reasoning/logic errors."""

    _instance: Optional["ReasoningCorrector"] = None

    def __init__(self) -> None:
        self.logger = logging.getLogger("ReasoningCorrector")
        self._code_mutator = None
        self._health_gate = None
        self._correction_history: List[Dict] = []
        self._suspended = False

    @classmethod
    def get(cls) -> "ReasoningCorrector":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def _get_mutator(self):
        if self._code_mutator is None:
            from brain_v9.agent.code_mutator import CodeMutator
            self._code_mutator = CodeMutator.get()
        return self._code_mutator

    def _get_health_gate(self):
        if self._health_gate is None:
            from brain_v9.agent.health_gate import HealthGate
            self._health_gate = HealthGate.get()
            # Wire up rollback callback
            self._health_gate.set_rollback_callback(self._handle_rollback)
        return self._health_gate

    def _handle_rollback(self, mutation_id: str, reason: str) -> None:
        """Handle rollback triggered by health gate."""
        mutator = self._get_mutator()
        success, msg = mutator.rollback(mutation_id, reason)
        if success:
            self.logger.info("Health gate rollback successful: %s", mutation_id)
        else:
            self.logger.error("Health gate rollback FAILED: %s - %s", mutation_id, msg)

    # ─────────────────────────────────────────────────────────────────
    # Failure Analysis
    # ─────────────────────────────────────────────────────────────────

    def classify_failure(
        self,
        error_text: str,
        context: Optional[Dict] = None,
    ) -> FailureAnalysis:
        """Classify a failure into one of the known types."""
        error_lower = error_text.lower()
        context = context or {}

        # Check patterns in order of specificity
        for pattern in _TRANSIENT_PATTERNS:
            if re.search(pattern, error_lower):
                return FailureAnalysis(
                    failure_type=FailureType.TRANSIENT,
                    confidence=0.8,
                    error_message=error_text[:500],
                    suggested_fix="Retry the operation",
                    context=context,
                )

        for pattern in _LOGIC_ERROR_PATTERNS:
            if re.search(pattern, error_text, re.IGNORECASE):
                # Try to extract source location from traceback
                source_file, source_line = self._extract_source_location(error_text)
                return FailureAnalysis(
                    failure_type=FailureType.LOGIC_ERROR,
                    confidence=0.85,
                    source_file=source_file,
                    source_line=source_line,
                    error_message=error_text[:1000],
                    suggested_fix="Code mutation required",
                    context=context,
                )

        for pattern in _PROMPT_ISSUE_PATTERNS:
            if re.search(pattern, error_lower):
                return FailureAnalysis(
                    failure_type=FailureType.PROMPT_ISSUE,
                    confidence=0.7,
                    error_message=error_text[:500],
                    suggested_fix="Refine system prompt or add few-shot example",
                    context=context,
                )

        for pattern in _KNOWLEDGE_GAP_PATTERNS:
            if re.search(pattern, error_lower):
                return FailureAnalysis(
                    failure_type=FailureType.KNOWLEDGE_GAP,
                    confidence=0.75,
                    error_message=error_text[:500],
                    suggested_fix="Cannot auto-fix: missing capability or data",
                    context=context,
                )

        # Default: unknown
        return FailureAnalysis(
            failure_type=FailureType.UNKNOWN,
            confidence=0.5,
            error_message=error_text[:500],
            context=context,
        )

    def _extract_source_location(self, error_text: str) -> Tuple[Optional[str], Optional[int]]:
        """Extract file and line number from Python traceback."""
        # Pattern: File "path/to/file.py", line 123
        match = re.search(
            r'File "([^"]+\.py)", line (\d+)',
            error_text,
        )
        if match:
            return (match.group(1), int(match.group(2)))

        # Also check for brain_v9 specific paths
        match = re.search(
            r'(brain_v9[/\\][^\s"]+\.py)["\s:,]+(?:line\s+)?(\d+)',
            error_text,
            re.IGNORECASE,
        )
        if match:
            return (match.group(1), int(match.group(2)))

        return (None, None)

    # ─────────────────────────────────────────────────────────────────
    # Correction Logic
    # ─────────────────────────────────────────────────────────────────

    async def attempt_correction(
        self,
        llm,
        error_text: str,
        task_context: str = "",
        action_history: Optional[List[Dict]] = None,
        allow_code_mutation: bool = True,
        allow_critical_files: bool = False,
    ) -> Tuple[bool, str, Optional[Dict]]:
        """Attempt to correct a failure.

        Returns:
            (success, message, correction_record)
        """
        if self._suspended:
            return (False, "ReasoningCorrector suspended (recursion guard)", None)

        self._suspended = True
        try:
            # Classify the failure
            analysis = self.classify_failure(error_text, {"task": task_context})
            _vmetrics.record(f"reasoning_failure_{analysis.failure_type}")

            self.logger.info(
                "Failure classified as %s (conf=%.2f): %s",
                analysis.failure_type, analysis.confidence, analysis.error_message[:100],
            )

            # Handle based on type
            if analysis.failure_type == FailureType.TRANSIENT:
                return (False, "Transient failure - should retry", {"type": "transient"})

            if analysis.failure_type == FailureType.KNOWLEDGE_GAP:
                return (False, "Knowledge gap - cannot auto-fix", {"type": "knowledge_gap"})

            if analysis.failure_type == FailureType.TOOL_MISMATCH:
                return (False, "Tool mismatch - handled by FailureLearner", {"type": "tool_mismatch"})

            if analysis.failure_type == FailureType.PROMPT_ISSUE:
                # TODO: Implement prompt refinement
                _vmetrics.record("reasoning_prompt_fix_skipped")
                return (False, "Prompt refinement not yet implemented", {"type": "prompt_issue"})

            if analysis.failure_type == FailureType.LOGIC_ERROR and allow_code_mutation:
                return await self._attempt_code_fix(
                    llm, analysis, task_context, action_history, allow_critical_files,
                )

            return (False, f"Cannot handle failure type: {analysis.failure_type}", None)

        finally:
            self._suspended = False

    async def _attempt_code_fix(
        self,
        llm,
        analysis: FailureAnalysis,
        task_context: str,
        action_history: Optional[List[Dict]],
        allow_critical: bool,
    ) -> Tuple[bool, str, Optional[Dict]]:
        """Attempt to fix a logic error via code mutation."""
        mutator = self._get_mutator()
        health_gate = self._get_health_gate()

        # Need source file to proceed
        if not analysis.source_file:
            return (False, "Cannot identify source file for code fix", None)

        source_path = Path(analysis.source_file)
        if not source_path.exists():
            # Try to find it relative to brain root
            from brain_v9.agent.code_mutator import _BRAIN_ROOT
            candidate = _BRAIN_ROOT / analysis.source_file
            if candidate.exists():
                source_path = candidate
            else:
                return (False, f"Source file not found: {analysis.source_file}", None)

        # Read code context
        try:
            full_content = source_path.read_text(encoding="utf-8")
            lines = full_content.split("\n")

            # Get surrounding context (50 lines around the error)
            start = max(0, (analysis.source_line or 1) - 25)
            end = min(len(lines), (analysis.source_line or 1) + 25)
            code_context = "\n".join(
                f"{i+1}: {lines[i]}" for i in range(start, end)
            )
        except Exception as e:
            return (False, f"Cannot read source file: {e}", None)

        # Build full error context
        error_context = f"""Error: {analysis.error_message}

Task context: {task_context[:500]}

Recent actions: {json.dumps(action_history[-5:] if action_history else [], default=str)[:1000]}
"""

        # Ask LLM for fix proposal
        proposal = await mutator.propose_fix(
            llm=llm,
            file_path=str(source_path),
            error_context=error_context,
            code_context=code_context,
            timeout=60.0,
        )

        if not proposal:
            return (False, "LLM could not propose a fix", None)

        self.logger.info(
            "Got fix proposal for %s: %s (conf=%.2f)",
            source_path.name, proposal.description[:100], proposal.confidence,
        )

        # Apply the fix
        success, msg, mutation = mutator.apply_edit(
            proposal,
            allow_critical=allow_critical,
            source="reasoning_corrector",
            model_used=getattr(llm, "last_model_used", "unknown"),
        )

        if not success:
            _vmetrics.record("reasoning_code_fix_failed")
            return (False, f"Failed to apply fix: {msg}", None)

        _vmetrics.record("reasoning_code_fix_applied")

        # Attempt hot-reload
        reload_ok, reload_msg = mutator.hot_reload(str(source_path))
        if reload_ok:
            self.logger.info("Hot-reload successful: %s", reload_msg)
        else:
            self.logger.warning("Hot-reload failed: %s", reload_msg)

        # Start health monitoring
        await health_gate.start_monitoring(mutation.id, duration=60.0)

        record = {
            "type": "code_mutation",
            "mutation_id": mutation.id,
            "file": str(source_path),
            "description": proposal.description,
            "confidence": proposal.confidence,
            "hot_reloaded": reload_ok,
        }
        self._correction_history.append(record)

        return (True, f"Code fix applied: {mutation.id}", record)

    # ─────────────────────────────────────────────────────────────────
    # Query API
    # ─────────────────────────────────────────────────────────────────

    def get_correction_history(self, limit: int = 20) -> List[Dict]:
        """Return recent correction attempts."""
        return self._correction_history[-limit:]
