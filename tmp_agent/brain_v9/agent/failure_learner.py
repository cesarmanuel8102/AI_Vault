"""B-Sprint: Failure Pattern Learner.

When a tool action fails:
  1. Lookup learned patterns by error signature -> apply if hit.
  2. If miss, ask LLM to abstract the failure into a generalizable correction.
  3. Validate the correction in a sandbox via SelfTester.
  4. If validation passes, persist + apply.

Replaces hardcoded _FAILURE_HINTS / _NATIVE_FALLBACKS with a learned,
persistable knowledge base. Patterns survive restarts.

Storage: state/learned_patterns/<id>.json + index.json
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any, Dict, List, Optional, Tuple

from brain_v9.core import validator_metrics as _vmetrics

# State path - tmp_agent/state/learned_patterns
_STATE_DIR = Path("C:/AI_VAULT/tmp_agent/state/learned_patterns")
_STATE_DIR.mkdir(parents=True, exist_ok=True)
_INDEX_PATH = _STATE_DIR / "index.json"

# Caps
_MAX_PATTERNS = 100
_MAX_APPLY_PER_SESSION = 5
_MIN_PASSES_FOR_AUTO_APPLY = 1


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _gen_id(error_text: str, tool: str) -> str:
    h = hashlib.sha1(f"{tool}::{error_text[:300]}".encode("utf-8", "ignore")).hexdigest()[:8]
    return f"lp_{h}"


@dataclass
class CorrectionTransform:
    """How to mutate the original call into a corrected one."""
    extract_arg: Optional[str] = None        # which arg to extract from
    regex_extract: Optional[str] = None      # regex with capture group(s)
    target_arg: Optional[str] = None         # destination arg name
    static_args: Dict[str, Any] = field(default_factory=dict)  # extra static args
    ascii_strip: bool = False                # strip non-ASCII before passing


@dataclass
class CorrectionSpec:
    kind: str  # "rewrite_call"
    to_tool: str
    transform: CorrectionTransform


@dataclass
class LearnedPattern:
    id: str
    created_utc: str
    tool_class: str               # original failing tool
    error_match_regex: str        # regex tested against error_text
    correction: CorrectionSpec
    validation: Dict[str, Any] = field(default_factory=lambda: {"tested": False, "passes": 0, "fails": 0})
    governance: Dict[str, Any] = field(default_factory=lambda: {
        "auto_apply": True,
        "max_apply_per_session": _MAX_APPLY_PER_SESSION,
        "require_min_passes": _MIN_PASSES_FOR_AUTO_APPLY,
    })
    source: str = "llm_abstracted"
    model_used: str = ""
    confidence: float = 0.0
    disabled: bool = False
    last_used_utc: str = ""
    use_count: int = 0

    def to_dict(self) -> Dict:
        d = asdict(self)
        return d

    @classmethod
    def from_dict(cls, d: Dict) -> "LearnedPattern":
        corr_d = d.get("correction", {})
        tr_d = corr_d.get("transform", {})
        tr = CorrectionTransform(**tr_d) if tr_d else CorrectionTransform()
        corr = CorrectionSpec(
            kind=corr_d.get("kind", "rewrite_call"),
            to_tool=corr_d.get("to_tool", ""),
            transform=tr,
        )
        return cls(
            id=d["id"],
            created_utc=d.get("created_utc", _now_iso()),
            tool_class=d.get("tool_class", ""),
            error_match_regex=d.get("error_match_regex", ""),
            correction=corr,
            validation=d.get("validation", {"tested": False, "passes": 0, "fails": 0}),
            governance=d.get("governance", {
                "auto_apply": True,
                "max_apply_per_session": _MAX_APPLY_PER_SESSION,
                "require_min_passes": _MIN_PASSES_FOR_AUTO_APPLY,
            }),
            source=d.get("source", "llm_abstracted"),
            model_used=d.get("model_used", ""),
            confidence=float(d.get("confidence", 0.0)),
            disabled=bool(d.get("disabled", False)),
            last_used_utc=d.get("last_used_utc", ""),
            use_count=int(d.get("use_count", 0)),
        )

    def matches(self, tool: str, error_text: str) -> bool:
        if self.disabled:
            return False
        if self.tool_class and tool and self.tool_class != tool:
            return False
        try:
            return bool(re.search(self.error_match_regex, error_text or "", re.IGNORECASE))
        except re.error:
            return False

    def ready_for_auto_apply(self) -> bool:
        if self.disabled or not self.governance.get("auto_apply", True):
            return False
        passes = int(self.validation.get("passes", 0))
        return passes >= int(self.governance.get("require_min_passes", _MIN_PASSES_FOR_AUTO_APPLY))


class FailureLearner:
    """Singleton-style learner with on-disk persistence."""

    _instance: Optional["FailureLearner"] = None
    _instance_lock = Lock()

    def __init__(self) -> None:
        self.logger = logging.getLogger("FailureLearner")
        self._patterns: Dict[str, LearnedPattern] = {}
        self._lock = Lock()
        self._session_apply_count: Dict[str, int] = {}
        # Recursion guard - disabled while abstracting/validating
        self._suspended: bool = False
        self._load()

    @classmethod
    def get(cls) -> "FailureLearner":
        with cls._instance_lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    # ---------------- Persistence ----------------
    def _load(self) -> None:
        if not _INDEX_PATH.exists():
            return
        try:
            with _INDEX_PATH.open("r", encoding="utf-8") as f:
                idx = json.load(f)
            for pid in idx.get("ids", []):
                p = _STATE_DIR / f"{pid}.json"
                if not p.exists():
                    continue
                try:
                    with p.open("r", encoding="utf-8") as f:
                        d = json.load(f)
                    pat = LearnedPattern.from_dict(d)
                    self._patterns[pat.id] = pat
                except Exception as e:
                    self.logger.warning("skip pattern %s: %s", pid, e)
            self.logger.info("FailureLearner loaded %d patterns", len(self._patterns))
        except Exception as e:
            self.logger.warning("FailureLearner load failed: %s", e)

    def _persist(self, pattern: LearnedPattern) -> None:
        try:
            (_STATE_DIR / f"{pattern.id}.json").write_text(
                json.dumps(pattern.to_dict(), indent=2, default=str),
                encoding="utf-8",
            )
            ids = sorted(self._patterns.keys())
            _INDEX_PATH.write_text(
                json.dumps({"ids": ids, "updated_utc": _now_iso(), "count": len(ids)}, indent=2),
                encoding="utf-8",
            )
        except Exception as e:
            self.logger.warning("persist %s failed: %s", pattern.id, e)

    # ---------------- API ----------------
    def lookup(self, tool: str, error_text: str) -> Optional[LearnedPattern]:
        if self._suspended:
            return None
        with self._lock:
            for pat in self._patterns.values():
                if pat.matches(tool, error_text) and pat.ready_for_auto_apply():
                    sess = self._session_apply_count.get(pat.id, 0)
                    if sess >= int(pat.governance.get("max_apply_per_session", _MAX_APPLY_PER_SESSION)):
                        continue
                    _vmetrics.record("learned_pattern_hit")
                    return pat
        return None

    def list_all(self) -> List[Dict]:
        with self._lock:
            return [p.to_dict() for p in self._patterns.values()]

    def get_pattern(self, pid: str) -> Optional[LearnedPattern]:
        with self._lock:
            return self._patterns.get(pid)

    def disable(self, pid: str) -> bool:
        with self._lock:
            p = self._patterns.get(pid)
            if not p:
                return False
            p.disabled = True
            self._persist(p)
        _vmetrics.record("learned_pattern_disabled")
        return True

    def delete(self, pid: str) -> bool:
        with self._lock:
            if pid not in self._patterns:
                return False
            del self._patterns[pid]
            try:
                (_STATE_DIR / f"{pid}.json").unlink(missing_ok=True)
            except Exception:
                pass
            ids = sorted(self._patterns.keys())
            try:
                _INDEX_PATH.write_text(
                    json.dumps({"ids": ids, "updated_utc": _now_iso(), "count": len(ids)}, indent=2),
                    encoding="utf-8",
                )
            except Exception:
                pass
        return True

    def record_use(self, pattern: LearnedPattern, success: bool) -> None:
        with self._lock:
            pattern.last_used_utc = _now_iso()
            pattern.use_count += 1
            if success:
                pattern.validation["passes"] = int(pattern.validation.get("passes", 0)) + 1
            else:
                pattern.validation["fails"] = int(pattern.validation.get("fails", 0)) + 1
                # Auto-disable patterns that fail more than they pass after 3 uses
                if (pattern.validation["fails"] > pattern.validation.get("passes", 0)
                        and pattern.use_count >= 3):
                    pattern.disabled = True
                    self.logger.warning("Pattern %s auto-disabled (fails>passes)", pattern.id)
            self._session_apply_count[pattern.id] = self._session_apply_count.get(pattern.id, 0) + 1
            self._persist(pattern)

    # ---------------- Apply correction ----------------
    def apply_correction(
        self, pattern: LearnedPattern, original_args: Dict[str, Any]
    ) -> Optional[Tuple[str, Dict[str, Any]]]:
        """Build (new_tool, new_args) from pattern + original args. None if cannot apply."""
        try:
            corr = pattern.correction
            tr = corr.transform
            new_args: Dict[str, Any] = dict(tr.static_args or {})
            if tr.extract_arg and tr.regex_extract and tr.target_arg:
                src = str(original_args.get(tr.extract_arg, "") or "")
                m = re.search(tr.regex_extract, src, re.IGNORECASE | re.DOTALL)
                if not m:
                    return None
                # Use first capture group, or full match if no groups
                value = m.group(1) if m.groups() else m.group(0)
                if tr.ascii_strip:
                    try:
                        value.encode("ascii")
                    except UnicodeEncodeError:
                        value = value.encode("ascii", "ignore").decode("ascii")
                new_args[tr.target_arg] = value
            elif tr.target_arg and tr.extract_arg:
                # Pass-through with rename
                value = original_args.get(tr.extract_arg)
                if value is None:
                    return None
                new_args[tr.target_arg] = value
            return (corr.to_tool, new_args)
        except Exception as e:
            self.logger.warning("apply_correction failed for %s: %s", pattern.id, e)
            return None

    # ---------------- LLM abstraction ----------------
    async def abstract_failure(
        self,
        llm,
        tool: str,
        original_args: Dict[str, Any],
        error_text: str,
        available_tools: List[str],
        timeout: float = 30.0,
        tool_signatures: Optional[Dict[str, str]] = None,
    ) -> Optional[LearnedPattern]:
        """Ask LLM to abstract failure into a generalizable correction pattern.

        If tool_signatures is provided (from ToolExecutor._TOOL_SIGNATURES), the
        prompt will include arg names to guide the LLM towards valid target_arg.
        """
        if self._suspended:
            return None
        if len(self._patterns) >= _MAX_PATTERNS:
            self._evict_lru()

        # Recursion guard
        self._suspended = True
        try:
            prompt = self._build_abstraction_prompt(
                tool, original_args, error_text, available_tools, tool_signatures,
            )
            try:
                result = await asyncio.wait_for(
                    llm.query(
                        [{"role": "user", "content": prompt}],
                        model_priority="agent_frontier",
                        max_time=int(timeout),
                    ),
                    timeout=timeout + 5,
                )
            except (asyncio.TimeoutError, Exception) as e:
                self.logger.warning("abstract_failure LLM error: %s", e)
                _vmetrics.record("learned_pattern_abstract_failed")
                return None

            if not result or not result.get("success") or not result.get("content"):
                _vmetrics.record("learned_pattern_abstract_failed")
                return None

            content = result["content"]
            parsed = self._parse_llm_pattern(content)
            if not parsed:
                self.logger.warning(
                    "abstract_failure: LLM content unparseable (first 500 chars): %s",
                    str(content)[:500],
                )
                _vmetrics.record("learned_pattern_parse_failed")
                return None

            # Validate basic shape
            if not parsed.get("error_match_regex") or not parsed.get("to_tool"):
                _vmetrics.record("learned_pattern_invalid")
                return None
            if parsed.get("to_tool") not in available_tools:
                self.logger.warning("LLM proposed unknown tool: %s", parsed.get("to_tool"))
                _vmetrics.record("learned_pattern_unknown_tool")
                return None
            if not parsed.get("generalizable", False):
                _vmetrics.record("learned_pattern_not_generalizable")
                return None
            if float(parsed.get("confidence", 0.0)) < 0.6:
                _vmetrics.record("learned_pattern_low_confidence")
                return None

            # ---- B2: Self-critique pass ----
            # Apply the proposed transform to the original args to detect over-fit.
            # If the extracted value loses too much information, ask LLM to fix.
            critique_ok, critique_reason, parsed = await self._self_critique(
                llm, parsed, original_args, tool, error_text, available_tools, timeout,
            )
            if not critique_ok:
                self.logger.warning(
                    "abstract_failure: critique rejected pattern: %s", critique_reason,
                )
                _vmetrics.record("learned_pattern_critique_failed")
                return None

            # Build LearnedPattern
            pid = _gen_id(error_text, tool)
            pattern = LearnedPattern(
                id=pid,
                created_utc=_now_iso(),
                tool_class=tool,
                error_match_regex=parsed["error_match_regex"],
                correction=CorrectionSpec(
                    kind="rewrite_call",
                    to_tool=parsed["to_tool"],
                    transform=CorrectionTransform(
                        extract_arg=parsed.get("extract_arg"),
                        regex_extract=parsed.get("regex_extract"),
                        target_arg=parsed.get("target_arg"),
                        static_args=parsed.get("static_args", {}),
                        ascii_strip=bool(parsed.get("ascii_strip", False)),
                    ),
                ),
                source="llm_abstracted",
                model_used=result.get("model", ""),
                confidence=float(parsed.get("confidence", 0.7)),
            )
            _vmetrics.record("learned_pattern_created")
            return pattern
        finally:
            self._suspended = False

    # ---------------- B2: Self-critique ----------------
    @staticmethod
    def _simulate_transform(parsed: Dict, original_args: Dict[str, Any]) -> Tuple[Optional[str], str]:
        """Apply the proposed transform to original_args; returns (extracted_value, kind).

        kind: 'regex' | 'passthrough' | 'static_only' | 'invalid'
        """
        extract_arg = parsed.get("extract_arg")
        regex_extract = parsed.get("regex_extract")
        target_arg = parsed.get("target_arg")
        if not target_arg:
            return (None, "invalid")
        if extract_arg and regex_extract:
            src = str(original_args.get(extract_arg, "") or "")
            try:
                m = re.search(regex_extract, src, re.IGNORECASE | re.DOTALL)
            except re.error:
                return (None, "invalid")
            if not m:
                return (None, "regex_no_match")
            value = m.group(1) if m.groups() else m.group(0)
            return (value, "regex")
        if extract_arg and not regex_extract:
            value = original_args.get(extract_arg)
            if value is None:
                return (None, "invalid")
            return (str(value), "passthrough")
        # static-args only path
        return (None, "static_only")

    @staticmethod
    def _check_overfit(
        original_args: Dict[str, Any], extracted: Optional[str], parsed: Dict,
    ) -> Tuple[bool, str]:
        """Returns (is_overfit, reason). True means transform loses essential info."""
        extract_arg = parsed.get("extract_arg")
        if not extract_arg:
            return (False, "no extract_arg, skip overfit check")
        original = str(original_args.get(extract_arg, "") or "").strip()
        if not original:
            return (False, "no original value, skip")
        if extracted is None:
            return (True, f"transform produced None for arg='{extract_arg}'")
        ext = str(extracted).strip()
        if not ext:
            return (True, "transform produced empty string")
        # Length ratio check: if extracted is < 40% of original, suspect over-fit
        ratio = len(ext) / max(len(original), 1)
        if ratio < 0.4:
            return (True, f"extracted len ratio {ratio:.2f} < 0.4 (lost info: orig='{original[:80]}' -> ext='{ext[:80]}')")
        # Token coverage: count significant tokens (>=3 chars) from original present in ext
        orig_tokens = [t for t in re.findall(r"[A-Za-z0-9_\-]+", original) if len(t) >= 3]
        if orig_tokens:
            present = sum(1 for t in orig_tokens if t in ext)
            coverage = present / len(orig_tokens)
            if coverage < 0.5:
                return (True, f"token coverage {coverage:.2f} < 0.5 (orig tokens: {orig_tokens[:5]}, missing in extracted)")
        return (False, "ok")

    async def _self_critique(
        self,
        llm,
        parsed: Dict,
        original_args: Dict[str, Any],
        tool: str,
        error_text: str,
        available_tools: List[str],
        timeout: float,
    ) -> Tuple[bool, str, Dict]:
        """B2: Detect transform over-fit; ask LLM to regenerate once if needed.

        Returns (ok, reason, parsed_final). parsed_final may be the original or revised.
        """
        extracted, kind = self._simulate_transform(parsed, original_args)
        is_overfit, reason = self._check_overfit(original_args, extracted, parsed)
        if not is_overfit:
            _vmetrics.record("learned_pattern_critique_passed")
            return (True, f"first-pass ok ({kind})", parsed)

        _vmetrics.record("learned_pattern_overfit_detected")
        self.logger.info("self_critique: over-fit detected: %s", reason)

        # Build critique prompt with concrete failure
        original_value = str(original_args.get(parsed.get("extract_arg", ""), "") or "")
        ext_str = str(extracted) if extracted is not None else "<None>"
        critique_prompt = (
            "Tu propuesta anterior tiene un problema de OVER-FIT. Cuando se aplica "
            f"a los args reales:\n"
            f"  original_args[{parsed.get('extract_arg')}] = '{original_value[:200]}'\n"
            f"  regex_extract = '{parsed.get('regex_extract')}'\n"
            f"  ----> valor extraido = '{ext_str[:200]}'\n\n"
            f"Diagnostico: {reason}\n\n"
            "Tu transform pierde informacion esencial. Regenera el JSON con un "
            "regex_extract MAS AMPLIO (ej. '(.+)' o el comando completo) o usa "
            "extract_arg sin regex_extract para pass-through, de modo que el "
            "valor final preserve el comando/intencion completos.\n\n"
            "Devuelve SOLO el JSON corregido, mismo schema que antes:\n"
            '{"error_match_regex":..., "to_tool":..., "extract_arg":..., '
            '"regex_extract":..., "target_arg":..., "static_args":{}, '
            '"ascii_strip":false, "generalizable":true, "confidence":<0.6-1.0>, '
            '"rationale":"..."}\n'
        )
        try:
            result = await asyncio.wait_for(
                llm.query(
                    [{"role": "user", "content": critique_prompt}],
                    model_priority="agent_frontier",
                    max_time=int(timeout),
                ),
                timeout=timeout + 5,
            )
        except Exception as e:
            self.logger.warning("self_critique LLM error: %s", e)
            return (False, f"critique LLM error: {e}", parsed)

        if not result or not result.get("success") or not result.get("content"):
            return (False, "critique LLM returned empty", parsed)
        revised = self._parse_llm_pattern(result["content"])
        if not revised:
            return (False, "critique response unparseable", parsed)
        if not revised.get("error_match_regex") or not revised.get("to_tool"):
            return (False, "critique response invalid shape", parsed)
        if revised.get("to_tool") not in available_tools:
            return (False, f"critique proposed unknown tool: {revised.get('to_tool')}", parsed)

        # Re-check overfit on revised
        extracted2, kind2 = self._simulate_transform(revised, original_args)
        is_overfit2, reason2 = self._check_overfit(original_args, extracted2, revised)
        if is_overfit2:
            return (False, f"critique still over-fits: {reason2}", parsed)

        _vmetrics.record("learned_pattern_critique_recovered")
        self.logger.info("self_critique: recovered with revised transform (%s)", kind2)
        return (True, f"recovered after critique ({kind2})", revised)

    def add_validated(self, pattern: LearnedPattern) -> None:
        """Persist a pattern that has been validated by SelfTester."""
        with self._lock:
            self._patterns[pattern.id] = pattern
            self._persist(pattern)
        _vmetrics.record("learned_pattern_validated")

    def _evict_lru(self) -> None:
        with self._lock:
            if len(self._patterns) < _MAX_PATTERNS:
                return
            sorted_pats = sorted(
                self._patterns.values(),
                key=lambda p: (p.use_count, p.last_used_utc or p.created_utc),
            )
            to_evict = sorted_pats[: max(1, len(self._patterns) - _MAX_PATTERNS + 10)]
            for p in to_evict:
                self._patterns.pop(p.id, None)
                try:
                    (_STATE_DIR / f"{p.id}.json").unlink(missing_ok=True)
                except Exception:
                    pass
            self.logger.info("Evicted %d LRU patterns", len(to_evict))

    @staticmethod
    def _build_abstraction_prompt(
        tool: str,
        args: Dict[str, Any],
        error_text: str,
        available_tools: List[str],
        tool_signatures: Optional[Dict[str, str]] = None,
    ) -> str:
        args_preview = json.dumps(args, default=str)[:600]
        err_preview = (error_text or "")[:1500]

        # B3a: Include tool signatures so LLM knows required args
        if tool_signatures:
            # Show only likely-relevant tools (run_*, check_*, etc) + first 20 others
            priority = [t for t in available_tools if t.startswith(("run_", "check_", "get_", "list_"))]
            others = [t for t in available_tools if t not in priority][:20]
            show = priority + others
            tools_section_lines = []
            for t in show[:40]:
                sig = tool_signatures.get(t, "()")
                tools_section_lines.append(f"  {t}{sig}")
            tools_section = "\n".join(tools_section_lines)
        else:
            tools_section = ", ".join(available_tools[:60])

        return (
            "Eres un meta-agente de auto-correccion. Una herramienta fallo. Tu trabajo es proponer un "
            "PATRON GENERALIZABLE para corregir esta clase de fallos en el futuro, NO solo este caso.\n\n"
            f"=== FALLO ===\n"
            f"tool: {tool}\n"
            f"args: {args_preview}\n"
            f"error_output: {err_preview}\n\n"
            f"=== TOOLS DISPONIBLES (con firmas de args) ===\n{tools_section}\n\n"
            "=== TAREA ===\n"
            "Devuelve SOLO un JSON valido (sin markdown, sin texto extra) con esta estructura exacta:\n"
            "{\n"
            '  "error_match_regex": "<regex case-insensitive que matchea el error_output>",\n'
            '  "to_tool": "<nombre exacto de tool destino>",\n'
            '  "extract_arg": "<arg del original a extraer, o null>",\n'
            '  "regex_extract": "<regex con grupo de captura para extraer valor, o null>",\n'
            '  "target_arg": "<arg destino en el nuevo tool (DEBE ser un arg valido de to_tool)>",\n'
            '  "static_args": {"<arg>": "<valor>"},\n'
            '  "ascii_strip": false,\n'
            '  "generalizable": true,\n'
            '  "confidence": 0.0-1.0,\n'
            '  "rationale": "<una linea explicando el patron>"\n'
            "}\n\n"
            "REGLAS:\n"
            "- generalizable=true SOLO si el patron aplicaria a OTRO caso similar (no solo este).\n"
            "- error_match_regex debe ser ESPECIFICO (no '.*'), capturar el sintoma del fallo.\n"
            "- Si no podes proponer un patron generalizable, devuelve {\"generalizable\": false, \"confidence\": 0}.\n"
            "- confidence debe ser >=0.6 para ser usable.\n"
            "- to_tool DEBE estar en la lista de tools disponibles.\n"
            "- target_arg DEBE coincidir con un arg de la firma de to_tool (ej: run_powershell tiene 'script').\n"
            "- regex_extract debe tener UN grupo de captura para el valor a transferir.\n"
        )

    @staticmethod
    def _parse_llm_pattern(content: str) -> Optional[Dict]:
        if not content:
            return None
        text = content.strip()
        # Strip markdown code fences (```json ... ``` or ``` ... ```)
        fence_match = re.search(r"```(?:json|JSON)?\s*\n?(.*?)\n?```", text, re.DOTALL)
        if fence_match:
            text = fence_match.group(1).strip()
        # Try direct parse
        try:
            return json.loads(text)
        except Exception:
            pass
        # Try extract first {...} block (greedy to last brace)
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if m:
            candidate = m.group(0)
            try:
                return json.loads(candidate)
            except Exception:
                pass
            # Try trimming trailing junk
            for end in range(len(candidate), 0, -1):
                if candidate[end - 1] == "}":
                    try:
                        return json.loads(candidate[:end])
                    except Exception:
                        continue
        return None
