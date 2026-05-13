"""
Brain V9 - Trading knowledge base
Base curada minima para teoria, indicadores, estrategias e hipotesis.
"""
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

log = logging.getLogger(__name__)

from brain_v9.config import BASE_PATH, PAPER_ONLY
from brain_v9.core.state_io import read_json, write_json

STATE_PATH = BASE_PATH / "tmp_agent" / "state"
KB_PATH = STATE_PATH / "trading_knowledge_base"
KB_PATH.mkdir(parents=True, exist_ok=True)

KNOWLEDGE_PATH = KB_PATH / "knowledge_base.json"
INDICATORS_PATH = KB_PATH / "indicator_registry.json"
STRATEGIES_PATH = KB_PATH / "strategy_specs.json"
HYPOTHESES_PATH = KB_PATH / "hypothesis_queue.json"
PO_BRIDGE_PATH = STATE_PATH / "rooms" / "brain_binary_paper_pb04_demo_execution" / "browser_bridge_latest.json"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _knowledge_seed() -> Dict:
    return {
        "schema_version": "trading_knowledge_base_v1",
        "updated_utc": _utc_now(),
        "source_policy": {
            "mode": "curated_internal_seed",
            "goal": "Convertir teoria de trading en conocimiento accionable y testeable para el Brain.",
            "notes": [
                "No sustituye research externo; lo organiza.",
                "Toda teoria debe poder convertirse a regla, setup o hipotesis.",
                "La promocion depende de resultados paper, no de teoria sola.",
            ],
        },
        "principles": [
            {
                "id": "trend_following",
                "title": "Trend following",
                "definition": "Favorecer entradas en direccion de la tendencia dominante en vez de luchar contra ella.",
                "when_valid": ["mercados direccionales", "rupturas con continuacion", "sesiones con momentum"],
                "when_invalid": ["rangos estrechos", "mercados extremadamente reversivos"],
                "risk_notes": ["entradas tardias", "whipsaws en transiciones de regimen"],
            },
            {
                "id": "mean_reversion",
                "title": "Mean reversion",
                "definition": "Buscar retorno hacia una media o zona de equilibrio despues de desviaciones excesivas.",
                "when_valid": ["rangos", "sobreextension local", "payout favorable con volatilidad contenida"],
                "when_invalid": ["breakouts reales", "cambios de regimen"],
                "risk_notes": ["atraparse contra tendencia fuerte", "promediar perdidas sin invalidador"],
            },
            {
                "id": "breakout_confirmation",
                "title": "Breakout confirmation",
                "definition": "No basta tocar un nivel; conviene confirmar expansion de rango, volumen o persistencia.",
                "when_valid": ["compresion previa", "niveles clave", "apertura o noticias"],
                "when_invalid": ["falsos rompimientos", "liquidez pobre"],
                "risk_notes": ["falsos breakouts", "spread amplio en microestructura debil"],
            },
        ],
        "risk_management": [
            {
                "id": "fixed_fractional_risk",
                "rule": "Riesgo por trade pequeno y estable en paper antes de cualquier escalado.",
                "good_practices": ["tamano constante por fase", "no doblar despues de perdida", "cortar estrategias con drawdown"],
            },
            {
                "id": "sample_before_promotion",
                "rule": "No promover una estrategia por pocos trades o por una sola sesion buena.",
                "good_practices": ["esperar muestra resuelta suficiente", "mirar expectancy y estabilidad", "usar out-of-sample cuando exista"],
            },
        ],
        "validation_principles": [
            "Separar teoria de ejecucion real paper.",
            "Cada estrategia debe definir entry, invalidator, exit y contexto.",
            "La señal sola no basta; hay que mirar spread, payout, latencia y calidad del dato.",
            "No usar live trading mientras el lane no este explicitamente promovido.",
        ],
    }


