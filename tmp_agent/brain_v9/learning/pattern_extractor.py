from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from brain_v9.core.state_io import read_json, write_json


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _pattern(pattern_id: str, description: str, relevance: float, risk: float, modules: List[str]) -> Dict[str, Any]:
    return {
        "pattern_id": pattern_id,
        "description": description,
        "relevance_to_brain": relevance,
        "risk": risk,
        "applicable_modules": modules,
        "do_not_copy_code": True,
    }


def _evidence(source_file: str, reason: str, evidence_type: str = "text_match") -> Dict[str, Any]:
    return {
        "source_file": source_file,
        "reason": reason,
        "evidence_type": evidence_type,
    }


def _with_grounding(pattern: Dict[str, Any], semantic_family: str, evidence_refs: List[Dict[str, Any]]) -> Dict[str, Any]:
    row = dict(pattern)
    row["semantic_family"] = semantic_family
    row["evidence_refs"] = evidence_refs
    return row


def _optional_json(path_value: str | Path | None, default: Any) -> Any:
    if not path_value:
        return default
    return read_json(path_value, default=default) or default


def _deep_matches(snippets: List[Dict[str, Any]], tokens: List[str], *, preferred: List[str] | None = None) -> List[Dict[str, Any]]:
    refs: List[Dict[str, Any]] = []
    preferred = preferred or []
    for item in snippets:
        path_value = str(item.get("path") or "")
        excerpt = str(item.get("excerpt") or "")
        text_l = f"{path_value}\n{excerpt}".lower()
        if not any(token in text_l for token in tokens):
            continue
        reason_tokens = [token for token in tokens if token in text_l][:3]
        evidence_kind = "priority_file_snippet"
        if preferred and not any(pref in path_value.lower() for pref in preferred):
            continue
        refs.append(_evidence(path_value, f"Priority file snippet contains: {', '.join(reason_tokens)}.", evidence_kind))
    return refs[:3]


