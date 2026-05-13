"""
META_COGNITION_L2.PY - Metacognicion de Segundo Orden
Pensamiento sobre el propio pensamiento: calibracion, sesgos, contrafactuales.
"""
import json
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

L2_DIR = Path("C:/AI_VAULT/tmp_agent/state/meta_cognition_l2")
L2_DIR.mkdir(parents=True, exist_ok=True)
CALIB_FILE = L2_DIR / "calibration.json"
BIAS_FILE = L2_DIR / "biases.json"
COUNTER_FILE = L2_DIR / "counterfactuals.json"


@dataclass
class CalibrationPoint:
    bin_low: float       # rango de confianza declarada (ej 0.7)
    bin_high: float
    n_predictions: int = 0
    n_correct: int = 0

    @property
    def accuracy(self) -> float:
        return self.n_correct / max(1, self.n_predictions)

    @property
    def expected(self) -> float:
        return (self.bin_low + self.bin_high) / 2

    @property
    def calibration_error(self) -> float:
        return abs(self.expected - self.accuracy)


@dataclass
class CognitiveBias:
    name: str
    description: str
    detected_count: int = 0
    last_detected: Optional[str] = None
    severity: float = 0.0  # 0..1


@dataclass
class Counterfactual:
    cf_id: str
    original_decision: str
    alternative: str
    predicted_alt_outcome: str
    plausibility: float
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


