"""B7-STRANGLER-02: ChatMetrics module (extracted from brain_v9.core.session).

This module contains the ChatMetrics class plus its process-wide singleton
accessor (get_chat_metrics) and supporting globals. It was extracted verbatim
from brain_v9/core/session.py during the B7 strangler refactor to reduce the
size of session.py and isolate metrics logic.

Backward compatibility is preserved: brain_v9.core.session re-exports
ChatMetrics, get_chat_metrics, _GLOBAL_CHAT_METRICS_LOCK and proxies
_GLOBAL_CHAT_METRICS via PEP 562 __getattr__.

Public API:
    - ChatMetrics
    - get_chat_metrics() -> ChatMetrics
    - _GLOBAL_CHAT_METRICS (module-level singleton; mutated by get_chat_metrics)
    - _GLOBAL_CHAT_METRICS_LOCK

No behavioral change vs. pre-extraction code.
"""

from __future__ import annotations

import json
import logging
import re  # noqa: F401  (used by some methods via local references)
import statistics  # noqa: F401  (used by trend/coherence analytics)
import threading as _threading
from typing import Dict, List, Optional, Tuple  # noqa: F401

from brain_v9.config import BASE_PATH

# Module-level logger (mirrors brain_v9.core.session "BrainSession" logger).
# ChatMetrics methods reference `log.info(...)` / `log.debug(...)` inside
# try/except blocks; without this binding NameError would be silently swallowed
# and the trailing diagnostic line would be lost. Defining it here restores
# parity with the pre-extraction behavior in session.py.
log = logging.getLogger("BrainSession")

# NO_TOOL_MARKERS: imported defensively to mirror session.py behavior.
try:
    from brain_v9.core.routing.guards import NO_TOOL_MARKERS
except ImportError:  # pragma: no cover - defensive fallback
    NO_TOOL_MARKERS = ()  # type: ignore[assignment]

# Mirror of session.py:_CHAT_METRICS_PATH (same BASE_PATH, idempotent constant).
_STATE_PATH = BASE_PATH / "tmp_agent" / "state"
_CHAT_METRICS_PATH = _STATE_PATH / "brain_metrics" / "chat_metrics_latest.json"


# ── Chat Metrics Collector ────────────────────────────────────────────────────

