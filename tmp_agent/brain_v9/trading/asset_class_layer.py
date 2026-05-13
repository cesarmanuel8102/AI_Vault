from __future__ import annotations

from typing import Any, Dict, List


_VENUE_FAMILY_DEFAULTS: dict[tuple[str, str], list[str]] = {
    ("ibkr", "trend_following"): ["stocks", "etfs"],
    ("ibkr", "breakout"): ["stocks", "etfs", "options"],
    ("ibkr", "mean_reversion"): ["stocks", "etfs"],
    ("pocket_option", "mean_reversion"): ["otc_binary"],
    ("pocket_option", "breakout"): ["otc_binary"],
}


def _as_text(value: Any, default: str = "") -> str:
    if value is None:
        return default
    text = str(value).strip()
    return text if text else default


def infer_asset_classes(strategy: Dict[str, Any]) -> List[str]:
    explicit = [str(item).strip().lower() for item in strategy.get("asset_classes", []) if str(item).strip()]
    if explicit:
        return explicit
    venue = _as_text(strategy.get("venue")).lower()
    family = _as_text(strategy.get("family")).lower()
    inferred = _VENUE_FAMILY_DEFAULTS.get((venue, family))
    if inferred:
        return list(inferred)
    if venue == "pocket_option":
        return ["otc_binary"]
    if venue == "ibkr":
        return ["stocks"]
    return ["generic"]


def classify_symbol(symbol: str | None, venue: str | None) -> str:
    symbol_text = _as_text(symbol).upper()
    venue_text = _as_text(venue).lower()
    if venue_text == "pocket_option" or symbol_text.endswith("_OTC"):
        return "otc_binary"
    if symbol_text in {"EURUSD", "GBPUSD", "USDJPY", "USDCHF", "AUDUSD", "NZDUSD"}:
        return "fx"
    if symbol_text in {"BTCUSD", "ETHUSD", "SOLUSD"}:
        return "crypto"
    if "_OPT_" in symbol_text or symbol_text.endswith("C") and "_" in symbol_text:
        return "options"
    if symbol_text in {"SPY", "QQQ", "DIA", "IWM"}:
        return "etfs"
    return "stocks"


def build_execution_profile(strategy: Dict[str, Any]) -> Dict[str, Any]:
    venue = _as_text(strategy.get("venue")).lower()
    family = _as_text(strategy.get("family")).lower()
    asset_classes = infer_asset_classes(strategy)
    if venue == "pocket_option":
        return {
            "mode": "binary_demo_shadow",
            "entry_style": "expiry_based",
            "supports_live_signal_resolution": False,
             "preferred_holding_seconds": 300,
            "asset_classes": asset_classes,
        }
    if venue == "ibkr":
        return {
            "mode": "price_follow_up_shadow",
            "entry_style": "price_context",
            "supports_live_signal_resolution": True,
            "preferred_holding_seconds": 300 if family == "breakout" else 900,
            "asset_classes": asset_classes,
        }
    return {
        "mode": "generic_shadow",
        "entry_style": "generic",
        "supports_live_signal_resolution": False,
        "preferred_holding_seconds": 300,
        "asset_classes": asset_classes,
    }


def normalize_strategy_asset_profile(strategy: Dict[str, Any]) -> Dict[str, Any]:
    payload = dict(strategy)
    asset_classes = infer_asset_classes(payload)
    payload["asset_classes"] = asset_classes
    payload["primary_asset_class"] = asset_classes[0] if asset_classes else "generic"
    payload["execution_profile"] = build_execution_profile(payload)
    return payload
