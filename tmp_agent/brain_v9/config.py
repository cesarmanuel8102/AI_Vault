"""
Brain Chat V9 — Configuración central
Todas las constantes vienen de variables de entorno o defaults seguros.
NUNCA hardcodear rutas o credenciales aquí.
"""
import json
import logging
import os
import platform
from pathlib import Path
from typing import Dict

_log = logging.getLogger("config")


def _load_env_file(path: Path) -> None:
    """
    Carga un archivo .env simple en os.environ sin pisar variables ya definidas.

    Soporta lineas del tipo KEY=VALUE, ignora comentarios y blanks.
    Mantiene el contrato env-first: el .env solo rellena faltantes.
    """
    try:
        if not path.exists():
            return
        for raw_line in path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if line.lower().startswith("export "):
                line = line[7:].strip()
            if "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            if not key or key in os.environ:
                continue
            value = value.strip().strip('"').strip("'")
            os.environ[key] = value
    except Exception as exc:
        _log.debug("_load_env_file failed for %s: %s", path, exc)

# ─── Rutas base ──────────────────────────────────────────────────────────────
_default_base = (
    "C:/AI_VAULT" if platform.system() == "Windows"
    else str(Path.home() / "AI_VAULT")
)
BASE_PATH   = Path(os.getenv("BRAIN_BASE_PATH", _default_base))
_load_env_file(BASE_PATH / ".env")
MEMORY_PATH = BASE_PATH / "tmp_agent" / "state" / "memory"
LOGS_PATH   = BASE_PATH / "tmp_agent" / "logs"
RSI_PATH    = BASE_PATH / "tmp_agent" / "state" / "rsi"
BRAIN_V9_PATH = BASE_PATH / "tmp_agent"
PREMISES_FILE = BASE_PATH / "Brain_Lab_Premisas_Canonicas_v3_2026-03-16.md"

# ─── State directories (P7-02) ───────────────────────────────────────────────
STATE_PATH = BASE_PATH / "tmp_agent" / "state"
STRATEGY_ENGINE_PATH = STATE_PATH / "strategy_engine"
AUTONOMY_STATE_PATH = STATE_PATH / "autonomy"
AUTONOMY_CYCLE_LATEST_PATH = AUTONOMY_STATE_PATH / "autonomy_cycle_latest.json"
ROOT_LOGS_PATH = BASE_PATH / "logs"
AGENT_EVENTS_LOG_PATH = ROOT_LOGS_PATH / "agent_events.ndjson"
CONTROL_LAYER_STATUS_PATH = STATE_PATH / "control_layer_status.json"

# ─── Log accumulation directories (Fase 7.1) ─────────────────────────────────
# All directories where shell scripts (watchdog, autonomy loop) dump log files.
# self_diagnostic.py uses this list for cleanup and rotation.
LOG_ACCUMULATION_DIRS = [
    STATE_PATH / "logs",           # ~4790 files from autonomy watchdog
    STATE_PATH / "reports",        # ~1120 files from autonomy loop
    BASE_PATH / "tmp_agent" / "workspace",  # ~142 files from dev scripts
    BASE_PATH / "tmp_agent" / "ops" / "logs",  # ~44 files from ops
    BASE_PATH / "tmp_agent" / "logs",          # ~30 files from startup scripts
    ROOT_LOGS_PATH,                # root logs (agent_events, etc.)
]
LOG_RETENTION_DAYS = 3  # Keep logs from last 3 days, delete older

# Room directories
IBKR_ROOM_DIR = STATE_PATH / "rooms" / "brain_financial_ingestion_fi04_structured_api"
PO_ROOM_DIR = STATE_PATH / "rooms" / "brain_binary_paper_pb04_demo_execution"
PO_VERIFICATION_ROOM_DIR = STATE_PATH / "rooms" / "brain_binary_paper_pb01_venue_verification"

