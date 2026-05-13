"""
Brain V9 — Fase 7.2 ADN Modular / Score de Calidad
Computes per-module quality indicators for the codebase.
Minimal implementation: lines, complexity hint, test coverage flag, overall score.
"""
import logging
from pathlib import Path
from typing import Any, Dict, List

from brain_v9.config import BRAIN_V9_PATH

logger = logging.getLogger("brain_v9.governance.adn_quality")

# ─── Constants ───────────────────────────────────────────────────────────────
BRAIN_V9_SRC = BRAIN_V9_PATH / "brain_v9"
TESTS_ROOT = BRAIN_V9_PATH / "tests"

# Complexity thresholds (naive line-count based)
HIGH_COMPLEXITY_LINES = 500
MEDIUM_COMPLEXITY_LINES = 150

# Quality weight factors
W_HAS_TEST = 0.40
W_COMPLEXITY = 0.30
W_SIZE = 0.30


def _scan_module(py_file: Path) -> Dict[str, Any]:
    """Analyze a single .py module for quality indicators."""
    try:
        content = py_file.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return {"path": str(py_file), "error": "unreadable"}

    lines = content.split("\n")
    line_count = len(lines)

    # Count functions and classes
    func_count = sum(1 for l in lines if l.strip().startswith("def "))
    class_count = sum(1 for l in lines if l.strip().startswith("class "))

    # Naive complexity: high >500, medium >150, low otherwise
    if line_count > HIGH_COMPLEXITY_LINES:
        complexity = "high"
    elif line_count > MEDIUM_COMPLEXITY_LINES:
        complexity = "medium"
    else:
        complexity = "low"

    # Count bare except blocks (code smell)
    bare_except_count = sum(
        1 for l in lines
        if l.strip() == "except:" or l.strip().startswith("except Exception:")
    )

    return {
        "path": str(py_file.relative_to(BRAIN_V9_PATH)),
        "lines": line_count,
        "functions": func_count,
        "classes": class_count,
        "complexity": complexity,
        "bare_excepts": bare_except_count,
    }


def _find_test_file(module_rel: str) -> bool:
    """Check if a test file exists for the given module path."""
    # module_rel like "brain_v9/trading/backtest_gate.py"
    module_name = Path(module_rel).stem  # "backtest_gate"
    # Search tests/ recursively for test_*module_name*.py
    for test_file in TESTS_ROOT.rglob(f"test_*{module_name}*.py"):
        return True
    # Also check root-level test files
    for test_file in TESTS_ROOT.glob(f"test_*{module_name}*.py"):
        return True
    return False


def _compute_score(module: Dict[str, Any], has_test: bool) -> float:
    """Compute quality score 0.0-1.0 for a module."""
    # Test coverage contribution
    test_score = 1.0 if has_test else 0.0

    # Complexity score (lower is better)
    complexity = module.get("complexity", "low")
    if complexity == "low":
        complexity_score = 1.0
    elif complexity == "medium":
        complexity_score = 0.6
    else:
        complexity_score = 0.3

    # Size score (penalize very large files)
    lines = module.get("lines", 0)
    if lines <= 200:
        size_score = 1.0
    elif lines <= 500:
        size_score = 0.7
    elif lines <= 1000:
        size_score = 0.4
    else:
        size_score = 0.2

    return round(
        W_HAS_TEST * test_score + W_COMPLEXITY * complexity_score + W_SIZE * size_score,
        3,
    )


def build_adn_quality_report() -> Dict[str, Any]:
    """
    Scan the brain_v9 codebase and produce a quality report.
    Returns per-module scores and an aggregate.
    """
    modules = []
    total_score = 0.0
    untested_modules = []
    high_complexity_modules = []

    for py_file in sorted(BRAIN_V9_SRC.rglob("*.py")):
        if py_file.name == "__init__.py":
            continue

        info = _scan_module(py_file)
        if "error" in info:
            continue

        has_test = _find_test_file(info["path"])
        score = _compute_score(info, has_test)

        info["has_test"] = has_test
        info["quality_score"] = score
        modules.append(info)
        total_score += score

        if not has_test:
            untested_modules.append(info["path"])
        if info["complexity"] == "high":
            high_complexity_modules.append(info["path"])

    n_modules = len(modules) or 1
    aggregate_score = round(total_score / n_modules, 3)

    # Sort by worst score first (priority for improvement)
    modules.sort(key=lambda m: m["quality_score"])

    return {
        "schema": "adn_quality_v1",
        "total_modules": len(modules),
        "aggregate_quality_score": aggregate_score,
        "untested_count": len(untested_modules),
        "high_complexity_count": len(high_complexity_modules),
        "untested_modules": untested_modules,
        "high_complexity_modules": high_complexity_modules,
        "worst_10": modules[:10],
        "best_10": modules[-10:] if len(modules) >= 10 else modules,
        "all_modules": modules,
    }