def extract_patterns(
    source_manifest: Dict[str, Any],
    curation_report: Dict[str, Any],
    repo_metadata_path: Path,
    readme_path: Path,
    output_path: Path,
) -> Dict[str, Any]:
    metadata = read_json(repo_metadata_path, default={}) or {}
    root_index = _optional_json(source_manifest.get("root_index_path"), [])
    priority_snippets = _optional_json(source_manifest.get("priority_file_snippets_path"), [])
    dependency_hints = _optional_json(source_manifest.get("dependency_hints_path"), {})
    readme = readme_path.read_text(encoding="utf-8", errors="replace") if readme_path.exists() else ""
    text = f"{metadata.get('name', '')}\n{metadata.get('description', '')}\n{readme}".lower()
    full_name = (metadata.get("full_name") or "").lower()
    root_names = {str(item.get("name") or "").lower() for item in root_index}
    patterns: List[Dict[str, Any]] = []

    debate_refs = _deep_matches(priority_snippets, ["critic", "judge", "groupchat", "multi-agent", "debate"], preferred=["agent", "chat", "group"])
    if "autogen" in full_name or re.search(r"\bcritic\b|\bjudge\b|\bgroup chat\b|\bmulti-agent\b", text) or debate_refs:
        patterns.append(_with_grounding(
            _pattern(
                "structured_multi_agent_debate",
                "Role-based proposal, critique, defense and judge loop for complex planning.",
                9.0, 4.0, ["planner", "evaluator", "governance"],
            ),
            "multi_agent_debate",
            debate_refs or [_evidence("README.snapshot.md", "README mentions multi-agent/group chat/critic/judge roles.")],
        ))
        tool_role_refs = _deep_matches(priority_snippets, ["tool", "handoff", "router", "delegate"], preferred=["agent", "tool"])
        patterns.append(_with_grounding(
            _pattern(
                "role_orchestrated_tool_routing",
                "Different agent roles own different tools and execution scopes.",
                8.5, 4.0, ["agent", "governance", "tools"],
            ),
            "tool_routing",
            tool_role_refs or [_evidence("README.snapshot.md", "README describes role-oriented orchestration that implies tool ownership.")],
        ))

    graph_refs = _deep_matches(priority_snippets, ["graph", "state", "node", "edge"], preferred=["graph", "state"])
    if "langgraph" in full_name or re.search(r"\bgraph\b|\bstate machine\b|\bcheckpoint\b", text) or graph_refs:
        patterns.append(_with_grounding(
            _pattern(
                "stateful_graph_orchestration",
                "Graph-based orchestration with explicit state transitions and checkpoints.",
                8.8, 3.5, ["planner", "session", "autonomy"],
            ),
            "graph_orchestration",
            graph_refs or [_evidence("README.snapshot.md", "README/description exposes graph-based orchestration language.")],
        ))
        checkpoint_refs = _deep_matches(priority_snippets, ["checkpoint", "resume", "persist", "recovery"], preferred=["checkpoint", "state", "memory"])
        patterns.append(_with_grounding(
            _pattern(
                "failure_recovery_checkpoints",
                "Persist checkpoints so long-horizon tasks can resume after faults.",
                8.1, 3.0, ["autonomy", "governance", "session"],
            ),
            "checkpoint_recovery",
            checkpoint_refs or [_evidence("README.snapshot.md", "README references checkpoints/state persistence for long-running tasks.")],
        ))

    patch_refs = _deep_matches(priority_snippets, ["patch", "diff", "repair", "workspace", "apply"], preferred=["patch", "diff", "workspace"])
    if "openhands" in full_name or re.search(r"\bpatch\b|\bdiff\b|\bcode agent\b|\brepair\b", text) or patch_refs:
        patterns.append(_with_grounding(
            _pattern(
                "sandboxed_patch_planning",
                "Patch planning should happen with explicit diffs, tests and sandbox boundaries.",
                8.9, 5.0, ["self_improvement", "governance", "code"],
            ),
            "patch_planning",
            patch_refs or [_evidence("README.snapshot.md", "README describes coding-agent / patch / diff behavior.")],
        ))
        repair_refs = _deep_matches(priority_snippets, ["test", "repair", "fix", "failing"], preferred=["test", "repair"])
        patterns.append(_with_grounding(
            _pattern(
                "test_first_code_repair",
                "Repair loops that center the patch around reproducible failing tests.",
                8.4, 4.5, ["self_improvement", "tests", "governance"],
            ),
            "test_first_repair",
            repair_refs or [_evidence("README.snapshot.md", "README/repo description emphasizes repair or coding-agent workflows.")],
        ))

    if ".github" in root_names or "tests" in root_names or "pytest.ini" in root_names:
        test_source = "tests/" if "tests" in root_names else ".github/" if ".github" in root_names else "pytest.ini"
        patterns.append(_with_grounding(
            _pattern(
                "ci_backed_regression_harness",
                "The repo exposes CI/test structure that can inspire stronger regression gates.",
                7.4, 2.5, ["evaluator", "governance", "tests"],
            ),
            "regression_harness",
            [_evidence(test_source, "Root index shows tests/CI structure.", "root_index_signal")],
        ))

    if any(name in root_names for name in ("pyproject.toml", "requirements.txt", "package.json")):
        manifest_name = next(name for name in ("pyproject.toml", "requirements.txt", "package.json") if name in root_names)
        patterns.append(_pattern(
            "dependency_manifest_governance",
            "Explicit dependency manifests can be used as inputs for source and patch risk checks.",
            7.1, 3.0, ["governance", "security", "research"],
        ))
        patterns[-1] = _with_grounding(
            patterns[-1],
            "dependency_governance",
            [_evidence(manifest_name, "Root dependency manifest is present and can be audited.", "root_index_signal")],
        )

    dep_text = "\n".join(str(v) for v in dependency_hints.values()).lower()
    tool_refs = _deep_matches(priority_snippets, ["tool", "function call", "tool calling", "invoke"], preferred=["tool", "router", "model"])
    if re.search(r"\btool\b|\btools\b|\bfunction call\b|\btool calling\b", text + "\n" + dep_text) or tool_refs:
        dep_source = next(iter(dependency_hints.keys()), "README.snapshot.md")
        patterns.append(_pattern(
            "structured_tool_dispatch",
            "Tool usage is modeled explicitly enough to inspire safer routing and observation loops.",
            8.0, 3.5, ["agent", "tools", "governance"],
        ))
        patterns[-1] = _with_grounding(
            patterns[-1],
            "tool_routing",
            tool_refs or [_evidence(dep_source, "Dependency hints or README mention tool calling / tool usage explicitly.")],
        )

    if not patterns:
        patterns.append(_with_grounding(
            _pattern(
                "documentation_driven_learning",
                "Source contains reusable concepts but no strong architecture pattern was detected automatically.",
                5.0, 2.0, ["research"],
            ),
            "documentation_learning",
            [_evidence("README.snapshot.md", "Only documentation-level reusable concepts detected.")],
        ))

    deduped: Dict[str, Dict[str, Any]] = {}
    for pattern in patterns:
        deduped.setdefault(pattern["pattern_id"], pattern)

    report = {
        "source_id": source_manifest.get("source_id"),
        "generated_at_utc": _utc_now(),
        "recommended_action": curation_report.get("recommended_action"),
        "patterns": list(deduped.values()),
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    write_json(output_path, report)
    return report