class ChatMetrics:
    """Lightweight conversation-level metrics for self-improvement impact measurement.

    Tracks per-route counts, success/failure, latency, and error types.
    Persists to disk every _PERSIST_EVERY conversations so the self-improvement
    pipeline can measure before/after impact of chat-related code changes.
    """

    _PERSIST_EVERY = 1  # R7.4: persist every chat (~3KB write, cheap; gives observability immediacy)

    def __init__(self):
        self.data = {
            "total_conversations": 0,
            "success": 0,
            "failed": 0,
            "routes": {"command": 0, "fastpath": 0, "agent": 0, "llm": 0},
            "agent_tool_calls_ok": 0,
            "agent_tool_calls_fail": 0,
            "avg_latency_ms": 0.0,
            "ghost_completion_count": 0,
            "tool_markup_leak_count": 0,
            "canned_no_result_count": 0,
            "errors": {},          # error_type -> count
            # R4.1: per-validator firings (R3/R3.1 quality guards). Lets us
            # see which guard catches the most LLM mistakes over time.
            "validators": {},      # validator_name -> count
            "last_updated": None,
            # F1-OBS: Routing observability log (last 100 decisions)
            "routing_log": [],       # List of routing decisions with candidates
        }
        self._load()

    def _load(self):
        try:
            if _CHAT_METRICS_PATH.exists():
                saved = json.loads(_CHAT_METRICS_PATH.read_text(encoding="utf-8"))
                for key in ("total_conversations", "success", "failed",
                            "agent_tool_calls_ok", "agent_tool_calls_fail",
                            "ghost_completion_count", "tool_markup_leak_count",
                            "canned_no_result_count"):
                    if key in saved:
                        self.data[key] = int(saved[key])
                if "avg_latency_ms" in saved:
                    self.data["avg_latency_ms"] = float(saved["avg_latency_ms"])
                if isinstance(saved.get("routes"), dict):
                    for r in self.data["routes"]:
                        self.data["routes"][r] = int(saved["routes"].get(r, 0))
                if isinstance(saved.get("errors"), dict):
                    self.data["errors"] = {k: int(v) for k, v in saved["errors"].items()}
                if isinstance(saved.get("validators"), dict):
                    self.data["validators"] = {k: int(v) for k, v in saved["validators"].items()}
                # F1-OBS: Load routing log if present
                if isinstance(saved.get("routing_log"), list):
                    self.data["routing_log"] = saved["routing_log"][-100:]
                log.info("Chat metrics loaded: %d conversations", self.data["total_conversations"])
        except Exception:
            pass

    def record(self, route: str, success: bool, latency_ms: float,
               error_type: str = "", agent_steps: int = 0,
               agent_ok: int = 0, agent_fail: int = 0):
        """Record a single conversation outcome."""
        self.data["total_conversations"] += 1
        if success:
            self.data["success"] += 1
        else:
            self.data["failed"] += 1
        self.data["routes"][route] = self.data["routes"].get(route, 0) + 1
        self.data["agent_tool_calls_ok"] += agent_ok
        self.data["agent_tool_calls_fail"] += agent_fail
        if error_type:
            self.data["errors"][error_type] = self.data["errors"].get(error_type, 0) + 1

        # Running average latency
        n = self.data["total_conversations"]
        if n <= 1:
            self.data["avg_latency_ms"] = latency_ms
        else:
            self.data["avg_latency_ms"] = (
                self.data["avg_latency_ms"] * (n - 1) + latency_ms
            ) / n

        if self.data["total_conversations"] % self._PERSIST_EVERY == 0:
            self._persist()

    def record_response_quality(self, content: str, agent_status: str = ""):
        """Track visible chat regressions that the structural metrics miss."""
        text = str(content or "")
        lowered = text.lower()
        if agent_status == "ghost_completion":
            self.data["ghost_completion_count"] += 1
        if "<function_calls" in lowered or "<invoke name=" in lowered:
            self.data["tool_markup_leak_count"] += 1
        if (
            "no obtuve resultados para esta consulta" in lowered
            or "*[resumen extractivo" in lowered
        ):
            self.data["canned_no_result_count"] += 1
        self._persist()

    def record_validator(self, name: str, count: int = 1):
        """R4.1: Increment a validator firing counter.

        Validator names (canonical):
          - speculation_blocked: R3 _SPECULATION_RE caught speculative verbs
          - file_claim_failed:   R3 _FILE_CLAIM_RE flagged unevidenced "creé X"
          - leak_tail_blocked:   R3 _LEAK_TAIL_RE caught chain-of-thought leak
          - cold_start_guard:    R3.1 short msg <90s after restart
          - wall_clock_timeout:  R3.1 60s tool timeout fired
          - tool_name_corrected: R4.2 LLM hallucinated tool name auto-mapped
          - num_predict_capped:  R4.3 kimi context overflow prevented
          - retry_on_validation: R3 retry triggered by failed validation
        """
        try:
            self.data["validators"][name] = self.data["validators"].get(name, 0) + int(count)
        except Exception:
            pass

    def snapshot(self) -> dict:
        """Return a copy of current metrics (for impact measurement)."""
        # R4.1: merge live validator counters from the global module-level
        # registry so they always reflect the current process state.
        try:
            from brain_v9.core import validator_metrics as _vm
            live_validators = _vm.snapshot()
            for k, v in live_validators.items():
                self.data["validators"][k] = max(self.data["validators"].get(k, 0), v)
        except Exception:
            pass
        return {
            **self.data,
            "success_rate": (
                self.data["success"] / max(self.data["total_conversations"], 1)
            ),
            "fastpath_rate": (
                self.data["routes"].get("fastpath", 0) /
                max(self.data["total_conversations"], 1)
            ),
            "validator_total_fires": sum(self.data.get("validators", {}).values()),
        }

    def _persist(self):
        try:
            _CHAT_METRICS_PATH.parent.mkdir(parents=True, exist_ok=True)
            import time as _t
            # R4.1: merge live module-level validator counters before writing
            # so the on-disk file always reflects the current process state.
            try:
                from brain_v9.core import validator_metrics as _vm
                live = _vm.snapshot()
                for k, v in live.items():
                    self.data["validators"][k] = max(
                        self.data["validators"].get(k, 0), int(v)
                    )
            except Exception:
                pass
            payload = {**self.data, "last_updated": _t.strftime("%Y-%m-%dT%H:%M:%S")}
            _CHAT_METRICS_PATH.write_text(
                json.dumps(payload, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception:
            pass

    def force_persist(self):
        """Persist immediately (called on shutdown)."""
        self._persist()

    def record_routing_decision(
        self,
        message: str,
        selected_route: str,
        candidates: List[Dict],
        guards_triggered: List[str],
        latency_ms: float,
        timestamp: Optional[str] = None,
    ):
        """F1-OBS: Record a routing decision with all candidates evaluated.
        
        This enables post-hoc analysis of routing patterns, overfire detection,
        and arbitration quality without affecting live routing decisions.
        
        Args:
            message: The user message (truncated for privacy)
            selected_route: The route that was actually selected
            candidates: List of {"name": str, "score": float, "blocked": bool, "reason": str}
            guards_triggered: List of negative guards that fired
            latency_ms: Time taken to make routing decision
            timestamp: ISO format timestamp (auto-generated if None)
        """
        try:
            import time as _time
            
            entry = {
                "timestamp": timestamp or _time.strftime("%Y-%m-%dT%H:%M:%S"),
                "message_preview": message[:200] if message else "",
                "selected_route": selected_route,
                "candidates": candidates,
                "guards_triggered": guards_triggered,
                "decision_latency_ms": round(latency_ms, 2),
            }
            
            # Keep only last 100 entries (circular buffer)
            self.data["routing_log"].append(entry)
            if len(self.data["routing_log"]) > 100:
                self.data["routing_log"] = self.data["routing_log"][-100:]
            
            # F1-OBS: Persist routing log separately for real-time analysis
            # This is lightweight and enables overfire detection
            self._persist_routing_log_slice()
        except Exception as e:
            log.debug("record_routing_decision failed: %s", e)
    
    def _persist_routing_log_slice(self):
        """Persist last 10 routing decisions for real-time monitoring."""
        try:
            import json as _json
            import time as _time
            
            slice_path = _CHAT_METRICS_PATH.parent / "routing_log_recent.json"
            recent = self.data["routing_log"][-10:] if self.data["routing_log"] else []
            payload = {
                "entries": recent,
                "total_recorded": len(self.data["routing_log"]),
                "last_updated": _time.strftime("%Y-%m-%dT%H:%M:%S"),
            }
            slice_path.write_text(
                _json.dumps(payload, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception:
            pass
    
    def get_routing_stats(self) -> Dict:
        """F1-OBS: Calculate routing statistics for analysis.
        
        Returns:
            Dict with route distribution, guard frequency, candidate counts
        """
        if not self.data["routing_log"]:
            return {"error": "No routing data available"}
        
        from collections import Counter
        
        routes = Counter(e["selected_route"] for e in self.data["routing_log"])
        guards = Counter()
        for entry in self.data["routing_log"]:
            for guard in entry.get("guards_triggered", []):
                guards[guard] += 1
        
        avg_candidates = sum(
            len(e.get("candidates", [])) 
            for e in self.data["routing_log"]
        ) / len(self.data["routing_log"])
        
        return {
            "total_decisions": len(self.data["routing_log"]),
            "route_distribution": dict(routes),
            "guard_frequency": dict(guards),
            "avg_candidates_evaluated": round(avg_candidates, 2),
            "recent_overfire_candidates": self._detect_overfire_candidates(),
        }
    
    def _detect_overfire_candidates(self) -> List[Dict]:
        """F1-OBS: Detect potentially problematic routing patterns.
        
        Returns list of suspicious routing decisions for manual review.
        """
        suspicious = []
        
        for entry in self.data["routing_log"][-20:]:  # Last 20 decisions
            msg_preview = entry.get("message_preview", "").lower()
            selected = entry.get("selected_route", "")
            candidates = entry.get("candidates", [])
            
            # Pattern 1: Trading fastpath with routing terms in message
            if selected == "trading_analysis" and any(
                term in msg_preview for term in [
                    "brainsession", "/chat", "route=", "router", "routing",
                    "pipeline conversacional", "no analices trading"
                ]
            ):
                suspicious.append({
                    "pattern": "trading_hijack",
                    "entry": entry,
                    "risk": "Trading fastpath captured non-trading query",
                })
            
            # Pattern 2: High-scoring candidate was blocked
            blocked_high_score = [
                c for c in candidates 
                if c.get("blocked") and c.get("score", 0) > 0.8
            ]
            if blocked_high_score:
                suspicious.append({
                    "pattern": "high_score_blocked",
                    "entry": entry,
                    "risk": f"High-score candidate blocked: {[c['name'] for c in blocked_high_score]}",
                })
            
            # Pattern 3: UI edit with analysis terms
            if selected == "grounded_ui_edit_fastpath" and any(
                term in msg_preview for term in [
                    "analiza", "no modifiques", "sin herramientas", "solo explica"
                ]
            ):
                suspicious.append({
                    "pattern": "ui_edit_overfire",
                    "entry": entry,
                    "risk": "UI edit triggered on analysis request",
                })
        
        return suspicious

    # ═══════════════════════════════════════════════════════════════════════════
    # FASE 2: OVERFIRE ANALYTICS
    # ═══════════════════════════════════════════════════════════════════════════
    
    def get_overfire_analytics(self, window_size: int = 100) -> Dict:
        """F2-OA: Comprehensive overfire analytics for routing quality monitoring.
        
        Detects and analyzes problematic routing patterns including:
        - trading hijack: trading fastpath capturing non-trading queries
        - ui_edit_overfire: UI edit activating on analysis requests  
        - agent_overuse: agent routed to ghost-prone queries
        - high_score_blocked: better candidate was blocked
        - repeated_fastpath: same fastpath activating on semantically diverse queries
        
        Args:
            window_size: Number of recent decisions to analyze (default 100)
            
        Returns:
            Dict with patterns, severity scores, recommendations, and actionable insights
        """
        if not self.data.get("routing_log"):
            return {
                "status": "no_data",
                "message": "No routing decisions recorded yet",
                "patterns": [],
                "summary": {},
            }
        
        from collections import Counter, defaultdict
        import time as _time
        
        recent_log = self.data["routing_log"][-window_size:]
        total_analyzed = len(recent_log)
        
        # Pattern detection containers
        patterns = []
        pattern_counts = Counter()
        route_distribution = Counter()
        guard_frequency = Counter()
        
        # Specific pattern tracking
        trading_hijacks = []
        ui_edit_overfires = []
        agent_overuse = []
        high_score_blockeds = []
        repeated_fastpaths = defaultdict(list)
        
        # Analyze each entry
        for idx, entry in enumerate(recent_log):
            msg_preview = entry.get("message_preview", "").lower()
            selected = entry.get("selected_route", "")
            candidates = entry.get("candidates", [])
            guards = entry.get("guards_triggered", [])
            
            route_distribution[selected] += 1
            for guard in guards:
                guard_frequency[guard] += 1
            
            # Pattern 1: Trading hijack
            if selected == "trading_analysis" or "trading" in selected:
                routing_terms = ["brainsession", "/chat", "route=", "router", 
                                "routing", "pipeline conversacional", 
                                "no analices trading", "conversacional"]
                if any(term in msg_preview for term in routing_terms):
                    pattern_counts["trading_hijack"] += 1
                    trading_hijacks.append({
                        "index": idx,
                        "timestamp": entry.get("timestamp"),
                        "message": msg_preview[:100],
                        "severity": "high",
                    })
            
            # Pattern 2: UI edit overfire
            if selected == "grounded_ui_edit_fastpath":
                analysis_terms = ["analiza", "no modifiques", "sin herramientas", 
                                 "solo explica", "solo analiza", "no edites",
                                 "no cambies", "sin cambios"]
                if any(term in msg_preview for term in analysis_terms):
                    pattern_counts["ui_edit_overfire"] += 1
                    ui_edit_overfires.append({
                        "index": idx,
                        "timestamp": entry.get("timestamp"),
                        "message": msg_preview[:100],
                        "severity": "high",
                    })
            
            # Pattern 3: Agent overuse on ghost-prone queries
            if selected in ["agent", "grounded_code_fastpath"]:
                ghost_prone_indicators = ["solo analiza", "no uses tools", 
                                         "sin herramientas", "explica", 
                                         "razona sobre", "que piensas de"]
                if any(term in msg_preview for term in ghost_prone_indicators):
                    # Check if there were blocked candidates with no-tool preference
                    has_no_tool_guard = any("no_tool" in g or "prefers" in g 
                                           for g in guards)
                    if has_no_tool_guard:
                        pattern_counts["agent_overuse"] += 1
                        agent_overuse.append({
                            "index": idx,
                            "timestamp": entry.get("timestamp"),
                            "message": msg_preview[:100],
                            "severity": "medium",
                        })
            
            # Pattern 4: High-score candidate blocked
            blocked_high = [c for c in candidates if c.get("blocked") 
                          and c.get("score", 0) > 0.7]
            if blocked_high:
                pattern_counts["high_score_blocked"] += 1
                high_score_blockeds.append({
                    "index": idx,
                    "timestamp": entry.get("timestamp"),
                    "blocked_candidates": [c["name"] for c in blocked_high],
                    "selected": selected,
                    "severity": "medium",
                })
            
            # Pattern 5: Repeated fastpath activation (potential overfire)
            if "fastpath" in selected:
                repeated_fastpaths[selected].append({
                    "index": idx,
                    "message": msg_preview[:80],
                    "timestamp": entry.get("timestamp"),
                })
        
        # Detect repeated fastpath patterns
        for route, activations in repeated_fastpaths.items():
            if len(activations) >= 5:  # Same fastpath 5+ times in window
                # Check if messages are semantically diverse
                messages = [a["message"] for a in activations]
                unique_keywords = set()
                for msg in messages:
                    unique_keywords.update(msg.split()[:5])  # First 5 words
                
                diversity_score = len(unique_keywords) / max(len(messages), 1)
                if diversity_score > 0.5:  # Diverse queries, potential overfire
                    pattern_counts["repeated_fastpath_semantic_drift"] += 1
                    patterns.append({
                        "pattern": "repeated_fastpath_semantic_drift",
                        "route": route,
                        "count": len(activations),
                        "severity": "low" if len(activations) < 10 else "medium",
                        "examples": activations[-3:],  # Last 3 examples
                        "recommendation": f"Review {route} keywords - may be too broad",
                    })
        
        # Build detailed pattern reports
        if trading_hijacks:
            patterns.append({
                "pattern": "trading_hijack",
                "count": len(trading_hijacks),
                "severity": "high",
                "description": "Trading fastpath capturing routing/conversational queries",
                "affected_route": "trading_analysis",
                "recent_examples": trading_hijacks[-3:],
                "recommended_action": "Review _ROUTING_DEBUG_TERMS guard - add more exclusion keywords",
            })
        
        if ui_edit_overfires:
            patterns.append({
                "pattern": "ui_edit_overfire",
                "count": len(ui_edit_overfires),
                "severity": "high",
                "description": "UI edit fastpath activating on analysis requests",
                "affected_route": "grounded_ui_edit_fastpath",
                "recent_examples": ui_edit_overfires[-3:],
                "recommended_action": "Strengthen _blocks_grounded_ui_edit_fastpath with more analysis markers",
            })
        
        if agent_overuse:
            patterns.append({
                "pattern": "agent_overuse_ghost_prone",
                "count": len(agent_overuse),
                "severity": "medium",
                "description": "Agent routed to queries prone to ghost_completion",
                "affected_route": "agent",
                "recent_examples": agent_overuse[-3:],
                "recommended_action": "Ensure _prefers_no_tool_analysis is checked before agent routing",
            })
        
        if high_score_blockeds:
            patterns.append({
                "pattern": "high_score_blocked",
                "count": len(high_score_blockeds),
                "severity": "medium",
                "description": "High-scoring candidates were blocked by negative guards",
                "affected_route": "various",
                "recent_examples": high_score_blockeds[-3:],
                "recommended_action": "Review guard logic - may be overly restrictive",
            })
        
        # Calculate summary statistics
        total_patterns = sum(pattern_counts.values())
        pattern_rate = (total_patterns / total_analyzed * 100) if total_analyzed > 0 else 0
        
        return {
            "status": "ok",
            "window_size": total_analyzed,
            "analysis_timestamp": _time.strftime("%Y-%m-%dT%H:%M:%S"),
            "summary": {
                "total_decisions_analyzed": total_analyzed,
                "total_patterns_detected": total_patterns,
                "pattern_rate_percent": round(pattern_rate, 2),
                "route_distribution": dict(route_distribution),
                "guard_frequency": dict(guard_frequency),
            },
            "patterns": patterns,
            "pattern_breakdown": dict(pattern_counts),
            "requires_attention": len([p for p in patterns if p.get("severity") == "high"]) > 0,
        }
    
    def get_trend_analysis(self, metric: str = "pattern_rate", 
                          intervals: int = 5) -> List[Dict]:
        """F2-OA: Analyze trends over time by splitting routing_log into intervals.
        
        Args:
            metric: Which metric to trend (pattern_rate, route_distribution, etc.)
            intervals: Number of time intervals to analyze
            
        Returns:
            List of trend data points with timestamps and values
        """
        if not self.data.get("routing_log") or len(self.data["routing_log"]) < intervals * 2:
            return [{"error": "Insufficient data for trend analysis"}]
        
        log = self.data["routing_log"]
        interval_size = len(log) // intervals
        
        trends = []
        for i in range(intervals):
            start_idx = i * interval_size
            end_idx = start_idx + interval_size if i < intervals - 1 else len(log)
            interval_log = log[start_idx:end_idx]
            
            # Count patterns in this interval
            pattern_count = 0
            for entry in interval_log:
                selected = entry.get("selected_route", "")
                msg = entry.get("message_preview", "").lower()
                
                # Quick pattern detection
                if selected == "trading_analysis" and any(t in msg for t in 
                    ["brainsession", "/chat", "route="]):
                    pattern_count += 1
                elif selected == "grounded_ui_edit_fastpath" and any(t in msg for t in
                    ["analiza", "no modifiques"]):
                    pattern_count += 1
            
            rate = (pattern_count / len(interval_log) * 100) if interval_log else 0
            
            trends.append({
                "interval": i + 1,
                "start_timestamp": interval_log[0].get("timestamp") if interval_log else None,
                "end_timestamp": interval_log[-1].get("timestamp") if interval_log else None,
                "decisions_count": len(interval_log),
                "pattern_count": pattern_count,
                "pattern_rate_percent": round(rate, 2),
                "trend_direction": "increasing" if i > 0 and rate > trends[-1].get("pattern_rate_percent", 0) else "stable",
            })
        
        return trends

    # ═══════════════════════════════════════════════════════════════════════════
    # FASE 3: ARBITRATION ADVISORY
    # ═══════════════════════════════════════════════════════════════════════════
    def generate_arbitration_advisory(
        self,
        message: str,
        selected_route: str,
        candidates: List[Dict],
        guards_triggered: List[str],
        confidence_scores: Optional[Dict] = None,
    ) -> Optional[Dict]:
        """F3-AA: Generate arbitration advisory WITHOUT changing the actual route.
        
        This provides insights into whether the selected route was optimal,
        suggesting alternatives that were blocked or had lower confidence.
        
        Args:
            message: Original user message
            selected_route: The route that was actually selected
            candidates: All evaluated candidates with scores and block status
            guards_triggered: List of negative guards that fired
            confidence_scores: Optional dict of route -> confidence score
            
        Returns:
            Advisory dict if potential issues detected, None otherwise
        """
        advisory = None
        
        # Check for blocked high-scoring candidates
        blocked_high = [c for c in candidates 
                       if c.get("blocked") and c.get("score", 0) > 0.75]
        
        if blocked_high:
            # Calculate confidence gap
            selected_score = next(
                (c.get("score", 0) for c in candidates if c.get("name") == selected_route), 
                0
            )
            best_blocked_score = max(c.get("score", 0) for c in blocked_high)
            confidence_gap = best_blocked_score - selected_score
            
            if confidence_gap > 0.3:  # Significant gap
                advisory = {
                    "advisory_type": "blocked_superior_candidate",
                    "selected_route": selected_route,
                    "advisory_route": blocked_high[0]["name"],
                    "confidence_gap": round(confidence_gap, 2),
                    "reason": f"Candidate '{blocked_high[0]['name']}' was blocked but had significantly higher score",
                    "guards_triggered": guards_triggered,
                    "recommendation": "Review negative guard logic - may be overly restrictive",
                    "severity": "warning",
                    "would_override": False,  # F3: Never override, just advise
                }
        
        # Check for semantic mismatch (fastpath on excluded domain)
        msg_lower = message.lower()
        if selected_route == "trading_analysis":
            if any(term in msg_lower for term in ["brainsession", "/chat", "router"]):
                advisory = {
                    "advisory_type": "semantic_mismatch",
                    "selected_route": selected_route,
                    "advisory_route": "llm",  # Fallback to LLM
                    "confidence_gap": None,
                    "reason": "Trading fastpath selected for conversational/routing query",
                    "guards_triggered": guards_triggered,
                    "recommendation": "Query appears to be about system routing, not trading",
                    "severity": "warning",
                    "would_override": False,
                }
        
        # Check for agent on no-tool query
        if selected_route == "agent":
            if any(ind in msg_lower for ind in NO_TOOL_MARKERS):
                if "prefers_no_tools" in guards_triggered or not any(
                    c.get("name") == "_has_explicit_tool_target" for c in candidates
                ):
                    advisory = {
                        "advisory_type": "agent_on_no_tool_query",
                        "selected_route": selected_route,
                        "advisory_route": "llm",
                        "confidence_gap": None,
                        "reason": "Agent selected for query with explicit no-tool request",
                        "guards_triggered": guards_triggered,
                        "recommendation": "Consider LLM route for analysis-only queries",
                        "severity": "info",
                        "would_override": False,
                    }
        
        # Log advisory to routing_log if generated
        if advisory:
            self.data.setdefault("advisories", []).append({
                "timestamp": __import__("time").strftime("%Y-%m-%dT%H:%M:%S"),
                "advisory": advisory,
            })
            # Keep only last 50 advisories
            if len(self.data["advisories"]) > 50:
                self.data["advisories"] = self.data["advisories"][-50:]
        
        return advisory

    # ═══════════════════════════════════════════════════════════════════════════
    # FASE 4: SOFT ARBITRATION (Controlled by feature flag)
    # ═══════════════════════════════════════════════════════════════════════════
    
    _SOFT_ARBITRATION_ENABLED = False  # F4: Default OFF - must be explicitly enabled
    
    @classmethod
    def enable_soft_arbitration(cls, enabled: bool = True):
        """F4-SA: Enable/disable soft arbitration globally.
        
        WARNING: Soft arbitration may change routing decisions. Enable only
        after thorough testing and when F2/F3 analytics show clear patterns.
        
        Args:
            enabled: True to enable soft arbitration, False to disable
        """
        cls._SOFT_ARBITRATION_ENABLED = enabled
        import logging
        logging.getLogger("ChatMetrics").warning(
            f"Soft arbitration {'ENABLED' if enabled else 'DISABLED'}"
        )
    
    def apply_soft_arbitration(
        self,
        message: str,
        selected_route: str,
        candidates: List[Dict],
        guards_triggered: List[str],
    ) -> Tuple[str, Optional[Dict]]:
        """F4-SA: Apply soft arbitration ONLY if enabled and safe to do so.
        
        Soft arbitration may override the selected route if:
        1. Soft arbitration is ENABLED (via _SOFT_ARBITRATION_ENABLED)
        2. Original route is marked as overfire pattern
        3. Alternate route has clearly superior score (>0.2 gap)
        4. Alternate route does NOT involve destructive tools
        5. Query has explicit negative guard
        
        Args:
            message: Original user message
            selected_route: Initially selected route
            candidates: All evaluated candidates
            guards_triggered: Negative guards that fired
            
        Returns:
            Tuple of (final_route, arbitration_log)
        """
        arbitration_log = {
            "original_route": selected_route,
            "soft_arbitration_enabled": self._SOFT_ARBITRATION_ENABLED,
            "override_applied": False,
            "reason": None,
        }
        
        # F4: If soft arbitration is disabled, always use selected route
        if not self._SOFT_ARBITRATION_ENABLED:
            arbitration_log["reason"] = "Soft arbitration disabled by default"
            return selected_route, arbitration_log
        
        # Check if we should consider override
        msg_lower = message.lower()
        
        # Condition 1: Check for overfire pattern
        is_overfire = False
        overfire_type = None
        
        if selected_route == "trading_analysis" and any(t in msg_lower for t in 
            ["brainsession", "/chat", "router", "routing"]):
            is_overfire = True
            overfire_type = "trading_hijack"
        elif selected_route == "grounded_ui_edit_fastpath" and any(t in msg_lower for t in
            ["analiza", "no modifiques", "sin herramientas"]):
            is_overfire = True
            overfire_type = "ui_edit_overfire"
        
        if not is_overfire:
            arbitration_log["reason"] = "No overfire pattern detected"
            return selected_route, arbitration_log
        
        # Condition 2: Find best alternate candidate
        blocked_high = [c for c in candidates if c.get("blocked")]
        if not blocked_high:
            arbitration_log["reason"] = "No blocked candidates to consider"
            return selected_route, arbitration_log
        
        best_blocked = max(blocked_high, key=lambda c: c.get("score", 0))
        selected_score = next(
            (c.get("score", 0) for c in candidates if c.get("name") == selected_route),
            0.5
        )
        
        # Condition 3: Score gap must be significant (>0.2)
        score_gap = best_blocked.get("score", 0) - selected_score
        if score_gap < 0.2:
            arbitration_log["reason"] = f"Score gap too small ({score_gap:.2f} < 0.2)"
            return selected_route, arbitration_log
        
        # Condition 4: Check alternate route is safe (no destructive tools)
        alternate_route = best_blocked["name"]
        destructive_routes = ["grounded_ui_edit_fastpath"]  # Routes that modify files
        
        if alternate_route in destructive_routes:
            arbitration_log["reason"] = f"Alternate route '{alternate_route}' involves destructive operations"
            return selected_route, arbitration_log
        
        # Condition 5: Must have explicit negative guard
        if not guards_triggered:
            arbitration_log["reason"] = "No negative guards triggered"
            return selected_route, arbitration_log
        
        # All conditions met - apply override
        final_route = alternate_route
        arbitration_log.update({
            "override_applied": True,
            "original_route": selected_route,
            "final_route": final_route,
            "overfire_type": overfire_type,
            "score_gap": round(score_gap, 2),
            "guards_triggered": guards_triggered,
            "reason": f"Overfire pattern '{overfire_type}' detected with superior alternate route",
        })
        
        return final_route, arbitration_log

    # ═══════════════════════════════════════════════════════════════════════════
    # SEMANTIC COHERENCE VALIDATION LAYER
    # ═══════════════════════════════════════════════════════════════════════════
    
    def validate_semantic_coherence(
        self,
        user_message: str,
        selected_route: str,
        response_content: Optional[str] = None,
        tools_used: Optional[List[str]] = None,
    ) -> Dict:
        """SCVL: Validate semantic coherence between user intent and system response.
        
        Detects contradictions between:
        - User constraints vs Route selected
        - User constraints vs Tools used
        - User constraints vs Response content
        - Grounded claims vs Evidence
        
        Args:
            user_message: Original user message
            selected_route: Route selected by router
            response_content: Final response text (if available)
            tools_used: List of tools that were executed
            
        Returns:
            Coherence validation report with score and contradictions
        """
        msg_lower = (user_message or "").lower()
        contradictions = []
        warnings = []
        coherence_score = 1.0
        
        # ── Detection 1: Domain Contradiction ─────────────────────────────────
        # User explicitly excludes a domain but route goes there
        domain_exclusions = {
            "trading": ["trading_analysis", "trading", "trade", "pipeline"],
            "memory": ["memory", "memoria", "recuerda"],
            "tools": ["agent", "tool", "herramienta"],
            "files": ["ui_edit", "edit", "modificar", "archivo"],
        }
        
        for domain, keywords in domain_exclusions.items():
            # Check if user excluded this domain
            exclusion_patterns = [
                f"no {domain}", f"no analices {domain}",
                f"sin {domain}", f"excluye {domain}",
                f"no uses {domain}", f"no hables de {domain}",
            ]
            if any(pattern in msg_lower for pattern in exclusion_patterns):
                # Check if route matches excluded domain
                if any(kw in selected_route.lower() for kw in keywords):
                    contradictions.append({
                        "type": "domain_contradiction",
                        "severity": "high",
                        "description": f"User excluded '{domain}' but route '{selected_route}' was selected",
                        "user_constraint": f"exclude_{domain}",
                        "route_selected": selected_route,
                    })
                    coherence_score -= 0.3
        
        # ── Detection 2: Tool Usage Contradiction ──────────────────────────────
        # User says "no tools" but tools were used
        if any(ind in msg_lower for ind in NO_TOOL_MARKERS):
            if tools_used and len(tools_used) > 0:
                contradictions.append({
                    "type": "tool_contradiction",
                    "severity": "high",
                    "description": "User requested no tools but tools were executed",
                    "tools_executed": tools_used,
                    "user_constraint": "no_tools",
                })
                coherence_score -= 0.4
            elif selected_route in ["agent", "grounded_code_fastpath", "grounded_ui_edit_fastpath"]:
                # These routes typically use tools
                contradictions.append({
                    "type": "tool_route_contradiction",
                    "severity": "medium",
                    "description": f"User requested no tools but '{selected_route}' was selected",
                    "user_constraint": "no_tools",
                    "route_selected": selected_route,
                })
                coherence_score -= 0.25
        
        # ── Detection 3: Action Contradiction ────────────────────────────────
        # User says "don't modify" but modification occurred
        no_action_indicators = {
            "modificar": ["edit", "modif", "cambio", "update"],
            "crear": ["create", "crea", "nuevo", "new"],
            "eliminar": ["delete", "elimin", "borrar"],
        }
        
        for action, indicators in no_action_indicators.items():
            if f"no {action}" in msg_lower or f"sin {action}" in msg_lower:
                # Check response for signs of action
                if response_content:
                    resp_lower = response_content.lower()
                    if any(ind in resp_lower for ind in indicators):
                        contradictions.append({
                            "type": "action_contradiction",
                            "severity": "high",
                            "description": f"User requested no '{action}' but response indicates it was done",
                            "user_constraint": f"no_{action}",
                            "evidence_in_response": [ind for ind in indicators if ind in resp_lower][:3],
                        })
                        coherence_score -= 0.35
        
        # ── Detection 4: Memory Contradiction ────────────────────────────────
        # User asks for inference but gets MEMORY intent
        inference_indicators = [
            "puedes inferir", "infer", "deduce", "deducir",
            "que opinas", "what do you think", "analiza",
        ]
        
        if any(ind in msg_lower for ind in inference_indicators):
            if selected_route == "MEMORY" or "memory" in selected_route.lower():
                contradictions.append({
                    "type": "memory_contradiction",
                    "severity": "low",
                    "description": "User requested inference/analysis but MEMORY route was selected",
                    "user_intent": "inference",
                    "route_selected": selected_route,
                })
                coherence_score -= 0.15
        
        # ── Detection 5: Grounded Claim Verification ───────────────────────
        # Check for claims without evidence
        if response_content:
            grounded_claim_patterns = [
                r"según el análisis", r"el código muestra",
                r"los datos indican", r"la evidencia",
                r"he verificado", r"el archivo contiene",
            ]
            
            for pattern in grounded_claim_patterns:
                if re.search(pattern, response_content.lower()):
                    # Check if there's actual evidence (tools used, files read)
                    has_evidence = tools_used and len(tools_used) > 0
                    if not has_evidence:
                        warnings.append({
                            "type": "unverified_grounded_claim",
                            "severity": "medium",
                            "description": "Response makes grounded claim but no tools were executed for verification",
                            "claim_pattern": pattern,
                            "recommendation": "Verify claims with tools or remove grounded language",
                        })
                        coherence_score -= 0.2
        
        # ── Detection 6: Semantic Mismatch ─────────────────────────────────────
        # Response doesn't match the topic of the query
        if response_content:
            # Simple heuristic: check if key terms from query appear in response
            query_terms = set(re.findall(r'\b\w{4,}\b', msg_lower))
            response_terms = set(re.findall(r'\b\w{4,}\b', response_content.lower()))
            
            if len(query_terms) > 0:
                overlap = len(query_terms & response_terms) / len(query_terms)
                if overlap < 0.1:  # Less than 10% term overlap
                    warnings.append({
                        "type": "semantic_mismatch",
                        "severity": "low",
                        "description": "Response may not address the user's query topic",
                        "term_overlap_percent": round(overlap * 100, 1),
                        "recommendation": "Verify response addresses user's specific question",
                    })
                    coherence_score -= 0.1
        
        # Calculate final score
        coherence_score = max(0.0, coherence_score)
        
        # Determine overall severity
        severities = [c["severity"] for c in contradictions]
        overall_severity = "high" if "high" in severities else ("medium" if "medium" in severities else "low")
        
        # Generate recommended action
        recommended_action = self._generate_coherence_recommendation(
            contradictions, warnings, coherence_score
        )
        
        return {
            "coherence_score": round(coherence_score, 2),
            "coherence_level": "high" if coherence_score >= 0.8 else ("medium" if coherence_score >= 0.5 else "low"),
            "contradictions_detected": len(contradictions),
            "warnings_detected": len(warnings),
            "contradictions": contradictions,
            "warnings": warnings,
            "overall_severity": overall_severity,
            "recommended_action": recommended_action,
            "validation_timestamp": __import__("time").strftime("%Y-%m-%dT%H:%M:%S"),
        }
    
    def _generate_coherence_recommendation(
        self,
        contradictions: List[Dict],
        warnings: List[Dict],
        coherence_score: float,
    ) -> str:
        """Generate recommendation based on coherence issues."""
        if coherence_score >= 0.8:
            return "No action needed - high coherence"
        
        high_severity = [c for c in contradictions if c["severity"] == "high"]
        
        if high_severity:
            types = [c["type"] for c in high_severity]
            if "tool_contradiction" in types:
                return "CRITICAL: User requested no tools but tools were used. Review _should_use_agent logic."
            elif "domain_contradiction" in types:
                return "HIGH: Route contradicts explicit user exclusion. Consider LLM route instead."
            elif "action_contradiction" in types:
                return "HIGH: Response indicates action user explicitly forbade. Review fastpath guards."
        
        if contradictions:
            return "MEDIUM: Review routing logic - user constraints may not be fully respected"
        
        if warnings:
            return "LOW: Minor coherence issues - consider adding verification for grounded claims"
        
        return "Review recommended"
    
    def record_coherence_validation(
        self,
        session_id: str,
        user_message: str,
        selected_route: str,
        coherence_report: Dict,
    ):
        """Record coherence validation to metrics and routing_log."""
        # Add to routing_log if exists
        if self.data.get("routing_log"):
            # Find the most recent entry for this session/route
            for entry in reversed(self.data["routing_log"]):
                if entry.get("message_preview", "").lower() in user_message.lower():
                    entry["coherence_validation"] = coherence_report
                    break
        
        # Track coherence metrics
        if "coherence_validations" not in self.data:
            self.data["coherence_validations"] = []
        
        self.data["coherence_validations"].append({
            "timestamp": __import__("time").strftime("%Y-%m-%dT%H:%M:%S"),
            "session_id": session_id,
            "route": selected_route,
            "coherence_score": coherence_report.get("coherence_score"),
            "contradictions": coherence_report.get("contradictions_detected", 0),
            "severity": coherence_report.get("overall_severity"),
        })
        
        # Keep only last 100
        if len(self.data["coherence_validations"]) > 100:
            self.data["coherence_validations"] = self.data["coherence_validations"][-100:]
        
        # Increment appropriate counters
        if coherence_report.get("contradictions_detected", 0) > 0:
            self.data["validators"]["coherence_contradiction"] = (
                self.data["validators"].get("coherence_contradiction", 0) + 1
            )
    
    def get_coherence_analytics(self, window_size: int = 100) -> Dict:
        """Get analytics on coherence validation over time."""
        if not self.data.get("coherence_validations"):
            return {
                "status": "no_data",
                "message": "No coherence validations recorded yet",
            }
        
        recent = self.data["coherence_validations"][-window_size:]
        
        scores = [v["coherence_score"] for v in recent if v.get("coherence_score") is not None]
        avg_score = sum(scores) / len(scores) if scores else 0
        
        contradiction_counts = [v["contradictions"] for v in recent]
        total_contradictions = sum(contradiction_counts)
        
        severity_counts = {}
        for v in recent:
            sev = v.get("severity", "unknown")
            severity_counts[sev] = severity_counts.get(sev, 0) + 1
        
        return {
            "status": "ok",
            "window_size": len(recent),
            "avg_coherence_score": round(avg_score, 2),
            "total_contradictions": total_contradictions,
            "contradiction_rate": round(total_contradictions / len(recent) * 100, 2) if recent else 0,
            "severity_distribution": severity_counts,
            "coherence_level_distribution": {
                "high": len([v for v in recent if v.get("coherence_score", 0) >= 0.8]),
                "medium": len([v for v in recent if 0.5 <= v.get("coherence_score", 0) < 0.8]),
                "low": len([v for v in recent if v.get("coherence_score", 0) < 0.5]),
            },
            "requires_attention": total_contradictions > 0 or avg_score < 0.7,
        }

    # ═══════════════════════════════════════════════════════════════════════════
    # CONTRADICTION LEARNING LAYER (CLL)
    # Statistical learning from contradictions to improve routing quality
    # ═══════════════════════════════════════════════════════════════════════════
    
    def record_routing_outcome(
        self,
        route: str,
        success: bool,
        contradiction_detected: bool,
        coherence_score: float,
        guards_triggered: List[str],
        false_positive: bool = False,
    ):
        """CLL: Record routing outcome for learning.
        
        This builds statistical models of route reliability and guard effectiveness.
        
        Args:
            route: The route that was selected
            success: Whether the routing was successful
            contradiction_detected: Whether a contradiction was detected
            coherence_score: Semantic coherence score (0.0-1.0)
            guards_triggered: List of negative guards that fired
            false_positive: Whether this was a false positive block
        """
        timestamp = __import__("time").strftime("%Y-%m-%dT%H:%M:%S")
        
        # Initialize learning data structures if needed
        if "route_reliability" not in self.data:
            self.data["route_reliability"] = {}
        if "guard_effectiveness" not in self.data:
            self.data["guard_effectiveness"] = {}
        if "contradiction_learning" not in self.data:
            self.data["contradiction_learning"] = []
        
        # Record outcome for learning
        self.data["contradiction_learning"].append({
            "timestamp": timestamp,
            "route": route,
            "success": success,
            "contradiction_detected": contradiction_detected,
            "coherence_score": coherence_score,
            "guards_triggered": guards_triggered,
            "false_positive": false_positive,
        })
        
        # Keep only last 500 for learning
        if len(self.data["contradiction_learning"]) > 500:
            self.data["contradiction_learning"] = self.data["contradiction_learning"][-500:]
        
        # Update route reliability stats
        if route not in self.data["route_reliability"]:
            self.data["route_reliability"][route] = {
                "total_uses": 0,
                "successes": 0,
                "contradictions": 0,
                "coherence_scores": [],
            }
        
        self.data["route_reliability"][route]["total_uses"] += 1
        if success:
            self.data["route_reliability"][route]["successes"] += 1
        if contradiction_detected:
            self.data["route_reliability"][route]["contradictions"] += 1
        self.data["route_reliability"][route]["coherence_scores"].append(coherence_score)
        
        # Keep only last 100 coherence scores per route
        if len(self.data["route_reliability"][route]["coherence_scores"]) > 100:
            self.data["route_reliability"][route]["coherence_scores"] = \
                self.data["route_reliability"][route]["coherence_scores"][-100:]
        
        # Update guard effectiveness stats
        for guard in guards_triggered:
            if guard not in self.data["guard_effectiveness"]:
                self.data["guard_effectiveness"][guard] = {
                    "total_triggers": 0,
                    "prevented_contradictions": 0,
                    "false_positives": 0,
                    "block_rate": 0.0,
                    "effectiveness": 0.0,
                }
            
            self.data["guard_effectiveness"][guard]["total_triggers"] += 1
            if contradiction_detected:
                self.data["guard_effectiveness"][guard]["prevented_contradictions"] += 1
            if false_positive:
                self.data["guard_effectiveness"][guard]["false_positives"] += 1
    
    def get_route_reliability_scores(self) -> Dict[str, Dict]:
        """CLL: Calculate reliability scores for each route.
        
        Returns:
            Dict mapping route names to reliability metrics
        """
        if not self.data.get("route_reliability"):
            return {}
        
        scores = {}
        for route, stats in self.data["route_reliability"].items():
            total = stats["total_uses"]
            if total == 0:
                continue
            
            success_rate = stats["successes"] / total
            contradiction_rate = stats["contradictions"] / total
            coherence_scores = stats.get("coherence_scores", [])
            avg_coherence = sum(coherence_scores) / len(coherence_scores) if coherence_scores else 0
            
            # Reliability score: combination of success rate and coherence
            reliability = (success_rate * 0.6) + (avg_coherence * 0.4)
            
            # Risk score: higher contradictions = higher risk
            risk_score = contradiction_rate * (2 - reliability)
            
            scores[route] = {
                "route": route,
                "total_uses": total,
                "success_rate": round(success_rate, 2),
                "contradiction_rate": round(contradiction_rate * 100, 2),  # percent
                "avg_coherence": round(avg_coherence, 2),
                "reliability_score": round(reliability, 2),
                "risk_score": round(risk_score, 2),
                "recommendation": self._generate_route_recommendation(
                    route, reliability, contradiction_rate, total
                ),
            }
        
        return scores
    
    def get_guard_effectiveness_scores(self) -> Dict[str, Dict]:
        """CLL: Calculate effectiveness scores for each guard.
        
        Returns:
            Dict mapping guard names to effectiveness metrics
        """
        if not self.data.get("guard_effectiveness"):
            return {}
        
        scores = {}
        for guard, stats in self.data["guard_effectiveness"].items():
            total = stats["total_triggers"]
            if total == 0:
                continue
            
            prevented = stats.get("prevented_contradictions", 0)
            false_pos = stats.get("false_positives", 0)
            
            # Effectiveness: ratio of prevented contradictions to total triggers
            effectiveness = prevented / total if total > 0 else 0
            
            # False positive rate
            fp_rate = false_pos / total if total > 0 else 0
            
            # Block rate: how often this guard triggers
            block_rate = total / sum(s["total_triggers"] for s in self.data["guard_effectiveness"].values()) \
                if self.data["guard_effectiveness"] else 0
            
            scores[guard] = {
                "guard": guard,
                "total_triggers": total,
                "prevented_contradictions": prevented,
                "false_positives": false_pos,
                "effectiveness": round(effectiveness, 2),
                "false_positive_rate": round(fp_rate * 100, 2),  # percent
                "block_rate": round(block_rate * 100, 2),  # percent
                "recommendation": self._generate_guard_recommendation(
                    guard, effectiveness, fp_rate
                ),
            }
        
        return scores
    
    def _generate_route_recommendation(
        self, route: str, reliability: float, contradiction_rate: float, total_uses: int
    ) -> str:
        """Generate recommendation based on route reliability."""
        if total_uses < 10:
            return "Insufficient data - monitor usage"
        
        if reliability >= 0.8 and contradiction_rate < 0.1:
            return "Route is reliable - no changes needed"
        elif reliability >= 0.6:
            return "Route is moderately reliable - consider refinement"
        elif reliability >= 0.4:
            return "Route has issues - review and strengthen guards"
        else:
            return "Route is unreliable - consider deprecation or major revision"
    
    def _generate_guard_recommendation(
        self, guard: str, effectiveness: float, fp_rate: float
    ) -> str:
        """Generate recommendation based on guard effectiveness."""
        if effectiveness > 0.8 and fp_rate < 0.1:
            return "Guard is highly effective - keep as is"
        elif effectiveness > 0.6:
            return "Guard is effective - monitor for false positives"
        elif fp_rate > 0.3:
            return "Guard has high false positive rate - consider refinement"
        else:
            return "Guard effectiveness is low - review logic"
    
    def get_false_positive_analytics(self, window_size: int = 100) -> Dict:
        """CLL: Analyze false positive patterns.
        
        Returns:
            Analytics on false positives and patterns
        """
        learning_data = self.data.get("contradiction_learning", [])
        if not learning_data:
            return {"status": "no_data", "message": "No learning data yet"}
        
        recent = learning_data[-window_size:]
        
        # Calculate false positive rate
        total = len(recent)
        false_positives = sum(1 for r in recent if r.get("false_positive"))
        fp_rate = (false_positives / total * 100) if total > 0 else 0
        
        # Find routes with highest FP rate
        route_fp = {}
        for r in recent:
            route = r.get("route", "unknown")
            if route not in route_fp:
                route_fp[route] = {"total": 0, "fp": 0}
            route_fp[route]["total"] += 1
            if r.get("false_positive"):
                route_fp[route]["fp"] += 1
        
        route_fp_rates = {
            route: {"fp_rate": round((data["fp"] / data["total"] * 100), 2), "count": data["total"]}
            for route, data in route_fp.items()
            if data["total"] >= 5  # Only routes with sufficient data
        }
        
        # Sort by FP rate
        problematic_routes = sorted(
            route_fp_rates.items(),
            key=lambda x: x[1]["fp_rate"],
            reverse=True
        )[:5]  # Top 5
        
        return {
            "status": "ok",
            "window_size": total,
            "false_positive_rate": round(fp_rate, 2),
            "total_false_positives": false_positives,
            "problematic_routes": [
                {"route": route, "fp_rate": data["fp_rate"], "count": data["count"]}
                for route, data in problematic_routes
            ],
            "recommendation": "Review routes with >30% FP rate" if fp_rate > 10 else "Continue monitoring",
        }
    
    def get_semantic_drift_indicators(self, window_size: int = 100) -> Dict:
        """CLL: Detect semantic drift in routing patterns.
        
        Semantic drift occurs when routes are applied to increasingly diverse
        or inappropriate queries over time.
        
        Returns:
            Indicators of semantic drift per route
        """
        routing_log = self.data.get("routing_log", [])
        if len(routing_log) < window_size:
            return {"status": "insufficient_data", "message": f"Need {window_size} entries, have {len(routing_log)}"}
        
        recent = routing_log[-window_size:]
        
        # Group by route
        route_messages = {}
        for entry in recent:
            route = entry.get("selected_route", "unknown")
            msg = entry.get("message_preview", "")
            if route not in route_messages:
                route_messages[route] = []
            route_messages[route].append(msg.lower())
        
        drift_indicators = {}
        for route, messages in route_messages.items():
            if len(messages) < 5:  # Need minimum data
                continue
            
            # Calculate semantic diversity
            all_words = set()
            message_word_sets = []
            for msg in messages:
                words = set(re.findall(r'\b\w{4,}\b', msg))
                all_words.update(words)
                message_word_sets.append(words)
            
            # Jaccard diversity: low overlap = high diversity
            total_pairs = 0
            total_jaccard = 0
            for i in range(len(message_word_sets)):
                for j in range(i + 1, len(message_word_sets)):
                    intersection = len(message_word_sets[i] & message_word_sets[j])
                    union = len(message_word_sets[i] | message_word_sets[j])
                    if union > 0:
                        total_jaccard += intersection / union
                    total_pairs += 1
            
            avg_similarity = total_jaccard / total_pairs if total_pairs > 0 else 1
            diversity_score = 1 - avg_similarity
            
            # Drift detection
            drift_detected = diversity_score > 0.6 and len(messages) > 10
            
            drift_indicators[route] = {
                "route": route,
                "messages_analyzed": len(messages),
                "diversity_score": round(diversity_score, 2),
                "avg_similarity": round(avg_similarity, 2),
                "drift_detected": drift_detected,
                "drift_level": "high" if diversity_score > 0.7 else ("medium" if diversity_score > 0.5 else "low"),
                "recommendation": "Route keywords may be too broad" if drift_detected else "No drift detected",
            }
        
        # Find routes with highest drift
        high_drift = [r for r in drift_indicators.values() if r["drift_detected"]]
        
        return {
            "status": "ok",
            "window_size": window_size,
            "routes_analyzed": len(drift_indicators),
            "high_drift_detected": len(high_drift),
            "drift_indicators": drift_indicators,
            "problematic_routes": sorted(
                high_drift,
                key=lambda x: x["diversity_score"],
                reverse=True
            )[:3],
        }
    
    def get_contradiction_learning_summary(self) -> Dict:
        """CLL: Generate comprehensive learning summary.
        
        Combines all learning metrics into actionable insights.
        
        Returns:
            Complete learning analytics report
        """
        # Get all component analytics
        route_reliability = self.get_route_reliability_scores()
        guard_effectiveness = self.get_guard_effectiveness_scores()
        fp_analytics = self.get_false_positive_analytics()
        drift_indicators = self.get_semantic_drift_indicators()
        
        # Calculate overall metrics
        learning_data = self.data.get("contradiction_learning", [])
        total_recorded = len(learning_data)
        
        if total_recorded == 0:
            return {
                "status": "no_data",
                "message": "No learning data recorded yet",
            }
        
        contradictions = sum(1 for r in learning_data if r.get("contradiction_detected"))
        false_positives = sum(1 for r in learning_data if r.get("false_positive"))
        
        avg_coherence = sum(r.get("coherence_score", 0) for r in learning_data) / total_recorded
        
        # Overall system health
        system_health = {
            "contradiction_rate": round((contradictions / total_recorded * 100), 2),
            "false_positive_rate": round((false_positives / total_recorded * 100), 2),
            "avg_coherence": round(avg_coherence, 2),
            "routes_learned": len(route_reliability),
            "guards_learned": len(guard_effectiveness),
        }
        
        # Risk assessment
        high_risk_routes = [r for r in route_reliability.values() if r.get("risk_score", 0) > 0.5]
        ineffective_guards = [g for g in guard_effectiveness.values() if g.get("effectiveness", 0) < 0.5]
        
        risk_assessment = {
            "level": "high" if len(high_risk_routes) > 2 else ("medium" if len(high_risk_routes) > 0 else "low"),
            "high_risk_routes": len(high_risk_routes),
            "ineffective_guards": len(ineffective_guards),
            "recommendations": [],
        }
        
        if high_risk_routes:
            risk_assessment["recommendations"].append(
                f"Review {len(high_risk_routes)} high-risk routes"
            )
        if ineffective_guards:
            risk_assessment["recommendations"].append(
                f"Refine {len(ineffective_guards)} ineffective guards"
            )
        
        return {
            "status": "ok",
            "total_recorded": total_recorded,
            "system_health": system_health,
            "route_reliability": route_reliability,
            "guard_effectiveness": guard_effectiveness,
            "false_positive_analytics": fp_analytics if fp_analytics.get("status") == "ok" else None,
            "semantic_drift": drift_indicators if drift_indicators.get("status") == "ok" else None,
            "risk_assessment": risk_assessment,
        }

# R5.1: Process-wide singleton so per-session ChatMetrics instances do not
# load/persist 1755 over and over. Previously each new session_id created its
# own ChatMetrics that loaded from disk but only persisted every 5 messages
# *within that session* — sessions of 1 msg never persisted.
_GLOBAL_CHAT_METRICS: Optional["ChatMetrics"] = None
_GLOBAL_CHAT_METRICS_LOCK = _threading.Lock()


def get_chat_metrics() -> "ChatMetrics":
    """Return the process-wide ChatMetrics singleton (creates on first call)."""
    global _GLOBAL_CHAT_METRICS
    if _GLOBAL_CHAT_METRICS is None:
        with _GLOBAL_CHAT_METRICS_LOCK:
            if _GLOBAL_CHAT_METRICS is None:
                _GLOBAL_CHAT_METRICS = ChatMetrics()
    return _GLOBAL_CHAT_METRICS