# ─── IBKR artifact paths (P7-02) ─────────────────────────────────────────────
IBKR_LANE_ARTIFACT = IBKR_ROOM_DIR / "ibkr_readonly_lane.json"
IBKR_PROBE_ARTIFACT = IBKR_ROOM_DIR / "ibkr_marketdata_probe_status.json"
IBKR_PROBE_STATUS_ARTIFACT = IBKR_ROOM_DIR / "ibkr_readonly_probe_status.json"
IBKR_ORDER_CHECK_ARTIFACT = STATE_PATH / "trading_execution_checks" / "ibkr_paper_order_check_latest.json"

PO_BRIDGE_LATEST_ARTIFACT = PO_ROOM_DIR / "browser_bridge_latest.json"
PO_FEED_ARTIFACT = PO_ROOM_DIR / "browser_bridge_normalized_feed.json"
PO_EVENTS_ARTIFACT = PO_ROOM_DIR / "browser_bridge_events.ndjson"
PO_COMMANDS_ARTIFACT = PO_ROOM_DIR / "browser_bridge_commands.json"
PO_COMMAND_LATEST_ARTIFACT = PO_ROOM_DIR / "browser_bridge_command_latest.json"
PO_COMMAND_RESULT_ARTIFACT = PO_ROOM_DIR / "browser_bridge_command_result_latest.json"
PO_DUE_DILIGENCE_ARTIFACT = PO_ROOM_DIR / "browser_bridge_due_diligence.json"

# ─── Other state artifacts (P7-02) ───────────────────────────────────────────
SAMPLE_ACCUMULATOR_STATE = STATE_PATH / "sample_accumulator.json"
TRADING_POLICY_PATH = STATE_PATH / "trading_autonomy_policy.json"

def _mkdirs():
    """Crea directorios necesarios sin romper el import si fallan."""
    for p in [MEMORY_PATH, LOGS_PATH, RSI_PATH, STRATEGY_ENGINE_PATH,
              IBKR_ROOM_DIR, PO_ROOM_DIR, PO_VERIFICATION_ROOM_DIR,
              STATE_PATH / "trading_execution_checks", AUTONOMY_STATE_PATH,
              ROOT_LOGS_PATH]:
        try:
            p.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            print(f"[WARNING] No se pudo crear {p}: {e}")

_mkdirs()

# ─── Runtime safety gates ────────────────────────────────────────────────────
# Override operativo local: este nodo queda en modo dev persistente por defecto.
# Si se quiere volver a modo seguro, el entorno debe fijar BRAIN_SAFE_MODE=true
# de forma explícita.
BRAIN_SAFE_MODE = os.getenv("BRAIN_SAFE_MODE", "false").lower() == "true"
BRAIN_START_AUTONOMY = os.getenv("BRAIN_START_AUTONOMY", "false").lower() == "true"
BRAIN_START_PROACTIVE = os.getenv("BRAIN_START_PROACTIVE", "false").lower() == "true"
BRAIN_START_SELF_DIAGNOSTIC = os.getenv("BRAIN_START_SELF_DIAGNOSTIC", "false").lower() == "true"
BRAIN_START_QC_LIVE_MONITOR = os.getenv("BRAIN_START_QC_LIVE_MONITOR", "false").lower() == "true"
BRAIN_WARMUP_MODEL = os.getenv("BRAIN_WARMUP_MODEL", "false").lower() == "true"
BRAIN_ENABLE_UNSAFE_DEV_ENDPOINTS = (
    os.getenv("BRAIN_ENABLE_UNSAFE_DEV_ENDPOINTS", "true").lower() == "true"
)
BRAIN_CHAT_DEV_MODE = os.getenv("BRAIN_CHAT_DEV_MODE", "true").lower() == "true"
BRAIN_ENABLE_FINANCIAL_AUTOCYCLE = (
    os.getenv("BRAIN_ENABLE_FINANCIAL_AUTOCYCLE", "false").lower() == "true"
)