def _indicator_seed() -> Dict:
    return {
        "schema_version": "indicator_registry_v1",
        "updated_utc": _utc_now(),
        "indicators": [
            {
                "id": "rsi_14",
                "family": "momentum",
                "description": "Oscilador de momentum para detectar sobrecompra/sobreventa y divergencias.",
                "features": ["value", "cross_30", "cross_50", "cross_70", "slope"],
                "best_for": ["mean_reversion", "momentum_filter"],
                "warnings": ["puede quedar sobrecomprado mucho tiempo en tendencia"],
            },
            {
                "id": "ema_20_50",
                "family": "trend",
                "description": "Cruce y alineacion de medias para direccion y estructura.",
                "features": ["ema20", "ema50", "distance_pct", "cross_state"],
                "best_for": ["trend_following", "breakout_filter"],
                "warnings": ["lag en giros rapidos"],
            },
            {
                "id": "atr_14",
                "family": "volatility",
                "description": "Mide rango verdadero promedio y ayuda a filtrar ruido o definir expansion.",
                "features": ["atr", "atr_pct", "volatility_regime"],
                "best_for": ["breakout", "position_sizing", "regime_detection"],
                "warnings": ["no da direccion por si solo"],
            },
            {
                "id": "bollinger_20_2",
                "family": "volatility",
                "description": "Bandas para detectar compresion, expansion y retornos a media.",
                "features": ["bandwidth", "touch_upper", "touch_lower", "zscore"],
                "best_for": ["mean_reversion", "squeeze_breakout"],
                "warnings": ["toque de banda no implica reversal automatico"],
            },
            {
                "id": "microstructure_l1",
                "family": "market_microstructure",
                "description": "Features de top-of-book y ticks: spread, bid/ask size, last vs close.",
                "features": ["spread_abs", "spread_bps", "bid_ask_imbalance", "last_vs_close_pct"],
                "best_for": ["execution_filter", "entry_quality", "paper_lane_scoring"],
                "warnings": ["requiere datos frescos y comparables por venue"],
            },
            {
                "id": "stochastic_14_3_3",
                "family": "momentum",
                "description": "Oscilador de aceleracion para detectar extremos de corto plazo y giros rapidos.",
                "features": ["%k", "%d", "cross", "overbought", "oversold"],
                "best_for": ["mean_reversion", "timing_filter"],
                "warnings": ["puede dar muchas señales falsas en drift fuerte"],
            },
            {
                "id": "macd_12_26_9",
                "family": "momentum_trend",
                "description": "Momentum direccional y desaceleracion de corto plazo mediante linea, señal e histograma.",
                "features": ["macd", "signal", "histogram", "cross", "slope"],
                "best_for": ["trend_filter", "mean_reversion_filter"],
                "warnings": ["tiene lag en cambios bruscos"],
            },
        ],
    }


