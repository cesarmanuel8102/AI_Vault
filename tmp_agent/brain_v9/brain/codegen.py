"""
Brain V9 — CodeGen Module
=========================
Dedicated LLM client for autonomous code generation.
Uses qwen3-coder:480b-cloud (Ollama cloud) for patch generation,
with qwen2.5-coder:14b (local) as fallback.

Separated from the chat LLM to avoid model-swap contention
and to allow independent timeout/context-window tuning.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any, Dict, List, Optional

from aiohttp import ClientSession, ClientTimeout, ClientConnectorError

log = logging.getLogger("CodeGen")

OLLAMA_CHAT_URL = "http://localhost:11434/api/chat"

# Model chain: cloud first (fast, 480B), local fallback (14B)
CODEGEN_MODELS = [
    {
        "key": "qwen3_coder_480b_cloud",
        "model": "qwen3-coder:480b-cloud",
        "timeout": 120,
        "local": False,
        "num_predict": 8192,
        "num_ctx": 32768,
        "temperature": 0.2,   # Low temp for precise code generation
    },
    {
        "key": "qwen25_coder_14b",
        "model": "qwen2.5-coder:14b",
        "timeout": 180,       # Local 14B is slower
        "local": True,
        "num_predict": 4096,
        "num_ctx": 8192,
        "temperature": 0.2,
    },
]

# Diagnostics model: fast local llama for pattern analysis (no code generation)
DIAGNOSTICS_MODEL = {
    "key": "llama8b_diag",
    "model": "llama3.1:8b",
    "timeout": 30,
    "local": True,
    "num_predict": 2048,
    "num_ctx": 8192,
    "temperature": 0.3,
}


class CodeGenClient:
    """Async client for code generation via Ollama."""

    def __init__(self):
        self._session: Optional[ClientSession] = None
        self.metrics = {
            "total_requests": 0,
            "successful": 0,
            "failed": 0,
            "fallbacks": 0,
            "avg_latency_s": 0.0,
        }

    async def _get_session(self, timeout: int = 120) -> ClientSession:
        if self._session is not None and not self._session.closed:
            return self._session
        # Close stale session if needed
        if self._session is not None:
            try:
                await self._session.close()
            except Exception:
                pass
        self._session = ClientSession(timeout=ClientTimeout(total=timeout))
        return self._session

    async def _call_ollama(
        self,
        model_cfg: Dict,
        messages: List[Dict],
    ) -> str:
        """Send a chat completion request to Ollama and return the response text."""
        timeout = model_cfg["timeout"]
        session = await self._get_session(timeout)
        payload = {
            "model": model_cfg["model"],
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": model_cfg.get("temperature", 0.2),
                "num_predict": model_cfg.get("num_predict", 4096),
                "num_ctx": model_cfg.get("num_ctx", 16384),
            },
        }
        async with session.post(
            OLLAMA_CHAT_URL,
            json=payload,
            timeout=ClientTimeout(total=timeout),
        ) as resp:
            if resp.status != 200:
                body = await resp.text()
                raise RuntimeError(f"Ollama HTTP {resp.status}: {body[:500]}")
            data = await resp.json()
            content = data.get("message", {}).get("content", "")
            if not content:
                raise RuntimeError("Ollama returned empty response")
            return content

    async def generate_patch(
        self,
        issue: Dict[str, Any],
        file_contents: Dict[str, str],
        max_retries: int = 2,
    ) -> Dict[str, Any]:
        """Generate a code patch for a diagnosed issue.

        Args:
            issue: Structured issue from trade_diagnostics, containing:
                - issue_id, title, description, severity
                - affected_file, affected_lines (optional)
                - evidence: dict with supporting data
                - suggested_fix: human-readable description of what to change
            file_contents: {file_path: file_content} for files the model needs to see
            max_retries: retry count if generation fails validation

        Returns:
            {
                "success": bool,
                "patch": {file_path: {"old": str, "new": str}} or None,
                "model_used": str,
                "reasoning": str,  # Model's explanation
                "latency_s": float,
                "retries": int,
            }
        """
        self.metrics["total_requests"] += 1
        start = time.time()

        # Build the prompt
        system_prompt = self._build_system_prompt()
        user_prompt = self._build_patch_prompt(issue, file_contents)
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        last_error = None
        for attempt in range(max_retries + 1):
            for idx, model_cfg in enumerate(CODEGEN_MODELS):
                try:
                    if idx > 0:
                        self.metrics["fallbacks"] += 1
                        log.info("Codegen fallback to %s", model_cfg["key"])

                    raw_response = await self._call_ollama(model_cfg, messages)
                    parsed = self._parse_patch_response(raw_response)

                    if parsed.get("success"):
                        latency = time.time() - start
                        self.metrics["successful"] += 1
                        self._update_avg_latency(latency)
                        return {
                            "success": True,
                            "patch": parsed["patch"],
                            "model_used": model_cfg["model"],
                            "model_key": model_cfg["key"],
                            "reasoning": parsed.get("reasoning", ""),
                            "latency_s": round(latency, 2),
                            "retries": attempt,
                            "raw_response_length": len(raw_response),
                        }
                    else:
                        last_error = parsed.get("error", "Failed to parse patch from response")
                        log.warning(
                            "Codegen attempt %d/%d with %s: parse failed: %s",
                            attempt + 1, max_retries + 1, model_cfg["key"], last_error
                        )
                        # Add the failed response as context for retry
                        if attempt < max_retries:
                            messages.append({"role": "assistant", "content": raw_response})
                            messages.append({
                                "role": "user",
                                "content": (
                                    f"Your response could not be parsed: {last_error}\n"
                                    "Please respond again with the EXACT format specified. "
                                    "Make sure to include the JSON patch block."
                                ),
                            })
                        break  # Retry with same chain, not next model

                except asyncio.TimeoutError:
                    last_error = f"{model_cfg['key']}: timeout ({model_cfg['timeout']}s)"
                    log.warning("Codegen timeout on %s", model_cfg["key"])
                except ClientConnectorError as e:
                    last_error = f"{model_cfg['key']}: connection failed: {e}"
                    log.warning("Codegen connection failed on %s: %s", model_cfg["key"], e)
                except Exception as e:
                    last_error = f"{model_cfg['key']}: {type(e).__name__}: {e}"
                    log.error("Codegen error on %s: %s: %s", model_cfg["key"], type(e).__name__, e)

                if idx < len(CODEGEN_MODELS) - 1:
                    await asyncio.sleep(1)

        latency = time.time() - start
        self.metrics["failed"] += 1
        return {
            "success": False,
            "patch": None,
            "model_used": None,
            "reasoning": None,
            "error": last_error,
            "latency_s": round(latency, 2),
            "retries": max_retries,
        }

    async def analyze_diagnostics(
        self,
        diagnostic_prompt: str,
    ) -> Dict[str, Any]:
        """Use the fast local model for diagnostic analysis (not code generation).

        Returns structured JSON analysis of trade patterns.
        """
        messages = [
            {
                "role": "system",
                "content": (
                    "You are a trading system diagnostician. Analyze the provided data "
                    "and return ONLY a JSON object (no markdown, no explanation outside JSON). "
                    "Identify patterns, anomalies, and recurring failures."
                ),
            },
            {"role": "user", "content": diagnostic_prompt},
        ]
        try:
            raw = await self._call_ollama(DIAGNOSTICS_MODEL, messages)
            # Try to extract JSON from response
            return {"success": True, "analysis": self._extract_json(raw), "raw": raw}
        except Exception as e:
            log.warning("Diagnostics analysis failed: %s", e)
            return {"success": False, "error": str(e), "analysis": None}

    # ── Prompt Construction ──────────────────────────────────────────────────

    def _build_system_prompt(self) -> str:
        return """You are an expert code surgeon for an autonomous trading system called Brain V9.