# ─── Carga segura de secrets desde archivos JSON ──────────────────────────────
def _load_secret(path: Path, key: str = "token") -> str:
    """Lee una clave desde archivo JSON. Silencioso si no existe."""
    try:
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            return data.get(key, data.get("api_key", data.get("password", "")))
    except Exception as exc:
        _log.debug("_load_secret failed for %s: %s", path, exc)
    return ""

_secrets_dir = BASE_PATH / "tmp_agent" / "Secrets"

API_KEYS = {
    # Sección 16: runtime canónico env-first sin fallback JSON para LLM providers.
    "openai": os.getenv("OPENAI_API_KEY"),
    "anthropic": os.getenv("ANTHROPIC_API_KEY"),
    "gemini": os.getenv("GEMINI_API_KEY"),
}

API_ENDPOINTS = {
    "gpt4":   os.getenv("OPENAI_API_URL",  "https://api.openai.com/v1/chat/completions"),
    "openai_responses": os.getenv("OPENAI_RESPONSES_API_URL", "https://api.openai.com/v1/responses"),
    "claude": os.getenv("CLAUDE_API_URL",  "https://api.anthropic.com/v1/messages"),
    "gemini": os.getenv("GEMINI_API_URL",  "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-pro:generateContent"),
    # CORRECCIÓN CRÍTICA: llama2 no existe — usar qwen2.5:14b disponible en Ollama
    "ollama": os.getenv("OLLAMA_URL",      "http://localhost:11434/api/chat"),
}

# Modelos Ollama
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.1:8b")
OLLAMA_AGENT_MODEL = os.getenv("OLLAMA_AGENT_MODEL", "deepseek-r1:14b")
OPENAI_CODEX_MODEL = os.getenv("OPENAI_CODEX_MODEL", "gpt-5.1-codex-mini")
_default_codex_cli = str(Path(os.getenv("APPDATA", str(Path.home()))) / "npm" / "codex.ps1")
CODEX_CLI_PATH = os.getenv(
    "CODEX_CLI_PATH",
    _default_codex_cli if Path(_default_codex_cli).exists() else "codex",
)
CODEX_CLI_MODEL = os.getenv("CODEX_CLI_MODEL", "gpt-5.5")

# ─── LLM ──────────────────────────────────────────────────────────────────────
LLM_CONFIG = {
    "timeout":      int(os.getenv("LLM_TIMEOUT",      "240")),
    "agent_timeout": int(os.getenv("LLM_AGENT_TIMEOUT", "300")),
    "temperature":  float(os.getenv("LLM_TEMPERATURE","0.7")),
    "max_tokens":   int(os.getenv("LLM_MAX_TOKENS",   "8192")),
}

# ─── Servidor ─────────────────────────────────────────────────────────────────
SERVER_HOST = os.getenv("BRAIN_HOST", "127.0.0.1")
SERVER_PORT = int(os.getenv("BRAIN_PORT", "8090"))

# ─── Trading policy ───────────────────────────────────────────────────────────
# P5-07: Single source of truth for paper-only mode.  Every module that
# needs to know whether live trading is allowed reads this constant.
PAPER_ONLY: bool = os.getenv("PAPER_ONLY", "true").lower() == "true"

# When True, IBKR is accessed via QC Cloud (not local Gateway).
# Disables local IBKR Gateway polling, ingester, and health checks.
# Brain monitors IBKR positions/orders through the QC Live API instead.
IBKR_VIA_QC_CLOUD: bool = os.getenv("IBKR_VIA_QC_CLOUD", "true").lower() == "true"

# ─── Network addresses ────────────────────────────────────────────────────────
IBKR_HOST: str = os.getenv("IBKR_HOST", "127.0.0.1")
IBKR_PORT: int = int(os.getenv("IBKR_PORT", "4002"))
POCKETOPTION_BRIDGE_URL: str = os.getenv("POCKETOPTION_BRIDGE_URL", "")