def _strategy_seed() -> Dict:
    return {
        "schema_version": "strategy_specs_v1",
        "updated_utc": _utc_now(),
        "strategies": [
            {
                "strategy_id": "ibkr_trend_pullback_v1",
                "venue_preference": ["ibkr"],
                "asset_classes": ["stocks", "etfs"],
                "family": "trend_following",
                "summary": "Entrar a favor de tendencia tras pullback controlado y confirmacion de continuidad.",
                "core_indicators": ["ema_20_50", "rsi_14", "microstructure_l1"],
                "entry_logic": [
                    "ema20 > ema50",
                    "retroceso local sin romper estructura",
                    "rsi vuelve a cruzar 50 al alza o recupera desde zona intermedia",
                    "spread y bid/ask imbalance no deteriorados",
                ],
                "invalidators": [
                    "ema20 cruza debajo de ema50",
                    "spread se expande demasiado",
                    "pullback rompe minimo estructural",
                ],
                "paper_only": PAPER_ONLY,
            },
            {
                "strategy_id": "ibkr_breakout_compression_v1",
                "venue_preference": ["ibkr"],
                "asset_classes": ["stocks", "options"],
                "family": "breakout",
                "summary": "Buscar compresion de volatilidad seguida de expansion confirmada.",
                "core_indicators": ["atr_14", "bollinger_20_2", "microstructure_l1"],
                "entry_logic": [
                    "bandwidth comprimido",
                    "ruptura del rango reciente",
                    "confirmacion por last vs close y spread razonable",
                ],
                "invalidators": [
                    "ruptura falla y vuelve al rango",
                    "microestructura pierde calidad",
                ],
                "paper_only": PAPER_ONLY,
            },
            {
                "strategy_id": "po_otc_reversion_probe_v1",
                "venue_preference": ["pocket_option"],
                "asset_classes": ["otc_binary"],
                "family": "mean_reversion",
                "summary": "Probe de reversion a media en OTC/binario con payout alto y sobreextension local.",
                "core_indicators": ["rsi_14", "bollinger_20_2"],
                "entry_logic": [
                    "payout superior a umbral minimo",
                    "sobreextension local con contexto de rango",
                    "expiry corto y setup claro",
                ],
                "invalidators": [
                    "contexto de breakout",
                    "payout insuficiente",
                    "latencia o feed degradado",
                ],
                "paper_only": PAPER_ONLY,
                "universe": ["EURUSD_otc"],
            },
            {
                "strategy_id": "po_audnzd_otc_reversion_v1",
                "venue_preference": ["pocket_option"],
                "asset_classes": ["otc_binary"],
                "family": "mean_reversion",
                "summary": "Candidato fresco de reversion corta en AUDNZD OTC usando payout alto y contexto de microdesviacion.",
                "core_indicators": ["rsi_14", "bollinger_20_2", "stochastic_14_3_3", "macd_12_26_9"],
                "entry_logic": [
                    "payout superior a umbral minimo",
                    "desviacion corta detectable en AUDNZD_otc",
                    "expiracion 60s",
                    "contexto local de rango sin breakout fuerte",
                ],
                "invalidators": [
                    "contexto de breakout",
                    "payout insuficiente",
                    "latencia o feed degradado",
                    "stream_symbol_mismatch",
                ],
                "paper_only": PAPER_ONLY,
                "universe": ["EURUSD_otc"],
            },
            {
                "strategy_id": "po_audnzd_otc_breakout_v1",
                "venue_preference": ["pocket_option"],
                "asset_classes": ["otc_binary"],
                "family": "breakout",
                "summary": "Candidato fresco de ruptura corta en AUDNZD OTC para aprovechar continuidad del movimiento visible en 60s.",
                "core_indicators": ["bollinger_20_2", "macd_12_26_9", "stochastic_14_3_3"],
                "entry_logic": [
                    "payout superior a umbral minimo",
                    "AUDNZD_otc visible y stream alineados",
                    "movimiento de corto plazo con continuidad detectable",
                    "regimen de ruptura o impulso en 60s",
                ],
                "invalidators": [
                    "missing_price_context",
                    "payout insuficiente",
                    "stream_symbol_mismatch",
                    "breakout_fail_revert",
                ],
                "paper_only": PAPER_ONLY,
                "universe": ["EURUSD_otc"],
            },
        ],
    }


