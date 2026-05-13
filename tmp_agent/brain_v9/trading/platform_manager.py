"""
Brain V9 - Platform Manager
Gestiona plataformas de trading de forma independiente (PO e IBKR)
Cada plataforma tiene su propio U score, métricas y seguimiento

P4-03: Aligned U formula with utility.py, switched to state_io, fixed bare excepts.
"""
import logging
import math
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field, asdict
from enum import Enum

import brain_v9.config as _cfg
from brain_v9.core.state_io import read_json, write_json

log = logging.getLogger("PlatformManager")

STATE_PATH = _cfg.BASE_PATH / "tmp_agent" / "state" / "platforms"
STATE_PATH.mkdir(parents=True, exist_ok=True)

# ── U-formula helpers (mirrors utility.py) ────────────────────────────────────

def _squash_signal(value: float, scale: float = 1.0) -> float:
    """tanh squash into [-1, 1], same as utility.py."""
    if scale <= 0:
        scale = 1.0
    return max(-1.0, min(1.0, math.tanh(float(value) / scale)))


def _round(value: float, digits: int = 4) -> float:
    return round(float(value), digits)


# Minimum resolved trades before a platform U can be non-zero.
_MIN_PLATFORM_RESOLVED = 5

class PlatformType(Enum):
    POCKET_OPTION = "pocket_option"
    IBKR = "ibkr"
    INTERNAL = "internal_paper"

@dataclass
class PlatformMetrics:
    """Métricas independientes por plataforma"""
    platform: str
    u_score: float = 0.0
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    total_profit: float = 0.0
    max_drawdown: float = 0.0
    current_drawdown: float = 0.0
    peak_profit: float = 0.0
    largest_loss_streak: int = 0
    current_loss_streak: int = 0
    sharpe_ratio: float = 0.0
    win_rate: float = 0.0
    expectancy: float = 0.0
    sample_quality: float = 0.0
    last_trade_time: Optional[str] = None
    updated_utc: str = field(default_factory=lambda: datetime.now().isoformat())

    def calculate_derived_metrics(self):
        """Calcula métricas derivadas after a new trade is recorded."""
        if self.total_trades > 0:
            self.win_rate = self.winning_trades / self.total_trades
            self.expectancy = self.total_profit / self.total_trades
        # sample_quality ramps from 0→1 over _MIN_PLATFORM_RESOLVED trades
        self.sample_quality = min(1.0, self.total_trades / max(_MIN_PLATFORM_RESOLVED, 1))
        # drawdown tracking
        if self.total_profit > self.peak_profit:
            self.peak_profit = self.total_profit
        self.current_drawdown = max(0.0, self.peak_profit - self.total_profit)
        if self.current_drawdown > self.max_drawdown:
            self.max_drawdown = self.current_drawdown
        self.updated_utc = datetime.now().isoformat()

@dataclass  
class PlatformU:
    """U score independiente por plataforma"""
    platform: str
    u_proxy: float = 0.0
    verdict: str = "no_promote"
    blockers: List[str] = field(default_factory=list)
    history: List[Dict] = field(default_factory=list)
    trend_24h: str = "stable"
    trend_7d: str = "stable"
    updated_utc: str = field(default_factory=lambda: datetime.now().isoformat())
    
    def update(self, new_u: float, reason: str = ""):
        """Actualiza U score con historial"""
        entry = {
            "timestamp": datetime.now().isoformat(),
            "u_score": new_u,
            "reason": reason
        }
        self.history.append(entry)
        # Mantener últimos 1000
        if len(self.history) > 1000:
            self.history = self.history[-1000:]
        
        self.u_proxy = new_u
        self._calculate_trend()
        self._update_verdict()
        self.updated_utc = datetime.now().isoformat()
    
    def _calculate_trend(self):
        """Calcula tendencia de U"""
        if len(self.history) < 2:
            return
        
        recent = self.history[-24:] if len(self.history) >= 24 else self.history
        if len(recent) < 2:
            return
            
        first = recent[0]["u_score"]
        last = recent[-1]["u_score"]
        change = last - first
        
        if abs(change) < 0.01:
            self.trend_24h = "stable"
        else:
            self.trend_24h = "up" if change > 0 else "down"
    
    def _update_verdict(self):
        """Actualiza veredicto basado en U"""
        if self.u_proxy > 0.3:
            self.verdict = "ready_for_promotion"
            self.blockers = []
        elif self.u_proxy > 0:
            self.verdict = "needs_improvement"
            self.blockers = ["u_below_threshold"]
        else:
            self.verdict = "no_promote"
            self.blockers = ["u_proxy_non_positive", "needs_samples"]