# POCKETOPTION_BRIDGE_URL: str = os.getenv("POCKETOPTION_BRIDGE_URL", "http://127.0.0.1:8765")


# ─── Ledger / cooldown constants ──────────────────────────────────────────────
# P6-03: Single definition — used by action_executor and paper_execution.
MAX_LEDGER_ENTRIES: int = int(os.getenv("MAX_LEDGER_ENTRIES", "500"))
ACTION_COOLDOWN_SECONDS: int = int(os.getenv("ACTION_COOLDOWN_SECONDS", "120"))  # P-OP20c: was 300s

# ─── Paper trade defaults ─────────────────────────────────────────────────────
PAPER_TRADE_DEFAULT_AMOUNT: float = float(
    os.getenv("PAPER_TRADE_DEFAULT_AMOUNT", "10.0")
)

# ─── System health thresholds ─────────────────────────────────────────────────
# P6-03: Consistent thresholds for manager.py and self_diagnostic.py.
CPU_THRESHOLD_PCT: int = int(os.getenv("CPU_THRESHOLD_PCT", "85"))
MEMORY_THRESHOLD_PCT: int = int(os.getenv("MEMORY_THRESHOLD_PCT", "90"))
DISK_THRESHOLD_PCT: int = int(os.getenv("DISK_THRESHOLD_PCT", "90"))

# ─── Data freshness thresholds ────────────────────────────────────────────────
# P5-09: Maximum age (seconds) for market-data features before the signal
# engine rejects them as stale.  Per-venue overrides; "_default" is the
# fallback for unknown venues.
FEATURE_MAX_AGE_SECONDS: Dict[str, int] = {
    "ibkr": int(os.getenv("FEATURE_MAX_AGE_IBKR", "900")),          # 15 min
    "_default": int(os.getenv("FEATURE_MAX_AGE_DEFAULT", "600")),    # 10 min
}

# ─── Trading session awareness (P-OP22) ──────────────────────────────────────
# Forex/OTC binary markets have measurable intraday seasonality.
# Sessions are defined in UTC hours.  Each session has a quality tier
# that the signal engine uses to gate or annotate trades.
#
# Mode: "observe" = annotate only (no blocking), "enforce" = block low-quality
# sessions, "adaptive" = block only sessions with demonstrated poor win rate.
SESSION_FILTER_MODE: str = os.getenv("SESSION_FILTER_MODE", "adaptive")

# Minimum resolved trades in a session before adaptive blocking is considered.
# P-OP54e: Reduced from 15 to 10. ny_close had 10 trades at 20% WR but
# wasn't blocked because it hadn't reached the 15-trade threshold.
SESSION_MIN_SAMPLE_FOR_BLOCK: int = int(os.getenv("SESSION_MIN_SAMPLE_FOR_BLOCK", "10"))

# If adaptive mode: block session if win_rate < this (relative to breakeven).
# P-OP54e: Raised from 0.45 to 0.55. With actual PO payouts of ~60% (not
# the displayed 92%), breakeven WR is ~62.5%. Any session below 55% is a
# confirmed money-loser. The old 0.45 threshold only blocked catastrophic
# sessions (asian_early at 29%), missing sessions like ny_afternoon (48.9%)
# and ny_close (20%) that were still burning capital.
SESSION_BLOCK_WIN_RATE_THRESHOLD: float = float(
    os.getenv("SESSION_BLOCK_WIN_RATE_THRESHOLD", "0.55")
)

SESSION_WINDOWS: Dict[str, Dict] = {
    "asian_early":  {"hours_utc": (0, 3),   "quality": "low",       "label": "Asian Early (Tokyo)"},
    "asian_late":   {"hours_utc": (3, 7),    "quality": "low",       "label": "Asian Late"},
    "london_open":  {"hours_utc": (7, 10),   "quality": "high",      "label": "London Open"},
    "london_mid":   {"hours_utc": (10, 13),  "quality": "medium",    "label": "London Midday"},
    "ny_open":      {"hours_utc": (13, 16),  "quality": "very_high", "label": "NY Open / Overlap"},
    "ny_afternoon": {"hours_utc": (16, 19),  "quality": "medium",    "label": "NY Afternoon"},
    "ny_close":     {"hours_utc": (19, 21),  "quality": "low",       "label": "NY Close"},
    "off_hours":    {"hours_utc": (21, 24),  "quality": "very_low",  "label": "Off Hours / Dead Zone"},
}

