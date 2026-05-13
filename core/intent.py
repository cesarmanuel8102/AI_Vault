"""
Brain Chat V9 — IntentDetector
Extraído de V8.0 líneas 376-588 sin cambios en la lógica.
Detección de intenciones en 3 niveles: keywords → Jaccard → contexto.
"""
import logging
import re
from typing import Dict, List, Tuple

# Diccionario de intenciones (copiado de V8.0 config)
INTENT_SYNONYMS = {
    "QUERY": {
        "keywords": ["consulta","pregunta","duda","información","qué","cómo","cuál","dónde","quién","cuándo","por qué"],
        "patterns":  [r"^qu[eé].*", r"^c[oó]mo.*", r"^cu[aá]l.*", r"^d[oó]nde.*", r"^qui[eé]n.*"],
    },
    "COMMAND": {
        "keywords": ["ejecuta","corre","inicia","detén","para","abre","cierra","crea","elimina","actualiza"],
        "patterns":  [r"^(ejecuta|corre|inicia|det[eé]n|para|abre|cierra)"],
    },
    "ANALYSIS": {
        "keywords": ["analiza","examina","revisa","compara","evalúa","calcula","procesa","diagnostica"],
        "patterns":  [r"^(analiza|examina|revisa|compara|eval[uú]a)"],
    },
    "CREATIVE": {
        "keywords": ["escribe","genera","crea","diseña","inventa","imagina","propón","sugiere"],
        "patterns":  [r"^(escribe|genera|crea|dise[ñn]a|inventa)"],
    },
    "CODE": {
        "keywords": ["código","programa","script","función","clase","método","debug","optimiza"],
        "patterns":  [r"\b(c[oó]digo|programa|script|funci[oó]n|clase)\b"],
    },
    "MEMORY": {
        "keywords": ["recuerda","memoriza","guarda","almacena","recuerdas","olvidaste","mencioné"],
        "patterns":  [r"\b(recuerda|recuerdas|memoriza|guarda|almacena)\b"],
    },
    "SYSTEM": {
        "keywords": ["estado","configura","configuración","ajusta","modifica","cambia","sistema"],
        "patterns":  [r"\b(estado|configura|configuraci[oó]n|ajusta)\b"],
    },
    "CONVERSATION": {
        "keywords": ["hola","adiós","gracias","por favor","disculpa","entendido","ok","vale","claro"],
        "patterns":  [r"^(hola|adi[oó]s|gracias|por favor|disculpa)"],
    },
    "TRADING": {
        "keywords": ["trading","trade","mercado","precio","acción","forex","crypto","rsi","señal","estrategia"],
        "patterns":  [r"\b(trading|trade|mercado|precio|acci[oó]n)\b"],
    },
}


class IntentDetector:
    """
    Detector de intenciones en 3 niveles:
    Nivel 1 — Keywords exactas    (confianza ≥ 0.9)
    Nivel 2 — Similitud Jaccard   (confianza ≥ 0.7)
    Nivel 3 — Contexto historial  (confianza ≥ 0.5)
    """

    def __init__(self):
        self.logger = logging.getLogger("IntentDetector")

    def detect(
        self,
        message: str,
        history: List[Dict] = None,
    ) -> Tuple[str, float, Dict]:
        """
        Retorna (intent_name, confidence, metadata).
        """
        history = history or []
        msg = message.lower().strip()
        results = []

        r1 = self._by_keywords(msg)
        if r1["confidence"] >= 0.9:
            return r1["intent"], r1["confidence"], {"method": "keywords", "matches": r1["matches"]}
        results.append(r1)

        r2 = self._by_jaccard(msg)
        if r2["confidence"] >= 0.7:
            return r2["intent"], r2["confidence"], {"method": "jaccard", "similarity": r2["similarity"]}
        results.append(r2)

        r3 = self._by_context(msg, history)
        if r3["confidence"] >= 0.5:
            return r3["intent"], r3["confidence"], {"method": "context", "match": r3["context_match"]}
        results.append(r3)

        best = max(results, key=lambda x: x["confidence"])
        return best["intent"], best["confidence"], {"method": "fallback"}

    # ── Nivel 1 ───────────────────────────────────────────────────────────────
    def _by_keywords(self, msg: str) -> Dict:
        best_intent, best_conf, matches = "UNKNOWN", 0.0, []
        for name, data in INTENT_SYNONYMS.items():
            kw = [k for k in data["keywords"] if k in msg]
            pt = [p for p in data["patterns"] if re.search(p, msg, re.IGNORECASE)]
            total = len(kw) + len(pt)
            if total > 0:
                conf = min(0.9 + total * 0.05, 0.99)
                if conf > best_conf:
                    best_conf, best_intent, matches = conf, name, kw + pt
        return {"intent": best_intent, "confidence": best_conf, "matches": matches}

    # ── Nivel 2 ───────────────────────────────────────────────────────────────
    def _by_jaccard(self, msg: str) -> Dict:
        tokens = set(re.findall(r"\b\w+\b", msg.lower()))
        best_intent, best_sim = "UNKNOWN", 0.0
        for name, data in INTENT_SYNONYMS.items():
            ref = set()
            for kw in data["keywords"]:
                ref.update(kw.lower().split())
            if not ref:
                continue
            inter = len(tokens & ref)
            union = len(tokens | ref)
            sim   = inter / union if union else 0.0
            if sim > best_sim:
                best_sim, best_intent = sim, name
        conf = min(best_sim * 1.2, 0.89)
        return {"intent": best_intent, "confidence": conf, "similarity": best_sim}

    # ── Nivel 3 ───────────────────────────────────────────────────────────────
    def _by_context(self, msg: str, history: List[Dict]) -> Dict:
        if not history:
            return {"intent": "CONVERSATION", "confidence": 0.5, "context_match": "no_history"}
        recent = []
        for m in history[-3:]:
            content = m.get("content", "").lower()
            for name, data in INTENT_SYNONYMS.items():
                if any(kw in content for kw in data["keywords"][:3]):
                    recent.append(name)
                    break
        if recent:
            dominant = max(set(recent), key=recent.count)
            conf = 0.6 + (recent.count(dominant) / len(recent)) * 0.2
            return {"intent": dominant, "confidence": min(conf, 0.69), "context_match": "continuous"}
        return {"intent": "CONVERSATION", "confidence": 0.5, "context_match": "default"}

    # ── Extras ────────────────────────────────────────────────────────────────
    def extract_entities(self, message: str) -> Dict:
        return {
            "urls":        re.findall(r"https?://[^\s<>\"{}|\\^`\[\]]+", message),
            "emails":      re.findall(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b", message),
            "code_blocks": re.findall(r"```[\s\S]*?```", message),
            "numbers":     re.findall(r"\b\d+(?:\.\d+)?\b", message),
            "mentions":    re.findall(r"@\w+", message),
        }

    def analyze_sentiment(self, message: str) -> Dict:
        pos = ["bien","excelente","genial","perfecto","gracias","me gusta","bueno","feliz"]
        neg = ["mal","error","problema","fallo","no funciona","malo","triste","odio"]
        msg = message.lower()
        pc  = sum(1 for w in pos if w in msg)
        nc  = sum(1 for w in neg if w in msg)
        total = pc + nc
        if total == 0:
            return {"sentiment": "neutral",   "score": 0.5}
        if pc > nc:
            return {"sentiment": "positive",  "score": 0.5 + (pc / total) * 0.5}
        return     {"sentiment": "negative",  "score": 0.5 - (nc / total) * 0.5}