def _hypothesis_seed() -> Dict:
    return {
        "schema_version": "hypothesis_queue_v2",
        "updated_utc": _utc_now(),
        "top_priority": "ibkr_trend_pullback_v1",
        "hypotheses": [
            {
                "id": "h_ibkr_pullback_quality",
                "strategy_id": "ibkr_trend_pullback_v1",
                "objective": "Comprobar si la calidad de microestructura mejora el expectancy frente a entradas naive.",
                "required_inputs": ["ema_20_50", "rsi_14", "microstructure_l1", "ibkr_l1_ticks"],
                "success_metric": "expectancy_positive_after_min_sample",
                "paper_only": PAPER_ONLY,
                "venue": "ibkr",
                "trigger": "entries_resolved >= 8 AND expectancy calculable",
                "expected_improvement": "+0.5 expectancy vs naive baseline",
                "risk_note": "Microstructure may add latency; only valid if fills confirm within 2s",
                "validation_plan": {
                    "min_sample": 15,
                    "acceptance_criteria": "expectancy > 0 AND win_rate > 0.45",
                    "max_duration_days": 14,
                    "abort_if": "drawdown > 5% of paper capital OR 10 consecutive losses",
                },
            },
            {
                "id": "h_ibkr_breakout_compression",
                "strategy_id": "ibkr_breakout_compression_v1",
                "objective": "Ver si compresion+expansion confirma mejor que breakout simple.",
                "required_inputs": ["atr_14", "bollinger_20_2", "microstructure_l1"],
                "success_metric": "higher_win_rate_than_baseline",
                "paper_only": PAPER_ONLY,
                "venue": "ibkr",
                "trigger": "entries_resolved >= 8 AND bandwidth_expansion detected",
                "expected_improvement": "+10% win_rate vs simple breakout",
                "risk_note": "Compression filter may reduce opportunity count significantly",
                "validation_plan": {
                    "min_sample": 20,
                    "acceptance_criteria": "win_rate > 0.50 AND expectancy > 0",
                    "max_duration_days": 21,
                    "abort_if": "expectancy < -2.0 after 10 resolved entries",
                },
            },
            {
                "id": "h_po_otc_payout_filter",
                "strategy_id": "po_otc_reversion_probe_v1",
                "objective": "Medir si un filtro de payout reduce perdidas en OTC demo.",
                "required_inputs": ["rsi_14", "payout_pct", "expiry_seconds", "session_result_scorecard"],
                "success_metric": "reduced_penalties_and_stable_outcomes",
                "paper_only": PAPER_ONLY,
                "venue": "pocket_option",
                "trigger": "payout_pct < 70 blocks entry; payout_pct >= 70 allows entry",
                "expected_improvement": "reduce loss_rate by 15% via payout floor filter",
                "risk_note": "May reduce trade frequency significantly in low-payout sessions",
                "validation_plan": {
                    "min_sample": 15,
                    "acceptance_criteria": "loss_rate < 0.55 AND net_profit improved vs unfiltered",
                    "max_duration_days": 7,
                    "abort_if": "no trades qualify for 48h due to payout filter",
                },
            },
            {
                "id": "h_po_audnzd_single_pair_reversion",
                "strategy_id": "po_audnzd_otc_reversion_v1",
                "objective": "Medir si AUDNZD OTC como par unico visible mejora timing y estabilidad frente al probe OTC multisimbolo ya refutado.",
                "required_inputs": [
                    "rsi_14",
                    "bollinger_20_2",
                    "stochastic_14_3_3",
                    "macd_12_26_9",
                    "payout_pct",
                    "expiry_seconds",
                    "audnzd_otc_short_horizon_feed",
                ],
                "success_metric": "positive_expectancy_with_visible_symbol_lock",
                "paper_only": PAPER_ONLY,
                "venue": "pocket_option",
                "trigger": "AUDNZD_otc visible AND payout >= 65% AND RSI extreme",
                "expected_improvement": "expectancy > 0 with single-pair focus (vs -0.85 on multi-symbol probe)",
                "risk_note": "Single-pair locks all capital to one symbol; regime shifts undetectable",
                "validation_plan": {
                    "min_sample": 20,
                    "acceptance_criteria": "expectancy > 0 AND sample_quality > 0.3",
                    "max_duration_days": 10,
                    "abort_if": "expectancy < -1.0 after 10 entries OR 0 entries in 72h",
                },
            },
            {
                "id": "h_po_audnzd_single_pair_breakout",
                "strategy_id": "po_audnzd_otc_breakout_v1",
                "objective": "Medir si AUDNZD OTC visible permite capturar continuidad de ruptura en 60s mejor que un setup de reversion.",
                "required_inputs": [
                    "bollinger_20_2",
                    "macd_12_26_9",
                    "stochastic_14_3_3",
                    "payout_pct",
                    "expiry_seconds",
                    "audnzd_otc_short_horizon_feed",
                ],
                "success_metric": "positive_expectancy_after_short_horizon_breakout_sample",
                "paper_only": PAPER_ONLY,
                "venue": "pocket_option",
                "trigger": "Bollinger expansion + MACD momentum aligned + payout >= 65%",
                "expected_improvement": "expectancy > 0 on breakout continuation within 60s window",
                "risk_note": "Breakout on OTC may be fake expansion; payout asymmetry may dominate",
                "validation_plan": {
                    "min_sample": 15,
                    "acceptance_criteria": "expectancy > 0 AND win_rate > 0.50",
                    "max_duration_days": 10,
                    "abort_if": "10 consecutive losses OR expectancy < -2.0 after 8 entries",
                },
            },
        ],
    }