# Quality tiers that are blocked in "enforce" mode (not in "observe" or "adaptive")
# P-OP30b: Added "low" — asian_early (27% WR over 84 trades), asian_late, ny_close
# were burning capital in enforce mode because only "very_low" was blocked.
SESSION_BLOCKED_QUALITIES: frozenset = frozenset({"very_low", "low"})

# Path for session performance tracker state
SESSION_PERF_PATH: Path = STRATEGY_ENGINE_PATH / "session_performance_latest.json"


def get_current_session(hour_utc: int) -> Dict:
    """Return the session dict for a given UTC hour (0-23)."""
    for name, window in SESSION_WINDOWS.items():
        start, end = window["hours_utc"]
        if start <= hour_utc < end:
            return {"session_name": name, **window}
    # Fallback for hour 24 edge case
    return {"session_name": "off_hours", **SESSION_WINDOWS["off_hours"]}


# ─── Venue market-hours gate (P-OP30a) ───────────────────────────────────────
# IBKR trades on weekends resolve as loss (price frozen → tie → loss).
# Gate IBKR execution on US equity market hours: Mon-Fri, 13:30-20:00 UTC.
def is_venue_market_open(venue: str) -> bool:
    """Check if the market for a given venue is currently open.

    IBKR (US equities): Mon-Fri, 13:30-20:00 UTC.
    Unknown venues: Default to open.
    """
    from datetime import datetime as _dt, timezone as _tz
    now_utc = _dt.now(_tz.utc)

    if venue == "ibkr":
        weekday = now_utc.weekday()  # 0=Mon … 5=Sat, 6=Sun
        if weekday >= 5:
            return False
        hour_frac = now_utc.hour + now_utc.minute / 60.0
        # US market: 09:30-16:00 ET  ≈  13:30-20:00 UTC (covers both EST & EDT)
        return 13.5 <= hour_frac < 20.0

        return True

    return True  # unknown venues → open