class PlatformManager:
    """Gestiona plataformas de trading de forma independiente"""
    
    def __init__(self):
        self.platforms: Dict[str, PlatformType] = {
            "pocket_option": PlatformType.POCKET_OPTION,
            "ibkr": PlatformType.IBKR,
            "internal_paper": PlatformType.INTERNAL
        }
        self._metrics: Dict[str, PlatformMetrics] = {}
        self._u_scores: Dict[str, PlatformU] = {}
        self._load_all()
    
    def _load_all(self):
        """Carga estado de todas las plataformas"""
        for platform in self.platforms.keys():
            self._load_platform(platform)
    
    def _load_platform(self, platform: str):
        """Carga estado de una plataforma"""
        # Métricas
        metrics_file = STATE_PATH / f"{platform}_metrics.json"
        try:
            data = read_json(metrics_file, default=None)
            if data is not None:
                self._metrics[platform] = PlatformMetrics(**data)
            else:
                self._metrics[platform] = PlatformMetrics(platform=platform)
        except Exception:
            log.warning("Failed to load metrics for %s, starting fresh", platform)
            self._metrics[platform] = PlatformMetrics(platform=platform)

        # U score
        u_file = STATE_PATH / f"{platform}_u.json"
        try:
            data = read_json(u_file, default=None)
            if data is not None:
                self._u_scores[platform] = PlatformU(**data)
            else:
                self._u_scores[platform] = PlatformU(platform=platform)
        except Exception:
            log.warning("Failed to load U score for %s, starting fresh", platform)
            self._u_scores[platform] = PlatformU(platform=platform)
    
    def _save_platform(self, platform: str):
        """Guarda estado de una plataforma via state_io (atomic writes)."""
        if platform in self._metrics:
            metrics_file = STATE_PATH / f"{platform}_metrics.json"
            write_json(metrics_file, asdict(self._metrics[platform]))

        if platform in self._u_scores:
            u_file = STATE_PATH / f"{platform}_u.json"
            write_json(u_file, asdict(self._u_scores[platform]))
    
    def get_platform_u(self, platform: str) -> PlatformU:
        """Obtiene U score de una plataforma"""
        if platform not in self._u_scores:
            self._u_scores[platform] = PlatformU(platform=platform)
        return self._u_scores[platform]
    
    def get_platform_metrics(self, platform: str) -> PlatformMetrics:
        """Obtiene métricas de una plataforma"""
        if platform not in self._metrics:
            self._metrics[platform] = PlatformMetrics(platform=platform)
        return self._metrics[platform]
    
    def update_platform_u(self, platform: str, new_u: float, reason: str = ""):
        """Actualiza U score de una plataforma"""
        if platform not in self._u_scores:
            self._u_scores[platform] = PlatformU(platform=platform)
        
        self._u_scores[platform].update(new_u, reason)
        self._save_platform(platform)
    
    def record_trade(self, platform: str, result: str, profit: float, symbol: str = "", strategy: str = ""):
        """Registra un trade en una plataforma específica.

        Args:
            platform: one of "pocket_option", "ibkr", "internal_paper"
            result: "win" or "loss"
            profit: absolute profit amount (positive value). Losses are subtracted internally.
            symbol: instrument symbol (for logging)
            strategy: strategy id (for logging)
        """
        if platform not in self._metrics:
            self._metrics[platform] = PlatformMetrics(platform=platform)

        metrics = self._metrics[platform]
        metrics.total_trades += 1
        metrics.last_trade_time = datetime.now().isoformat()

        if result == "win":
            metrics.winning_trades += 1
            metrics.total_profit += profit
            metrics.current_loss_streak = 0
        elif result == "loss":
            metrics.losing_trades += 1
            metrics.total_profit -= abs(profit)
            metrics.current_loss_streak += 1
            if metrics.current_loss_streak > metrics.largest_loss_streak:
                metrics.largest_loss_streak = metrics.current_loss_streak

        # Recalculate derived metrics (win_rate, expectancy, drawdown, sample_quality)
        metrics.calculate_derived_metrics()

        # Recompute platform U using the aligned formula (mirrors utility.py)
        new_u = self.compute_platform_u(metrics)
        self.update_platform_u(platform, new_u, f"Trade {result}: {symbol}")

        self._save_platform(platform)

    # ── Aligned U formula ─────────────────────────────────────────────────────

    @staticmethod
    def compute_platform_u(metrics: "PlatformMetrics") -> float:
        """Compute platform U using the same structure as utility.py's _compute_components.

        Formula:
            growth_signal  = tanh(expectancy / 3)    ∈ [-1, 1]
            dd_penalty     = clamp(max_drawdown / 0.30, 0, 2)
            tail_penalty   = clamp(largest_loss_streak / 5, 0, 2)
            U = growth_signal - dd_penalty - tail_penalty

        Returns 0.0 if fewer than _MIN_PLATFORM_RESOLVED trades have been recorded.
        """
        if metrics.total_trades < _MIN_PLATFORM_RESOLVED:
            return 0.0

        growth_signal = _squash_signal(metrics.expectancy, 3.0)
        # Use max_drawdown as fraction of peak; default tolerated = 30 %
        peak = max(metrics.peak_profit, 1.0)
        drawdown_fraction = metrics.max_drawdown / peak
        drawdown_penalty = max(0.0, min(2.0, drawdown_fraction / 0.30))
        tail_risk_penalty = max(0.0, min(2.0, metrics.largest_loss_streak / 5.0))

        return _round(growth_signal - drawdown_penalty - tail_risk_penalty)
    
    def get_all_platforms_status(self) -> Dict[str, Any]:
        """Obtiene estado de todas las plataformas"""
        status = {}
        for platform in self.platforms.keys():
            u = self.get_platform_u(platform)
            metrics = self.get_platform_metrics(platform)
            
            status[platform] = {
                "u_score": u.u_proxy,
                "verdict": u.verdict,
                "blockers": u.blockers,
                "trend_24h": u.trend_24h,
                "total_trades": metrics.total_trades,
                "win_rate": metrics.win_rate,
                "total_profit": metrics.total_profit,
                "last_trade": metrics.last_trade_time,
                "sample_quality": metrics.sample_quality
            }
        return status
    
    def get_platform_comparison(self) -> Dict[str, Any]:
        """Compara rendimiento entre plataformas"""
        comparison = {}
        for platform in self.platforms.keys():
            u = self.get_platform_u(platform)
            metrics = self.get_platform_metrics(platform)
            
            comparison[platform] = {
                "u_score": u.u_proxy,
                "rank": 0,  # Se calculará después
                "win_rate": metrics.win_rate,
                "profit": metrics.total_profit,
                "trades": metrics.total_trades,
                "status": "active" if metrics.total_trades > 0 else "idle"
            }
        
        # Calcular ranking
        sorted_platforms = sorted(
            comparison.items(), 
            key=lambda x: x[1]["u_score"], 
            reverse=True
        )
        
        for rank, (platform, _) in enumerate(sorted_platforms, 1):
            comparison[platform]["rank"] = rank
        
        return comparison

# Instancia global
_platform_manager: Optional[PlatformManager] = None

def get_platform_manager() -> PlatformManager:
    """Obtiene instancia singleton del PlatformManager"""
    global _platform_manager
    if _platform_manager is None:
        _platform_manager = PlatformManager()
    return _platform_manager