def prune_orphan_hypotheses() -> List[str]:
    """P5-08: Remove hypotheses whose strategy_id has no matching strategy spec.

    Returns list of pruned hypothesis IDs (empty if none removed).
    """
    strategies_data = read_json(STRATEGIES_PATH, _strategy_seed())
    valid_ids = {
        s.get("strategy_id") or s.get("id")
        for s in strategies_data.get("strategies", [])
    }
    valid_ids.discard(None)

    hyp_data = read_json(HYPOTHESES_PATH, _hypothesis_seed())
    hypotheses = hyp_data.get("hypotheses", [])
    pruned: List[str] = []
    kept: List[Dict] = []
    for h in hypotheses:
        if h.get("strategy_id") in valid_ids:
            kept.append(h)
        else:
            pruned.append(h.get("id", h.get("strategy_id", "unknown")))

    if pruned:
        hyp_data["hypotheses"] = kept
        hyp_data["updated_utc"] = _utc_now()
        # If top_priority points to a pruned strategy, clear it
        if hyp_data.get("top_priority") and hyp_data["top_priority"] not in valid_ids:
            hyp_data["top_priority"] = kept[0]["strategy_id"] if kept else None
        write_json(HYPOTHESES_PATH, hyp_data)

    return pruned


def ensure_research_foundation() -> Dict:
    if not KNOWLEDGE_PATH.exists():
        write_json(KNOWLEDGE_PATH, _knowledge_seed())
    if not INDICATORS_PATH.exists():
        write_json(INDICATORS_PATH, _indicator_seed())
    if not STRATEGIES_PATH.exists():
        write_json(STRATEGIES_PATH, _strategy_seed())
    if not HYPOTHESES_PATH.exists():
        write_json(HYPOTHESES_PATH, _hypothesis_seed())
    # P5-08: prune hypotheses referencing non-existent strategies
    prune_orphan_hypotheses()
    return get_research_summary()


def get_research_summary() -> Dict:
    knowledge = read_json(KNOWLEDGE_PATH, _knowledge_seed())
    indicators = read_json(INDICATORS_PATH, _indicator_seed())
    strategies = read_json(STRATEGIES_PATH, _strategy_seed())
    hypotheses = read_json(HYPOTHESES_PATH, _hypothesis_seed())
    return {
        "updated_utc": _utc_now(),
        "knowledge_base_path": str(KNOWLEDGE_PATH),
        "indicator_registry_path": str(INDICATORS_PATH),
        "strategy_specs_path": str(STRATEGIES_PATH),
        "hypothesis_queue_path": str(HYPOTHESES_PATH),
        "principles_count": len(knowledge.get("principles", [])),
        "risk_rules_count": len(knowledge.get("risk_management", [])),
        "indicators_count": len(indicators.get("indicators", [])),
        "strategies_count": len(strategies.get("strategies", [])),
        "hypotheses_count": len(hypotheses.get("hypotheses", [])),
        "top_priority_strategy": hypotheses.get("top_priority"),
        "primary_venues": sorted({
            venue
            for s in strategies.get("strategies", [])
            for venue in (s.get("venue_preference") or ([s.get("venue")] if s.get("venue") else []))
        }),
    }


def read_knowledge_base() -> Dict:
    ensure_research_foundation()
    return read_json(KNOWLEDGE_PATH, {})