class MetaCognitionL2:
    """Razonamiento sobre el propio razonamiento."""

    BIAS_CATALOG = {
        "overconfidence": "Exceso de confianza vs precision real",
        "anchoring": "Sesgo de anclaje en valores iniciales",
        "confirmation": "Buscar solo evidencia que confirma hipotesis",
        "availability": "Sobrevalorar lo reciente o memorable",
        "sunk_cost": "Continuar por costo invertido en lugar de utilidad futura",
        "base_rate_neglect": "Ignorar tasas base al evaluar probabilidades",
    }

    def __init__(self):
        self.bins: List[CalibrationPoint] = self._init_bins()
        self.biases: Dict[str, CognitiveBias] = self._init_biases()
        self.counterfactuals: List[Counterfactual] = []
        self._load()

    def _init_bins(self) -> List[CalibrationPoint]:
        return [CalibrationPoint(bin_low=i/10, bin_high=(i+1)/10) for i in range(10)]

    def _init_biases(self) -> Dict[str, CognitiveBias]:
        return {name: CognitiveBias(name=name, description=desc)
                for name, desc in self.BIAS_CATALOG.items()}

    def _load(self):
        if CALIB_FILE.exists():
            try:
                data = json.loads(CALIB_FILE.read_text(encoding="utf-8"))
                self.bins = [CalibrationPoint(**b) for b in data.get("bins", self.bins)]
            except Exception:
                pass
        if BIAS_FILE.exists():
            try:
                data = json.loads(BIAS_FILE.read_text(encoding="utf-8"))
                for name, b in data.get("biases", {}).items():
                    self.biases[name] = CognitiveBias(**b)
            except Exception:
                pass

    def _save(self):
        CALIB_FILE.write_text(json.dumps(
            {"bins": [asdict(b) for b in self.bins]}, indent=2), encoding="utf-8")
        BIAS_FILE.write_text(json.dumps(
            {"biases": {k: asdict(v) for k, v in self.biases.items()}}, indent=2), encoding="utf-8")
        COUNTER_FILE.write_text(json.dumps(
            {"counterfactuals": [asdict(c) for c in self.counterfactuals[-200:]]}, indent=2), encoding="utf-8")

    # --- Calibracion ---
    def record_prediction(self, declared_confidence: float, was_correct: bool):
        """Registra prediccion vs realidad para calibrar confianza."""
        c = max(0.0, min(0.999, declared_confidence))
        idx = int(c * 10)
        b = self.bins[idx]
        b.n_predictions += 1
        if was_correct:
            b.n_correct += 1
        self._save()

    def calibration_error(self) -> float:
        """ECE (Expected Calibration Error) ponderado."""
        total = sum(b.n_predictions for b in self.bins)
        if total == 0:
            return 0.0
        ece = 0.0
        for b in self.bins:
            if b.n_predictions == 0:
                continue
            ece += (b.n_predictions / total) * b.calibration_error
        return ece

    def is_overconfident(self) -> bool:
        """Verdadero si confianza declarada > precision real consistentemente."""
        bias = 0.0
        n = 0
        for b in self.bins:
            if b.n_predictions >= 3:
                bias += (b.expected - b.accuracy)
                n += 1
        return n > 0 and (bias / n) > 0.15

    # --- Deteccion de sesgos ---
    def detect_bias(self, decision_history: List[Dict[str, Any]]) -> Dict[str, float]:
        """Analiza historial buscando sesgos cognitivos."""
        detected = {}
        if not decision_history:
            return detected
        # Overconfidence: confianza alta + outcome malo
        high_conf_failures = sum(
            1 for d in decision_history
            if d.get("confidence_at_decision", 0) > 0.8
            and d.get("actual_consequences") and "fail" in str(d.get("actual_consequences")).lower()
        )
        if high_conf_failures >= 2:
            self._mark_bias("overconfidence", high_conf_failures / 10)
            detected["overconfidence"] = high_conf_failures
        # Confirmation: pocas alternativas consideradas
        avg_alts = sum(len(d.get("alternatives_rejected", [])) for d in decision_history) / len(decision_history)
        if avg_alts < 1.5:
            self._mark_bias("confirmation", 0.4)
            detected["confirmation"] = avg_alts
        # Availability: recencia dominante en reasoning
        recent_refs = sum(
            1 for d in decision_history
            if any("recent" in r.lower() or "last" in r.lower() for r in d.get("reasoning_chain", []))
        )
        if recent_refs > len(decision_history) * 0.4:
            self._mark_bias("availability", recent_refs / len(decision_history))
            detected["availability"] = recent_refs
        # Sunk cost: muchos reintentos sobre mismo objetivo
        from collections import Counter
        targets = Counter(d.get("selected_option", "") for d in decision_history[-50:])
        repeated = sum(1 for _, n in targets.most_common(3) if n > 5)
        if repeated >= 1:
            self._mark_bias("sunk_cost", 0.5)
            detected["sunk_cost"] = repeated
        self._save()
        return detected

    def _mark_bias(self, name: str, severity: float):
        b = self.biases.get(name)
        if not b:
            return
        b.detected_count += 1
        b.last_detected = datetime.now().isoformat()
        b.severity = max(b.severity, min(1.0, severity))

    # --- Contrafactuales ---
    def generate_counterfactual(self, decision: Dict[str, Any]) -> Counterfactual:
        """Genera 'que habria pasado si' para una decision."""
        alternatives = decision.get("alternatives_rejected", [])
        if not alternatives:
            alt_str = "no_action"
        else:
            alt_str = alternatives[0][0] if isinstance(alternatives[0], (list, tuple)) else str(alternatives[0])
        # Plausibilidad basada en confianza original (alta confianza -> baja plausibilidad alterna)
        plausibility = 1.0 - decision.get("confidence_at_decision", 0.5)
        cf = Counterfactual(
            cf_id=f"cf_{datetime.now().strftime('%Y%m%d%H%M%S')}_{len(self.counterfactuals)}",
            original_decision=decision.get("selected_option", "unknown"),
            alternative=alt_str,
            predicted_alt_outcome=self._predict_alt_outcome(alt_str, decision),
            plausibility=plausibility,
        )
        self.counterfactuals.append(cf)
        self._save()
        return cf

    def _predict_alt_outcome(self, alternative: str, original: Dict[str, Any]) -> str:
        """Heuristica simple: alternativas conservadoras -> menor riesgo, menor reward."""
        a = alternative.lower()
        if any(w in a for w in ("no_", "skip", "wait", "abort")):
            return "lower_risk_lower_reward"
        if any(w in a for w in ("aggressive", "force", "all")):
            return "higher_risk_higher_variance"
        return "moderate_outcome_uncertain"

    # --- Reporte ---
    def report(self) -> Dict[str, Any]:
        active_biases = {k: v.severity for k, v in self.biases.items() if v.detected_count > 0}
        return {
            "calibration_error": round(self.calibration_error(), 3),
            "is_overconfident": self.is_overconfident(),
            "active_biases": active_biases,
            "counterfactuals_count": len(self.counterfactuals),
            "bins_with_data": sum(1 for b in self.bins if b.n_predictions > 0),
            "total_predictions": sum(b.n_predictions for b in self.bins),
        }


_L2: Optional[MetaCognitionL2] = None

def get_l2() -> MetaCognitionL2:
    global _L2
    if _L2 is None:
        _L2 = MetaCognitionL2()
    return _L2