Your job is to generate precise, minimal code patches to fix diagnosed issues.

RULES:
1. Generate the MINIMUM change needed. Do not refactor unrelated code.
2. Preserve existing code style, indentation, and naming conventions.
3. Every patch must be syntactically valid in the target language (Python or JavaScript).
4. Always respond with your reasoning first, then the patch in the EXACT format below.

RESPONSE FORMAT:
```reasoning
<explain what the issue is and what your fix does, 2-5 sentences>
```

```patch
{
  "C:/AI_VAULT/tmp_agent/brain_v9/trading/signal_engine.py": {
    "old": "exact string to find in the file (multi-line ok, must match exactly)",
    "new": "replacement string"
  }
}
```

CRITICAL:
- The JSON keys MUST be the ACTUAL FULL FILE PATHS from the "FILE CONTENTS" section below (e.g. "C:/AI_VAULT/tmp_agent/brain_v9/trading/signal_engine.py"). NEVER use a placeholder like "file_path".
- The "old" string MUST exist verbatim in the current file content. Copy it exactly.
- You may include multiple files in one patch object — each key is a real file path.
- If a file needs multiple changes, use an array: [{"old": ..., "new": ...}, ...]
- Do NOT include line numbers in old/new strings.
- Do NOT wrap code in markdown code blocks inside the JSON strings.
"""

    def _build_patch_prompt(
        self,
        issue: Dict[str, Any],
        file_contents: Dict[str, str],
    ) -> str:
        parts = []
        parts.append(f"## ISSUE: {issue.get('title', 'Unknown')}")
        parts.append(f"**Severity:** {issue.get('severity', 'unknown')}")
        parts.append(f"**Description:** {issue.get('description', '')}")
        if issue.get("suggested_fix"):
            parts.append(f"**Suggested Fix:** {issue['suggested_fix']}")
        if issue.get("evidence"):
            parts.append(f"**Evidence:** {json.dumps(issue['evidence'], indent=2, default=str)[:3000]}")

        parts.append("\n## FILE CONTENTS:")
        for fpath, content in file_contents.items():
            # Truncate very large files but include enough context
            if len(content) > 15000:
                # Include first and last sections + area around affected lines
                affected_lines = issue.get("affected_lines", [])
                if affected_lines:
                    start_line = max(0, min(affected_lines) - 30)
                    end_line = max(affected_lines) + 30
                    lines = content.split("\n")
                    relevant = "\n".join(lines[start_line:end_line])
                    content = (
                        f"[Lines 1-50]\n" + "\n".join(lines[:50]) +
                        f"\n\n[... truncated ...]\n\n[Lines {start_line+1}-{end_line+1} (AFFECTED AREA)]\n" +
                        relevant +
                        f"\n\n[... truncated ...]\n\n[Lines {len(lines)-20}-{len(lines)}]\n" +
                        "\n".join(lines[-20:])
                    )
            parts.append(f"\n### {fpath}\n```\n{content}\n```")

        parts.append(
            "\nGenerate the minimal patch to fix this issue. "
            "Remember: the 'old' string must match EXACTLY what's in the file."
        )
        return "\n".join(parts)

    # ── Response Parsing ─────────────────────────────────────────────────────

    def _parse_patch_response(self, raw: str) -> Dict[str, Any]:
        """Parse the model's response to extract reasoning and patch."""
        reasoning = ""
        patch = None

        # Extract reasoning block
        if "```reasoning" in raw:
            try:
                r_start = raw.index("```reasoning") + len("```reasoning")
                r_end = raw.index("```", r_start)
                reasoning = raw[r_start:r_end].strip()
            except ValueError:
                pass

        # Extract patch JSON block
        patch_json_str = None
        if "```patch" in raw:
            try:
                p_start = raw.index("```patch") + len("```patch")
                p_end = raw.index("```", p_start)
                patch_json_str = raw[p_start:p_end].strip()
            except ValueError:
                pass

        # Fallback: look for any JSON block with "old"/"new" keys
        if not patch_json_str:
            # Try to find JSON in ```json blocks
            for marker in ["```json", "```"]:
                if marker in raw:
                    try:
                        idx = raw.index(marker) + len(marker)
                        end = raw.index("```", idx)
                        candidate = raw[idx:end].strip()
                        if '"old"' in candidate and '"new"' in candidate:
                            patch_json_str = candidate
                            break
                    except ValueError:
                        continue

        if not patch_json_str:
            return {"success": False, "error": "No patch block found in response", "reasoning": reasoning}

        try:
            patch_data = json.loads(patch_json_str)
        except json.JSONDecodeError as e:
            return {"success": False, "error": f"Invalid JSON in patch: {e}", "reasoning": reasoning}

        # Normalize: ensure patch_data is {filepath: changes}
        if not isinstance(patch_data, dict):
            return {"success": False, "error": "Patch must be a JSON object", "reasoning": reasoning}

        # Validate structure
        normalized = {}
        for fpath, changes in patch_data.items():
            if isinstance(changes, dict) and "old" in changes and "new" in changes:
                normalized[fpath] = [changes]
            elif isinstance(changes, list):
                valid = all(isinstance(c, dict) and "old" in c and "new" in c for c in changes)
                if not valid:
                    return {"success": False, "error": f"Invalid change format for {fpath}", "reasoning": reasoning}
                normalized[fpath] = changes
            else:
                return {"success": False, "error": f"Unexpected format for {fpath}", "reasoning": reasoning}

        if not normalized:
            return {"success": False, "error": "Empty patch", "reasoning": reasoning}

        return {"success": True, "patch": normalized, "reasoning": reasoning}

    def _extract_json(self, raw: str) -> Optional[Dict]:
        """Try to extract a JSON object from a text response."""
        # Try direct parse
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            pass
        # Try extracting from code block
        for marker in ["```json", "```"]:
            if marker in raw:
                try:
                    start = raw.index(marker) + len(marker)
                    end = raw.index("```", start)
                    return json.loads(raw[start:end].strip())
                except (ValueError, json.JSONDecodeError):
                    continue
        # Try finding first { to last }
        first_brace = raw.find("{")
        last_brace = raw.rfind("}")
        if first_brace != -1 and last_brace > first_brace:
            try:
                return json.loads(raw[first_brace:last_brace + 1])
            except json.JSONDecodeError:
                pass
        return None

    def _update_avg_latency(self, new_latency: float):
        n = self.metrics["successful"]
        if n <= 1:
            self.metrics["avg_latency_s"] = new_latency
        else:
            self.metrics["avg_latency_s"] = (
                self.metrics["avg_latency_s"] * (n - 1) + new_latency
            ) / n

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()