def read_indicator_registry() -> Dict:
    ensure_research_foundation()
    return read_json(INDICATORS_PATH, {})


def read_strategy_specs() -> Dict:
    ensure_research_foundation()
    payload = read_json(STRATEGIES_PATH, {})
    strategies = payload.get("strategies", [])
    if strategies and all(not (s.get("strategy_id") or s.get("id")) for s in strategies):
        repaired = _strategy_seed()
        write_json(STRATEGIES_PATH, repaired)
        return repaired
    return payload


def read_hypothesis_queue() -> Dict:
    ensure_research_foundation()
    return read_json(HYPOTHESES_PATH, {})


def build_strategy_candidates(strategies: List[Dict] | None = None) -> List[Dict]:
    strategies = strategies if strategies is not None else read_strategy_specs().get("strategies", [])
    hypotheses = {h["strategy_id"]: h for h in read_hypothesis_queue().get("hypotheses", [])}
    candidates = []
    for strategy in strategies:
        strategy_id = strategy.get("strategy_id") or strategy.get("id")
        hypothesis = hypotheses.get(strategy_id, {})
        candidates.append({
            "strategy_id": strategy_id,
            "family": strategy.get("family"),
            "venues": strategy.get("venue_preference", [strategy.get("venue")] if strategy.get("venue") else []),
            "summary": strategy.get("summary"),
            "indicators": strategy.get("core_indicators", []),
            "objective": hypothesis.get("objective"),
            "success_metric": hypothesis.get("success_metric"),
            "paper_only": strategy.get("paper_only", PAPER_ONLY),
        })
    return candidates


_log = logging.getLogger("knowledge_base")

# P8-05: Family inversion map for generating opposite-thesis variants.
_FAMILY_INVERSE = {
    "breakout": "mean_reversion",
    "mean_reversion": "breakout",
    "trend_following": "mean_reversion",
    "momentum_trend": "mean_reversion",
}

# P8-05: Indicator pools per family for building core_indicators on variants.
_FAMILY_INDICATORS = {
    "mean_reversion": ["rsi_14", "bollinger_20_2", "stochastic_14_3_3"],
    "breakout": ["bollinger_20_2", "macd_12_26_9", "atr_14"],
    "trend_following": ["ema_20_50", "rsi_14", "macd_12_26_9"],
}

# P8-05: Extended OTC symbol pool for PocketOption variants.
_PO_OTC_SYMBOLS = [
    "AUDNZD_otc", "AUDUSD_otc", "EURUSD_otc",
    "GBPUSD_otc", "USDCHF_otc", "NZDUSD_otc",
]

# P8-05: IBKR symbol pool for equity variants.
_IBKR_SYMBOLS = ["SPY", "QQQ", "IWM", "AAPL", "MSFT"]


def _active_po_symbol() -> str | None:
    bridge = read_json(PO_BRIDGE_PATH, {})
    current = bridge.get("current", {}) if isinstance(bridge, dict) else {}
    symbol = current.get("symbol") if isinstance(current, dict) else None
    return str(symbol).strip() if symbol else None


def _variant_universe_for_source(source: Dict[str, Any], src_venues: List[str]) -> List[str]:
    src_universe = list(source.get("universe") or [])
    # Alternate PO symbols to pick from when we need something different
    _PO_ALTERNATES = ["EURUSD_otc", "GBPUSD_otc", "USDJPY_otc", "EURGBP_otc", "AUDNZD_otc"]
    _IBKR_ALTERNATES = ["SPY", "QQQ", "AAPL", "MSFT", "IWM"]
    if "pocket_option" in src_venues:
        active_symbol = _active_po_symbol()
        if active_symbol and active_symbol not in src_universe:
            return [active_symbol]
        # Pick an alternate symbol that is NOT in the source universe
        for alt in _PO_ALTERNATES:
            if alt not in src_universe:
                return [alt]
        # Last resort — all alternates are in source; just use first alternate
        return [_PO_ALTERNATES[0]]
    if "ibkr" in src_venues:
        if src_universe:
            return src_universe[: min(len(src_universe), 3)]
        return ["SPY", "QQQ", "AAPL"]
    return src_universe or ["EURUSD_otc"]


