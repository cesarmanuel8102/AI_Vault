"""
P4-15 — QC Pattern Ingester

Reads the QuantConnect pattern library and applies validated patterns
when creating or updating strategy specs.

Responsibilities:
  1. ``load_pattern_library``    – read + validate the pattern library JSON
  2. ``PATTERN_PARAMS``          – mapping from pattern_id → concrete params
  3. ``apply_patterns_to_spec``  – enrich a strategy spec with pattern-derived
                                   parameters (risk, validation, execution)
  4. ``ingest_patterns_for_project`` – given a project_id, return the merged
                                       parameter set from all its patterns
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from brain_v9.config import BASE_PATH
from brain_v9.core.state_io import read_json

logger = logging.getLogger("QCPatternIngester")

# ─── Paths ───────────────────────────────────────────────────────────────────
_PATTERN_LIBRARY_PATH = (
    BASE_PATH / "tmp_agent" / "state" / "rooms"
    / "brain_financial_ingestion_fi07_memory"
    / "quantconnect_pattern_library.json"
)

# ─── Pattern → Concrete Parameter Mapping ────────────────────────────────────
#
# Each key is a pattern_id from the library.  The value is a dict of concrete
# parameter overrides that the brain should apply when a strategy references
# this pattern.
#
# These are *additive* — if a strategy already has a value for a parameter,
# the pattern value is used only when the existing value is empty/default.
#
PATTERN_PARAMS: Dict[str, Dict[str, Any]] = {
    "qc_objectstore_model_contract": {
        # Model registry contract: strategies using this pattern rely on
        # persisted models with a manifest.  The brain should know that
        # model retraining cadence affects signal freshness.
        "model_persistence": True,
        "model_format": "objectstore_manifest",
        "retrain_cadence_days": 30,
        "model_staleness_threshold_days": 45,
    },
    "qc_ibkr_execution_lane": {
        # IBKR execution: explicit risk limits from the QC algo.
        "execution_lane": "ibkr",
        "max_portfolio_leverage": 1.0,
        "max_position_pct": 0.15,
        "min_order_fill_confidence": 0.90,
        "supports_live_signal_resolution": True,
    },
    "qc_options_ml_stack": {
        # Options ML stack: DTE, spread, OI constraints from the QC algo.
        "asset_class_hint": "options",
        "min_dte": 14,
        "max_dte": 45,
        "max_spread_pct": 0.07,
        "min_open_interest": 700,
        "max_portfolio_beta": 1.0,
        "vol_scaling_enabled": True,
    },
    "qc_temporal_validation_and_calibration": {
        # Validation discipline: triple barrier, temporal CV, per-regime thresholds.
        "validation_method": "temporal_cross_validation",
        "labeling_method": "triple_barrier",
        "calibration_enabled": True,
        "per_regime_thresholds": True,
        "min_oos_sharpe": 0.5,
        "min_walk_forward_windows": 3,
    },
}


def load_pattern_library(
    library_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """Read and return the pattern library JSON.

    Returns
    -------
    dict
        The full library payload, or an empty fallback if the file is missing.
    """
    path = Path(library_path or _PATTERN_LIBRARY_PATH)
    return read_json(path, default={
        "schema_version": "quantconnect_pattern_library_v1",
        "reusable_patterns": [],
    })


def get_available_patterns(
    library_path: Optional[Path] = None,
) -> List[Dict[str, Any]]:
    """Return the list of reusable pattern dicts from the library."""
    lib = load_pattern_library(library_path)
    return lib.get("reusable_patterns", [])


def ingest_patterns_for_project(
    project_id: int,
    project_patterns: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Merge all pattern params for a project into a single dict.

    Parameters
    ----------
    project_id : int
        The QC project ID (used for logging).
    project_patterns : list of str, optional
        Pattern IDs associated with this project.  Typically comes from
        ``QC_PROJECTS[project_id]["patterns"]``.

    Returns
    -------
    dict
        Merged parameter dict.  Later patterns override earlier ones on key
        conflicts.
    """
    if not project_patterns:
        return {}

    merged: Dict[str, Any] = {}
    applied_patterns: List[str] = []

    for pid in project_patterns:
        params = PATTERN_PARAMS.get(pid)
        if params:
            merged.update(params)
            applied_patterns.append(pid)
        else:
            logger.debug(
                "Pattern '%s' for project %d has no param mapping — skipped",
                pid, project_id,
            )

    if applied_patterns:
        merged["_applied_patterns"] = applied_patterns

    return merged


def apply_patterns_to_spec(
    spec: Dict[str, Any],
    pattern_ids: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Enrich a strategy spec with pattern-derived parameters.

    The function adds a ``qc_pattern_params`` key to the spec containing all
    merged pattern parameters.  It also updates specific top-level spec fields
    if the pattern provides better values:

    * ``filters.spread_pct_max`` — from ``max_spread_pct``
    * ``execution_profile.supports_live_signal_resolution`` — from pattern
    * ``success_criteria.min_expectancy`` — from ``min_oos_sharpe`` proxy

    Parameters
    ----------
    spec : dict
        A strategy spec dict (from ``backtest_to_strategy_spec`` or existing).
    pattern_ids : list of str, optional
        Pattern IDs to apply.  If None, reads from
        ``spec["qc_metadata"]["patterns"]``.

    Returns
    -------
    dict
        The enriched spec (same object, mutated in-place).
    """
    if pattern_ids is None:
        qc_meta = spec.get("qc_metadata") or {}
        pattern_ids = qc_meta.get("patterns", [])

    if not pattern_ids:
        return spec

    project_id = (spec.get("qc_metadata") or {}).get("project_id", 0)
    merged = ingest_patterns_for_project(project_id, pattern_ids)
    if not merged:
        return spec

    # Store full pattern params on the spec
    spec["qc_pattern_params"] = merged

    # ── Propagate selected params to standard spec fields ────────────────
    filters = spec.setdefault("filters", {})
    exec_profile = spec.setdefault("execution_profile", {})
    success = spec.setdefault("success_criteria", {})

    # Spread filter
    if "max_spread_pct" in merged:
        current = filters.get("spread_pct_max", 999)
        if merged["max_spread_pct"] < current:
            filters["spread_pct_max"] = merged["max_spread_pct"]

    # Execution lane
    if merged.get("supports_live_signal_resolution"):
        exec_profile["supports_live_signal_resolution"] = True

    # Validation discipline
    if merged.get("min_oos_sharpe"):
        current_min = success.get("min_expectancy", 0.0)
        if merged["min_oos_sharpe"] > current_min:
            success["min_expectancy"] = merged["min_oos_sharpe"]

    # Model staleness
    if merged.get("model_staleness_threshold_days"):
        spec.setdefault("invalidators", [])
        if "model_degradation" not in spec["invalidators"]:
            spec["invalidators"].append("model_degradation")

    return spec