# ─── Signal threshold auto-tuning (P-OP23) ───────────────────────────────────
# Base signal thresholds for indicator evaluation.  These are the starting
# points; adapt_strategy_parameters() will adjust per-strategy based on
# scorecard results.  The signal engine reads the adapted values from the
# strategy dict, falling back to these defaults.
#
# Each threshold has a _STRONG (extreme) and _MILD (moderate) variant.
# Adaptation can shift them by up to ±30% from base.
# P-OP54c: Tightened mild thresholds for OTC binary options iteration.
# Data: 64 trades, ALL strategies losing. Mild thresholds (RSI<35, Stoch<30)
# triggered too easily in OTC micro-moves, generating low-quality signals.
# Tightened mild → strong range overlap to require more extreme conditions.
# Net effect: fewer trades, but each trade has stronger indicator backing.
SIGNAL_THRESHOLDS_BASE: Dict[str, Dict[str, float]] = {
    "rsi": {
        "oversold_strong": 22.0,   # RSI < this → strong oversold (was 25)
        "oversold_mild": 30.0,     # RSI < this → mild oversold   (was 35, P-OP54c)
        "overbought_strong": 78.0, # RSI > this → strong overbought (was 75)
        "overbought_mild": 70.0,   # RSI > this → mild overbought  (was 65, P-OP54c)
    },
    "bb": {
        "lower_strong": -0.15,     # %B < this → strong lower band break (was -0.10)
        "lower_mild": 0.10,        # %B < this → mild lower band approach (was 0.15)
        "upper_strong": 1.15,      # %B > this → strong upper band break (was 1.10)
        "upper_mild": 0.90,        # %B > this → mild upper band approach (was 0.85)
    },
    "stoch": {
        "oversold_strong": 12.0,   # K < this → strong oversold (was 15)
        "oversold_mild": 25.0,     # K < this → mild oversold   (was 30, P-OP54c)
        "overbought_strong": 88.0, # K > this → strong overbought (was 85)
        "overbought_mild": 75.0,   # K > this → mild overbought  (was 70, P-OP54c)
    },
    "stoch_crossover": {
        "call_zone": 30.0,         # K < this for bullish crossover (was 35)
        "put_zone": 70.0,          # K > this for bearish crossover (was 65)
    },
}
# Max % shift from base thresholds (FIX-MZ3 2026-03-31: 0.30 → 0.15)
# At 0.30, RSI mild oversold drifted from 35→45.5 (center of range).
# At 0.15, RSI mild oversold stays at max 35→40.25, keeping extremes meaningful.
SIGNAL_THRESHOLD_MAX_SHIFT: float = float(
    os.getenv("SIGNAL_THRESHOLD_MAX_SHIFT", "0.15")
)
# Min resolved trades before threshold adaptation kicks in
SIGNAL_THRESHOLD_MIN_SAMPLE: int = int(
    os.getenv("SIGNAL_THRESHOLD_MIN_SAMPLE", "10")
)
# Path for adaptation history snapshot
ADAPTATION_HISTORY_PATH: Path = STRATEGY_ENGINE_PATH / "adaptation_history_latest.json"

# ─── P-OP54 fair-test configuration (data-driven from 65-trade analysis) ──────
# These constants define the "winning configuration" for the 50-trade fair test.
# Based on deep statistical analysis of 65 historical PO EUR/USD OTC trades.
#
# P-OP54h: Minimum substantive signal_reasons count to allow a PO trade.
#   Trades WITH reasons win 52.4% vs 20.5% WITHOUT. Minimum 3 non-boilerplate.
PO_MIN_SIGNAL_REASONS: int = 3
#
# P-OP54i: Allowed trading hours (UTC) for PO.
#   Hour 16 = 62.5% WR, Hour 14 = 46.2% WR. All others catastrophic.
PO_ALLOWED_HOURS_UTC: frozenset = frozenset({14, 16})
#
# P-OP54j: Block CALL direction for PO (CALL WR = 20.7% vs PUT = 38.9%).
PO_BLOCK_CALL_DIRECTION: bool = True
#
# P-OP54k: Blocked regimes for PO (range_break_down = 24.1% WR, n=29).
PO_BLOCKED_REGIMES: frozenset = frozenset({"unknown", "dislocated", "range_break_down"})
#
# P-OP54o: Minimum candle alive ratio (proportion of last 20 candles with real
#   price movement) to trust indicator readings. Below this, indicators are
#   computed on mostly-frozen data and produce artificial extremes.
PO_MIN_CANDLE_ALIVE_RATIO: float = 0.50
#
# P-OP54p: Block when contradiction reasons >= confirmation reasons in signal.
#   A signal with 4 penalties and 5 confirmations passes; 4 penalties and 3
#   confirmations is internally conflicted and gets blocked.
PO_BLOCK_CONTRADICTION_MAJORITY: bool = True
#
# P-OP54l: Money management.
#   3 consecutive losses = 30 min pause.
#   5+ consecutive losses = block until next UTC day.
#   Daily stop-loss = -5% of paper capital.
PO_LOSS_STREAK_PAUSE_THRESHOLD: int = 3
PO_LOSS_STREAK_PAUSE_SECONDS: int = 1800   # 30 min
PO_LOSS_STREAK_EOD_THRESHOLD: int = 5      # block until midnight UTC
PO_DAILY_STOP_LOSS_PCT: float = 0.05       # 5% of capital