def generate_strategy_variants(max_variants: int = 2) -> List[str]:
    """P8-05: Generate new strategy variants from existing frozen strategies.

    Creates up to ``max_variants`` new strategy specs by:
    - Taking frozen strategies and flipping the family (breakout ↔ reversion)
    - Using different symbols from the same venue
    - Adding corresponding hypotheses

    Skips generation if variants with the proposed IDs already exist.
    Returns a list of newly created strategy_id strings.

    P-OP7: Hard cap at MAX_TOTAL_STRATEGIES (50) to prevent variant
    proliferation from exhausting resources and making the catalog
    unmanageable.  Once the cap is reached, no new variants are created
    until strategies are archived/removed.
    """
    MAX_TOTAL_STRATEGIES = 50

    strategies_data = read_strategy_specs()
    existing = strategies_data.get("strategies", [])
    existing_ids = {s.get("strategy_id") or s.get("id") for s in existing}

    # P-OP7: Refuse to generate if we already have too many strategies
    if len(existing) >= MAX_TOTAL_STRATEGIES:
        log.info(
            "P-OP7: Strategy cap reached (%d >= %d), skipping variant generation.",
            len(existing), MAX_TOTAL_STRATEGIES,
        )
        return []

    # Read scorecards to find frozen strategies
    from brain_v9.trading.strategy_scorecard import read_scorecards
    scorecards_payload = read_scorecards()
    scorecards = scorecards_payload.get("scorecards", {})

    # Collect frozen sources to derive variants from
    frozen_sources: List[Dict] = []
    for strategy in existing:
        sid = strategy.get("strategy_id") or strategy.get("id")
        card = scorecards.get(sid, {})
        gov_state = str(card.get("governance_state") or "")
        if gov_state in ("frozen", "retired") or card.get("archive_state") == "archived_refuted":
            frozen_sources.append(strategy)

    if not frozen_sources:
        # Also try non-frozen strategies that simply aren't executing
        # (e.g., paper_candidate with 0 trades)
        for strategy in existing:
            sid = strategy.get("strategy_id") or strategy.get("id")
            card = scorecards.get(sid, {})
            if int(card.get("entries_resolved", 0) or 0) == 0:
                frozen_sources.append(strategy)

    # P-OP2: Prioritise venues that are currently trading (24/7 venues like
    # Pocket Option go before venues whose market is closed) so we don't
    # waste max_variants slots on unreachable venues.
    _VENUE_AVAILABILITY_ORDER = {"pocket_option": 0, "ibkr": 1}
    frozen_sources.sort(
        key=lambda s: _VENUE_AVAILABILITY_ORDER.get(
            (s.get("venue_preference") or [s.get("venue")])[0]
            if (s.get("venue_preference") or [s.get("venue")])
            else "zzz",
            2,
        )
    )

    new_ids: List[str] = []
    hyp_data = read_json(HYPOTHESES_PATH, _hypothesis_seed())
    hypotheses = hyp_data.get("hypotheses", [])

    for source in frozen_sources:
        if len(new_ids) >= max_variants:
            break

        src_id = source.get("strategy_id") or source.get("id") or ""
        src_family = source.get("family", "")
        src_venues = source.get("venue_preference") or []

        # P-OP54d: Skip PocketOption auto-variants entirely. These shells
        # share the SAME signal_engine code paths as the parent strategy
        # (breakout or mean_reversion) with no differentiated logic. All
        # 8 previously generated PO variants (v2-v9_auto) had 0 entries or
        # negative expectancy. Only manual strategy specs with intentional
        # parameter changes should be created for PO.
        _inferred_venue = src_venues[0] if src_venues else ("pocket_option" if src_id.startswith("po") else "")
        if _inferred_venue == "pocket_option":
            log.info("P-OP54d: Skipping auto-variant for PO strategy %s — PO variants disabled.", src_id)
            continue
        # Infer venue from strategy_id prefix when venue_preference is missing
        if not src_venues:
            if src_id.startswith("ibkr"):
                src_venues = ["ibkr"]
            elif src_id.startswith("po"):
                src_venues = ["pocket_option"]
        src_universe = source.get("universe", [])

        # Derive inverse family
        new_family = _FAMILY_INVERSE.get(src_family, "mean_reversion")

        # Build variant ID
        # e.g. ibkr_trend_pullback_v1 → ibkr_mean_reversion_v2_auto
        venue_prefix = src_venues[0] if src_venues else "auto"
        if venue_prefix == "pocket_option":
            venue_prefix = "po"
        variant_id = f"{venue_prefix}_{new_family}_v2_auto"

        # Ensure unique
        if variant_id in existing_ids:
            # Try incrementing suffix
            for suffix_n in range(3, 10):
                candidate_id = f"{venue_prefix}_{new_family}_v{suffix_n}_auto"
                if candidate_id not in existing_ids:
                    variant_id = candidate_id
                    break
            else:
                continue  # All slots taken

        if variant_id in existing_ids:
            continue

        # Reuse the strategy base according to venue/type instead of jumping to
        # unrelated symbols.  For Pocket Option, prefer the active visible pair.
        if "pocket_option" in src_venues:
            new_universe = _variant_universe_for_source(source, src_venues)
            asset_classes = ["otc_binary"]
        elif "ibkr" in src_venues:
            new_universe = _variant_universe_for_source(source, src_venues)
            asset_classes = ["stocks", "etfs"]
        else:
            new_universe = _variant_universe_for_source(source, src_venues)
            asset_classes = source.get("asset_classes", ["otc_binary"])

        new_indicators = _FAMILY_INDICATORS.get(new_family, ["rsi_14", "bollinger_20_2"])

        new_strategy = {
            "strategy_id": variant_id,
            "venue_preference": src_venues,
            "asset_classes": asset_classes,
            "family": new_family,
            "summary": (
                f"Auto-generated {new_family} variant derived from frozen "
                f"strategy {src_id}. Explores inverse thesis on "
                f"{', '.join(new_universe)}."
            ),
            "core_indicators": new_indicators,
            "entry_logic": [
                f"auto-generated {new_family} entry logic",
                "payout/spread must meet minimum threshold",
                f"regime compatible with {new_family}",
            ],
            "invalidators": [
                "regime incompatible",
                "feed degraded or stale",
            ],
            "paper_only": PAPER_ONLY,
            "universe": new_universe,
            "timeframes": list(source.get("timeframes") or (["5m"] if "pocket_option" in src_venues else ["5m", "15m"])),
            "success_criteria": dict(source.get("success_criteria") or {}),
            "setup_variants": list(source.get("setup_variants") or []),
            "auto_generated": True,
            "source_strategy": src_id,
        }

        existing.append(new_strategy)
        existing_ids.add(variant_id)
        new_ids.append(variant_id)

        # Create matching hypothesis
        new_hypothesis = {
            "id": f"h_{variant_id}",
            "strategy_id": variant_id,
            "objective": (
                f"Test whether {new_family} approach on "
                f"{', '.join(new_universe)} outperforms the frozen "
                f"{src_family} strategy {src_id}."
            ),
            "required_inputs": new_indicators,
            "success_metric": "positive_expectancy_after_min_sample",
            "paper_only": PAPER_ONLY,
            "auto_generated": True,
        }
        hypotheses.append(new_hypothesis)

    if new_ids:
        strategies_data["strategies"] = existing
        strategies_data["updated_utc"] = _utc_now()
        write_json(STRATEGIES_PATH, strategies_data)

        hyp_data["hypotheses"] = hypotheses
        hyp_data["updated_utc"] = _utc_now()
        write_json(HYPOTHESES_PATH, hyp_data)

        _log.info(
            "P8-05: Generated %d strategy variant(s): %s",
            len(new_ids), new_ids,
        )

    return new_ids
