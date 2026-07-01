from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from tmp_agent.brain_v9.config import BASE_PATH

ROOT = BASE_PATH

QUEUE_DIR = ROOT / "memory" / "promotion_queue"
STAGING_DIR = ROOT / "memory" / "semantic_staging"
STAGING_JSONL = STAGING_DIR / "semantic_memory_candidate.jsonl"
SEMANTIC_JSONL = ROOT / "memory" / "semantic" / "semantic_memory.jsonl"

ALLOWED_TERMINAL_STATUSES: Set[str] = {
    "approved_for_canonical_promotion",
    "promoted_to_canonical",
    "archived_duplicate",
    "archived_superseded",
    "pending_review",
    "rejected",
    "staging_only",
}

# High-confidence keyword-based domain mapping for unknown-domain candidates.
DOMAIN_KEYWORD_MAP = {
    "autonomy_dashboard_visual_trace_self_improvement_governance": [
        "autonomy", "dashboard", "visual", "trace", "self-improvement", "governance",
        "scheduler", "self-diagnosis", "fallback", "timeout", "operator ux", "status reliability",
    ],
    "brain_architecture": [
        "brain", "architecture", "debugging", "local ai", "coding", "developer", "intent router",
        "generalization", "router", "runtime", "native runtime",
    ],
    "semantic_memory": [
        "memory", "faiss", "retrieval", "semantic", "promotion quality", "promotion queue", "snapshot",
        "rollback", "jsonl", "embedding", "index",
    ],
    "learning_external": [
        "external source", "github", "repo", "official sources", "learning pipeline", "documentation",
        "api", "sdk",
    ],
    "governance": [
        "governance", "audit", "approval", "operator readiness", "safety", "evidence", "discipline",
        "rollback/snapshot",
    ],
    "production_operations": [
        "production", "operations", "deployment", "runtime operations", "trucking", "dispatcher",
        "business operations", "field inspection", "cei", "fdot", "finance", "risk management",
        "flatbed",
    ],
    "operator_readiness": [
        "operator", "ux", "clarity", "career", "professional communication", "english", "readiness",
    ],
    "tools_capabilities": [
        "tool", "capability", "file patch", "git commit", "smoke test", "promotion candidate", "gateway",
    ],
}

KNOWN_DOMAINS = set(DOMAIN_KEYWORD_MAP.keys()) | {
    "runtime_operations",
    "general",
}