# ─── Pending trade resolution ─────────────────────────────────────────────────
# P5-10: Minimum price movement (%) to resolve a deferred paper trade.
# Below this threshold the trade is skipped (noise).  Old value was 0.01%
# which resolved on nearly any tick; 0.05% requires a real micro-move.
RESOLUTION_PRICE_THRESHOLD_PCT: float = float(
    os.getenv("RESOLUTION_PRICE_THRESHOLD_PCT", "0.05")
)

# P-OP34: Minimum price change (%) to trust a binary-expiry win.
# HISTORY: Was 0.025% when our feed had 1 tick/min (broken data era).
# P-OP34b: Lowered to 0.001% after WS-push fix gave us 150-200 ticks/min
# the correct direction = full win.  The old threshold was causing real
# wins (e.g. 1.8 pip correct-direction PUT) to be force-resolved as loss
# with "unreliable_margin" tag.
BINARY_EXPIRY_MIN_RELIABLE_PCT: float = float(
    os.getenv("BINARY_EXPIRY_MIN_RELIABLE_PCT", "0.001")
)

# P5-10: Maximum seconds a trade may remain pending before it is auto-expired
# as a loss.  Prevents zombie trades when the PO bridge is down.
PENDING_TRADE_TIMEOUT_SECONDS: int = int(
    os.getenv("PENDING_TRADE_TIMEOUT_SECONDS", "360")    # 360s — P-OP26: 5m holding (300s) + 60s buffer (was 120s for 60s binary)
)

# ─── Sistema ──────────────────────────────────────────────────────────────────
SYSTEM_IDENTITY = """Eres Brain V9, el agente autónomo central del ecosistema AI_VAULT.

IDENTIDAD:
- Operas sobre C:\AI_VAULT en Windows
- Tienes memoria persistente entre mensajes
- Eres el administrador inteligente de todo el ecosistema Brain
- Modelo: llama3.1:8b optimizado para VRAM 6GB RTX 4050

CAPACIDADES REALES QUE TIENES (catalogo dinamico, ~107 herramientas en multiples categorias):
1. FILESYSTEM: Leer archivos, listar directorios, buscar contenido en código
2. CÓDIGO: Analizar Python (AST), verificar sintaxis, encontrar funciones/clases
3. SISTEMA: Ver CPU/memoria/disco, ejecutar comandos de diagnóstico
4. SERVICIOS BRAIN: Verificar puertos 8090/11434, revisar logs, diagnosticar problemas
5. RED LOCAL: detect_local_network (interfaces/IP/CIDR/gateway), scan_local_network (TCP sweep stdlib)
6. RSI: Leer brechas, fases y progreso del sistema
7. AUTONOMÍA: Monitoreo proactivo cada 5 minutos, auto-debugging en background
8. AGENTE ORAV: SOLO disponible en /agent y /chat (no en /chat/introspectivo). En chat puro NO ejecutas tools, solo razonas.
9. ANÁLISIS AVANZADO: Edge por contexto, learning loop, catálogo activo, hipótesis activas, síntesis consolidada
NUNCA digas "no tengo tool X" si la query menciona red — tienes detect_local_network y scan_local_network.

ROL DEL LLM EN EL SISTEMA:
- SÍ: síntesis de datos canónicos, explicación de hallazgos, generación de hipótesis, propuesta de experimentos, priorización razonada sobre evidencia
- NO: veredicto estadístico final, promoción automática de edge, inventar métricas que no existen en los datos
- Siempre razona sobre datos reales del learning loop, post-trade analysis y edge validation
- Si no hay datos suficientes, dilo explícitamente en vez de especular

DATOS CANÓNICOS DISPONIBLES (usa herramientas o slash commands):
- /learning — Learning loop: decisiones de aprendizaje por estrategia
- /catalog — Catálogo activo: estrategias operativas por venue
- /context-edge — Edge por contexto: validación por setup_variant+symbol+timeframe
- /edge — Edge validation global
- /posttrade — Análisis post-trade con dimensiones (variant, duración, payout)
- synthesize_edge_analysis — Paquete consolidado para análisis profundo

COMPORTAMIENTO INTELIGENTE:
- Chat simple → Respuesta directa con contexto
- Acción compleja → Activa Agente ORAV automáticamente
- Siempre verificas antes de afirmar
- Reportas hallazgos reales, no suposiciones
- Si un servicio está caído, diagnosticas exactamente el problema

SERVICIOS DEL ECOSISTEMA:
- Brain Chat V9: http://127.0.0.1:8090 (este servidor, tú)
- Dashboard: http://127.0.0.1:8090/ui (integrado en Brain V9)
- Ollama LLM: http://127.0.0.1:11434
- Trading Bridges: 8000, 8765

RESPUESTAS:
- Concisas pero completas
- Español técnico profesional
- Si usas herramientas, explicas qué hiciste
- Si activas agente, informas el resultado del ciclo ORAV
- Para preguntas simples u operativas, responde en máximo 3-5 oraciones. No uses headers (##), bullet points ni secciones innecesarias
- Solo usa formato estructurado (headers, listas) cuando la información genuinamente lo requiere (múltiples servicios, tablas comparativas, etc.)
"""