class PromotionPipelineAdapter:
    """
    Read-only compatibility adapter between historical promotion pipeline and
    current Agent V2 semantic memory (FAISS + MemoryGatewayV2).

    This adapter never writes to canonical semantic memory or FAISS.
    """

    def load_candidates(
        self,
        source: str = "all",
        queue_dir: Optional[Path] = None,
        staging_dir: Optional[Path] = None,
        staging_jsonl: Optional[Path] = None,
    ) -> List[Dict[str, Any]]:
        candidates: List[Dict[str, Any]] = []
        if source in ("promotion_queue", "all"):
            candidates.extend(self._load_queue_candidates(queue_dir=queue_dir))
        if source in ("semantic_staging", "all"):
            candidates.extend(self._load_staging_candidates(staging_dir=staging_dir, staging_jsonl=staging_jsonl))
        return candidates

    def _load_queue_candidates(self, queue_dir: Optional[Path] = None) -> List[Dict[str, Any]]:
        qdir = queue_dir or QUEUE_DIR
        if not qdir.exists():
            return []
        out: List[Dict[str, Any]] = []
        for path in sorted(qdir.glob("*.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(data, list):
                    for item in data:
                        out.append(self.normalize_candidate(item, str(path), "promotion_queue"))
                elif isinstance(data, dict):
                    out.append(self.normalize_candidate(data, str(path), "promotion_queue"))
            except Exception:
                continue
        return out

    def _load_staging_candidates(
        self,
        staging_dir: Optional[Path] = None,
        staging_jsonl: Optional[Path] = None,
    ) -> List[Dict[str, Any]]:
        sdir = staging_dir or STAGING_DIR
        sjsonl = staging_jsonl or STAGING_JSONL
        out: List[Dict[str, Any]] = []
        if sjsonl.exists():
            for line in sjsonl.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                try:
                    item = json.loads(line)
                    out.append(self.normalize_candidate(item, str(sjsonl), "semantic_staging"))
                except Exception:
                    continue
        for path in sorted(sdir.glob("*.json")):
            if path.name == "semantic_memory_candidate.jsonl":
                continue
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(data, list):
                    for item in data:
                        out.append(self.normalize_candidate(item, str(path), "semantic_staging"))
                elif isinstance(data, dict):
                    out.append(self.normalize_candidate(data, str(path), "semantic_staging"))
            except Exception:
                continue
        return out

    def normalize_candidate(
        self,
        candidate: Dict[str, Any],
        source_path: str,
        source_bucket: str,
    ) -> Dict[str, Any]:
        text = str(candidate.get("text") or candidate.get("summary") or "").strip()
        summary = str(candidate.get("summary") or candidate.get("text") or "").strip()
        if len(summary) > 300:
            summary = summary[:300] + "..."
        original_id = str(candidate.get("candidate_id") or candidate.get("event_id") or "").strip()
        candidate_id_generated = False
        record_id = original_id
        if not record_id:
            record_id = self._generate_candidate_id(source_bucket, source_path, text)
            candidate_id_generated = True
        raw = {
            "candidate_id": record_id,
            "original_candidate_id": original_id,
            "candidate_id_generated": candidate_id_generated,
            "candidate_id_generation_method": "sha256_source_path_text" if candidate_id_generated else "source_field",
            "source_path": source_path,
            "source_bucket": source_bucket,
            "text": text,
            "summary": summary,
            "domain": str(candidate.get("domain") or candidate.get("canonical_domain") or "unknown"),
            "canonical_domain": str(candidate.get("canonical_domain") or candidate.get("domain") or "unknown"),
            "category": str(candidate.get("category") or "unknown"),
            "confidence": self._float(candidate.get("confidence")),
            "quality_score": self._float(candidate.get("quality_score")),
            "usefulness_score": self._float(candidate.get("usefulness_score")),
            "safety_score": self._float(candidate.get("safety_score")),
            "terminal_status": str(candidate.get("terminal_status") or "pending_review"),
            "staging_status": str(candidate.get("staging_status") or "unknown"),
            "canonical_promotion": bool(candidate.get("canonical_promotion", False)),
            "review_required": bool(candidate.get("review_required", True)),
            "raw_cot_exposed": bool(candidate.get("raw_cot_exposed", False)),
            "secrets_exposed": bool(candidate.get("secrets_exposed", False)),
            "trading_execution_detected": bool(candidate.get("trading_execution_detected", False)),
            "source_cycle": str(candidate.get("source_cycle") or candidate.get("cycle") or "unknown"),
            "source_metadata": dict(candidate.get("source_metadata") or {}),
            "evidence_path": str(candidate.get("evidence_path") or ""),
            "created_utc": str(candidate.get("created_utc") or ""),
            "hash": self._hash(text, record_id),
        }
        raw["adapter_status"] = "normalized"
        # Apply deterministic domain normalization only if currently unknown.
        domain_info = self._normalize_domain(raw)
        raw["domain"] = domain_info["domain"]
        raw["canonical_domain"] = domain_info["canonical_domain"]
        raw["domain_review_required"] = domain_info["domain_review_required"]
        raw["domain_mapping_confidence"] = domain_info["domain_mapping_confidence"]
        raw["normalization_notes"] = domain_info["normalization_notes"]
        return raw

    def validate_candidate(self, candidate: Dict[str, Any]) -> Dict[str, Any]:
        errors: List[str] = []
        if not candidate.get("candidate_id"):
            errors.append("missing_candidate_id")
        text = str(candidate.get("text") or "").strip()
        if not text:
            errors.append("blank_text")
        if candidate.get("raw_cot_exposed"):
            errors.append("raw_cot_exposed")
        if candidate.get("secrets_exposed"):
            errors.append("secrets_exposed")
        if candidate.get("trading_execution_detected"):
            errors.append("trading_execution_detected")
        terminal = candidate.get("terminal_status")
        if terminal not in ALLOWED_TERMINAL_STATUSES:
            errors.append(f"terminal_status_not_allowed:{terminal}")
        if candidate.get("canonical_promotion") and not candidate.get("review_required"):
            approved = candidate.get("terminal_status") in {"approved_for_canonical_promotion", "promoted_to_canonical"}
            if not approved:
                errors.append("canonical_promotion_without_review")
        if not candidate.get("domain") or candidate.get("domain") == "unknown":
            errors.append("domain_unknown")
        if not candidate.get("source_cycle") or candidate.get("source_cycle") == "unknown":
            errors.append("source_cycle_unknown")
        duplicate = self._is_duplicate_text(text)
        if duplicate:
            errors.append("duplicate_exact_text_in_canonical_memory")
        return {
            "valid": len(errors) == 0,
            "validation_errors": errors,
            "duplicate_exact": duplicate,
            "safety_hash": self._hash(text, candidate.get("candidate_id") or ""),
        }

    def dry_run_promotion(self, candidate_id: str) -> Dict[str, Any]:
        candidates = self.load_candidates("all")
        candidate = next((c for c in candidates if c.get("candidate_id") == candidate_id), None)
        if candidate is None:
            return {
                "ok": False,
                "candidate_valid": False,
                "validation_errors": ["candidate_not_found"],
                "would_write_jsonl": False,
                "would_write_faiss": False,
                "would_create_snapshot": False,
                "would_append_audit": False,
                "would_require_human_approval": True,
                "write_performed": False,
            }
        validation = self.validate_candidate(candidate)
        proposed_record = self._build_proposed_semantic_record(candidate)
        snapshot_path = str(ROOT / "memory" / "rollback_snapshots" / f"dry_run_{candidate_id}")
        rollback_plan = {
            "snapshot_dir": snapshot_path,
            "canonical_files": [
                str(ROOT / "memory" / "semantic" / "semantic_memory.jsonl"),
                str(ROOT / "memory" / "semantic" / "semantic_memory_faiss.index"),
                str(ROOT / "memory" / "semantic" / "semantic_memory_faiss_ids.json"),
            ],
            "restore_method": "copy snapshot files back to memory/semantic",
        }
        return {
            "ok": True,
            "candidate_valid": validation["valid"],
            "validation_errors": validation["validation_errors"],
            "duplicate_exact": validation["duplicate_exact"],
            "normalized_candidate": candidate,
            "proposed_semantic_record": proposed_record,
            "would_write_jsonl": False,
            "would_write_faiss": False,
            "would_create_snapshot": True,
            "would_append_audit": True,
            "would_require_human_approval": True,
            "rollback_plan": rollback_plan,
            "write_performed": False,
        }

    def _build_proposed_semantic_record(self, candidate: Dict[str, Any]) -> Dict[str, Any]:
        text = str(candidate.get("text") or "").strip()
        return {
            "id": candidate.get("candidate_id") or "",
            "created_utc": candidate.get("created_utc") or "",
            "source": candidate.get("source_bucket") or "promotion_pipeline",
            "session_id": "promotion_adapter_dry_run",
            "kind": "canonical_candidate",
            "text": text,
            "metadata": {
                "domain": candidate.get("domain"),
                "canonical_domain": candidate.get("canonical_domain"),
                "category": candidate.get("category"),
                "source_cycle": candidate.get("source_cycle"),
                "evidence_path": candidate.get("evidence_path"),
                "source_metadata": candidate.get("source_metadata"),
                "confidence": candidate.get("confidence"),
                "quality_score": candidate.get("quality_score"),
                "usefulness_score": candidate.get("usefulness_score"),
                "safety_score": candidate.get("safety_score"),
                "terminal_status": candidate.get("terminal_status"),
            },
        }

    def _generate_candidate_id(self, source_bucket: str, source_path: str, text: str) -> str:
        payload = json.dumps({"bucket": source_bucket, "path": source_path, "text": text}, sort_keys=True, ensure_ascii=False)
        return "cand_" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]

    def _normalize_domain(self, candidate: Dict[str, Any]) -> Dict[str, Any]:
        domain = str(candidate.get("domain") or "unknown").lower()
        canonical_domain = str(candidate.get("canonical_domain") or domain).lower()
        if domain in KNOWN_DOMAINS or canonical_domain in KNOWN_DOMAINS:
            return {
                "domain": domain if domain in KNOWN_DOMAINS else canonical_domain,
                "canonical_domain": canonical_domain if canonical_domain in KNOWN_DOMAINS else domain,
                "domain_review_required": False,
                "domain_mapping_confidence": "existing",
                "normalization_notes": "domain already known",
            }

        # Collect evidence text for keyword matching.
        evidence_parts = [
            candidate.get("category", ""),
            candidate.get("source_cycle", ""),
            str(candidate.get("source_metadata") or {}),
            Path(candidate.get("source_path", "")).name,
            candidate.get("text", ""),
            candidate.get("summary", ""),
        ]
        evidence_text = " ".join(str(p).lower() for p in evidence_parts if p)

        scores: Dict[str, int] = {}
        for known_domain, keywords in DOMAIN_KEYWORD_MAP.items():
            score = 0
            for keyword in keywords:
                if keyword.lower() in evidence_text:
                    score += 1
            if score > 0:
                scores[known_domain] = score

        if scores:
            best_domain = max(scores, key=lambda d: scores[d])
            best_score = scores[best_domain]
            # Require at least 2 keyword hits to avoid low-confidence guessing.
            if best_score >= 2:
                return {
                    "domain": best_domain,
                    "canonical_domain": best_domain,
                    "domain_review_required": False,
                    "domain_mapping_confidence": "high",
                    "normalization_notes": f"mapped from keywords (score={best_score})",
                }

        return {
            "domain": domain,
            "canonical_domain": canonical_domain,
            "domain_review_required": True,
            "domain_mapping_confidence": "low",
            "normalization_notes": "no high-confidence domain mapping found",
        }

    def _is_duplicate_text(self, text: str) -> bool:
        if not SEMANTIC_JSONL.exists() or not text:
            return False
        target = text.strip()
        try:
            for line in SEMANTIC_JSONL.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                rec = json.loads(line)
                rec_text = str(rec.get("text") or "").strip()
                if rec_text == target:
                    return True
        except Exception:
            pass
        return False

    def _hash(self, text: str, record_id: str) -> str:
        payload = json.dumps({"text": text, "id": record_id}, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]

    @staticmethod
    def _float(value: Any) -> Optional[float]:
        try:
            return float(value) if value is not None else None
        except (TypeError, ValueError):
            return None


def load_candidates(source: str = "all") -> List[Dict[str, Any]]:
    return PromotionPipelineAdapter().load_candidates(source)


def normalize_candidate(candidate: Dict[str, Any], source_path: str) -> Dict[str, Any]:
    # Determine source_bucket from path heuristic
    bucket = "unknown"
    norm_path = Path(source_path).resolve()
    try:
        if norm_path.is_relative_to(QUEUE_DIR.resolve()):
            bucket = "promotion_queue"
        elif norm_path.is_relative_to(STAGING_DIR.resolve()):
            bucket = "semantic_staging"
    except ValueError:
        pass
    return PromotionPipelineAdapter().normalize_candidate(candidate, source_path, bucket)


def validate_candidate(candidate: Dict[str, Any]) -> Dict[str, Any]:
    return PromotionPipelineAdapter().validate_candidate(candidate)


def dry_run_promotion(candidate_id: str) -> Dict[str, Any]:
    return PromotionPipelineAdapter().dry_run_promotion(candidate_id)