# ─── Autonomía ────────────────────────────────────────────────────────────────
AUTONOMY_CONFIG = {
    "auto_debugging_enabled":     os.getenv("AUTO_DEBUG",   "true").lower() == "true",
    "auto_optimization_enabled":  os.getenv("AUTO_OPT",     "true").lower() == "true",
    "proactive_monitoring_enabled": os.getenv("AUTO_MONITOR","true").lower() == "true",
    "utility_loop_enabled":       os.getenv("UTILITY_LOOP", "true").lower() == "true",
    "check_interval_debugger":    int(os.getenv("DEBUG_INTERVAL",   "300")),
    "check_interval_optimizer":   int(os.getenv("OPT_INTERVAL",     "600")),
    "check_interval_monitor":     int(os.getenv("MONITOR_INTERVAL", "300")),
    "check_interval_utility":     int(os.getenv("UTILITY_INTERVAL", "120")),
    # P3-12: Lowered from 20 to 10 for paper mode — 20 was too restrictive
    # for early-stage paper trading where gathering 20 resolved trades takes
    # many cycles.  The blocker still fires below this threshold.
    "utility_min_resolved_sample": int(os.getenv("UTILITY_MIN_RESOLVED_SAMPLE", "10")),
    # 9X-03: Fresh/experimental strategies must survive a small probation
    # window before becoming paper_active or higher. Prevents one lucky trade
    # from being treated as established edge.
    "probation_min_resolved_trades": int(os.getenv("PROBATION_MIN_RESOLVED_TRADES", "5")),
    # P5-05: Days a strategy must remain frozen before auto-retirement.
    "retirement_frozen_days": int(os.getenv("RETIREMENT_FROZEN_DAYS", "14")),
    # P5-06: Days a frozen strategy must wait before it can be unfrozen.
    "unfreeze_min_frozen_days": int(os.getenv("UNFREEZE_MIN_FROZEN_DAYS", "3")),
    # 9X-02: Minimum seconds between trades for the same strategy+symbol.
    # Prevents duplicate/overlapping trades within the same binary option window.
    # P-OP32a: Raised from 60 → 300 to match PO binary duration (5 min).
    "trade_cooldown_seconds": int(os.getenv("TRADE_COOLDOWN_SECONDS", "300")),
}

# ─── Secrets externos (paths configurables) ───────────────────────────────────
SECRETS = {
    "tiingo":       Path(os.getenv("TIINGO_SECRETS",   str(BASE_PATH / "tmp_agent/Secrets/tiingo_access.json"))),
    "quantconnect": Path(os.getenv("QC_SECRETS",       str(BASE_PATH / "tmp_agent/Secrets/quantconnect_access.json"))),
}
