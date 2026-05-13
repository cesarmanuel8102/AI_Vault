"""
Brain Chat V9 — core/nlp.py
Suite NLP completa extraída de V8.0 líneas 5164-6805.
Contiene: TextNormalizer, ContextManager, ResponseFormatter.
"""
import json
import logging
import re
import unicodedata
from collections import deque
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Union

from brain_v9.core.intent import IntentDetector


# ─── TextNormalizer ───────────────────────────────────────────────────────────
class TextNormalizer:
    """Normaliza texto para NLP: tildes, espacios, idioma, entidades."""

    LANGUAGE_MARKERS = {
        "es": ["el","la","de","que","en","y","a","los","las","un","una","es","son"],
        "en": ["the","is","are","and","of","to","in","that","have","it","for","not"],
        "pt": ["o","a","de","que","em","e","os","as","um","uma","é","são"],
        "fr": ["le","la","de","que","en","et","les","un","une","est","sont"],
    }

    STOPWORDS_ES = {
        "el","la","los","las","un","una","unos","unas","de","del","al","y","o",
        "pero","porque","que","a","ante","bajo","con","contra","desde","durante",
        "en","entre","hacia","hasta","mediante","para","por","según","sin","sobre",
        "tras","es","son","está","están","fue","fueron","ser","estar","tener",
        "este","esta","estos","estas","ese","esa","esos","esas","mi","tu","su",
        "qué","quién","cuándo","dónde","cómo","cuánto",
    }

    def __init__(self):
        self.logger = logging.getLogger("TextNormalizer")
        self.patterns = {
            "symbol":         re.compile(r"\b[A-Z]{1,5}\b"),
            "path_windows":   re.compile(r"[A-Za-z]:\\\S+", re.IGNORECASE),
            "path_unix":      re.compile(r"(?:/\w+)+/?\S*"),
            "number_money":   re.compile(r"\$\d+(?:\.\d+)?|\d+(?:\.\d+)?\s*(?:USD|EUR|GBP|BTC|ETH)"),
            "number_percent": re.compile(r"\d+(?:\.\d+)?%"),
            "number_decimal": re.compile(r"\b\d+(?:\.\d+)?\b"),
            "date_relative":  re.compile(r"\b(hoy|ayer|mañana|próxim[oa]|pasad[oa]|últim[oa])\b", re.IGNORECASE),
            "email":          re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
            "url":            re.compile(r"https?://\S+|www\.\S+"),
            "time_expr":      re.compile(r"\b(?:\d{1,2}:)?\d{1,2}\s*(?:am|pm|hrs?)?\b", re.IGNORECASE),
        }

    def normalize(self, text: str) -> str:
        if not text:
            return ""
        text = unicodedata.normalize("NFKD", str(text))
        text = text.encode("ASCII", "ignore").decode("ASCII")
        text = text.lower()
        text = re.sub(r"\s+", " ", text).strip()
        return text

    def tokenize(self, text: str) -> List[str]:
        return re.sub(r"[^\w\s]", " ", text).lower().split()

    def remove_stopwords(self, tokens: List[str], lang: str = "es") -> List[str]:
        if lang == "es":
            return [t for t in tokens if t not in self.STOPWORDS_ES]
        return tokens

    def detect_language(self, text: str) -> Dict:
        words = re.findall(r"\b\w+\b", text.lower())
        if not words:
            return {"language": "unknown", "confidence": 0.0}
        scores = {
            lang: sum(1 for w in words if w in markers) / len(words)
            for lang, markers in self.LANGUAGE_MARKERS.items()
        }
        best = max(scores, key=scores.get)
        return {"language": best, "confidence": min(scores[best] * 5, 1.0), "scores": scores}

    def compute_similarity(self, t1: str, t2: str) -> float:
        s1 = set(self.tokenize(self.normalize(t1)))
        s2 = set(self.tokenize(self.normalize(t2)))
        if not s1 or not s2:
            return 0.0
        return len(s1 & s2) / len(s1 | s2)

    def extract_entities(self, text: str) -> Dict:
        out: Dict[str, list] = {
            "symbols": [], "paths": [], "numbers": [],
            "dates": [], "emails": [], "urls": [], "times": [],
        }
        for m in self.patterns["symbol"].finditer(text):
            if m.group().isupper():
                out["symbols"].append(m.group())
        for m in self.patterns["path_windows"].finditer(text):
            out["paths"].append({"type": "windows", "value": m.group()})
        for m in self.patterns["path_unix"].finditer(text):
            v = m.group()
            if "/" in v and len(v) > 1:
                out["paths"].append({"type": "unix", "value": v})
        for m in self.patterns["number_money"].finditer(text):
            out["numbers"].append({"type": "money", "value": m.group()})
        for m in self.patterns["number_percent"].finditer(text):
            out["numbers"].append({"type": "percent", "value": m.group()})
        for m in self.patterns["date_relative"].finditer(text):
            out["dates"].append(m.group())
        for m in self.patterns["email"].finditer(text):
            out["emails"].append(m.group())
        for m in self.patterns["url"].finditer(text):
            out["urls"].append(m.group())
        for m in self.patterns["time_expr"].finditer(text):
            out["times"].append(m.group())
        return out


# ─── ContextManager ───────────────────────────────────────────────────────────
class ContextManager:
    """Mantiene historial enriquecido por sesión con metadatos de intención."""

    def __init__(self, max_context: int = 10):
        self.max_context    = max_context
        self.contexts:  Dict[str, deque]     = {}
        self.metadata:  Dict[str, Dict]      = {}
        self.summaries: Dict[str, List[Dict]] = {}
        self.normalizer = TextNormalizer()
        self.intent     = IntentDetector()
        self.logger     = logging.getLogger("ContextManager")

    def add_message(self, session_id: str, role: str, content: str, intent: Optional[str] = None) -> Dict:
        if session_id not in self.contexts:
            self.contexts[session_id]  = deque(maxlen=self.max_context)
            self.metadata[session_id]  = {
                "created_at": datetime.now().isoformat(),
                "message_count": 0, "intents": {},
            }
            self.summaries[session_id] = []

        if intent is None and role == "user":
            history = self.get_context(session_id, n=3)
            intent, confidence, _ = self.intent.detect(content, history)
        else:
            confidence = 1.0

        entities  = self.normalizer.extract_entities(content)
        sentiment = self.intent.analyze_sentiment(content)

        entry = {
            "role": role, "content": content,
            "timestamp": datetime.now().isoformat(),
            "intent": intent, "intent_confidence": confidence,
            "entities": entities, "sentiment": sentiment,
            "message_id": self.metadata[session_id]["message_count"],
        }
        self.contexts[session_id].append(entry)
        self.metadata[session_id]["message_count"] += 1
        if intent:
            d = self.metadata[session_id]["intents"]
            d[intent] = d.get(intent, 0) + 1
        return entry

    def get_context(self, session_id: str, n: int = 5) -> List[Dict]:
        ctx = list(self.contexts.get(session_id, []))
        return ctx[-n:] if len(ctx) > n else ctx

    def get_dominant_intent(self, session_id: str) -> Optional[str]:
        intents = self.metadata.get(session_id, {}).get("intents", {})
        return max(intents, key=intents.get) if intents else None

    def clear(self, session_id: str):
        self.contexts.pop(session_id, None)
        self.metadata.pop(session_id, None)
        self.summaries.pop(session_id, None)

    def get_stats(self, session_id: str) -> Dict:
        meta = self.metadata.get(session_id, {})
        return {
            "session_id":    session_id,
            "message_count": meta.get("message_count", 0),
            "intents":       meta.get("intents", {}),
            "dominant":      self.get_dominant_intent(session_id),
        }


# ─── ResponseFormatter ────────────────────────────────────────────────────────
class ResponseFormatter:
    """Formatea respuestas según perfil: developer o business."""

    def __init__(self):
        self.logger = logging.getLogger("ResponseFormatter")

    def format(self, response: Union[str, Dict], profile: str = "developer", context: Optional[Dict] = None) -> str:
        if profile == "business":
            return self.format_business(response, context)
        return self.format_developer(response, context)

    def format_developer(self, response: Union[str, Dict], context: Optional[Dict] = None) -> str:
        out = []
        if isinstance(response, dict):
            if "error" in response:
                out.append(f"[FAIL] **Error:** `{response['error']}`")
            if "code" in response:
                lang = response.get("language", "python")
                out.append(f"```{lang}\n{response['code']}\n```")
            if "data" in response:
                out.append("**Data:**\n```json\n" + json.dumps(response["data"], indent=2, default=str) + "\n```")
            if "message" in response:
                out.append(response["message"])
        else:
            out.append(str(response))
        return "\n\n".join(out)

    def format_business(self, response: Union[str, Dict], context: Optional[Dict] = None) -> str:
        out = []
        if isinstance(response, dict):
            if "summary" in response:
                out.append(f"**Resumen:** {response['summary']}")
            if "metrics" in response and isinstance(response["metrics"], dict):
                lines = ["**Métricas:**"]
                for name, val in response["metrics"].items():
                    change = val.get("change", "—") if isinstance(val, dict) else "—"
                    v      = val.get("value", val) if isinstance(val, dict) else val
                    lines.append(f"• **{name}:** {v} ({change})")
                out.append("\n".join(lines))
            if "alerts" in response and response["alerts"]:
                lines = ["**Alertas:**"]
                for a in response["alerts"]:
                    lvl = a.get("level","info") if isinstance(a,dict) else "info"
                    msg = a.get("message", str(a))
                    lines.append(f"🚨 **{lvl}:** {msg}")
                out.append("\n".join(lines))
            if "recommendations" in response:
                lines = ["**Recomendaciones:**"]
                for r in response["recommendations"]:
                    lines.append(f"💡 {r}")
                out.append("\n".join(lines))
            if "message" in response:
                out.append(response["message"])
        else:
            out.append(str(response))
        return "\n\n".join(out)

    @staticmethod
    def format_error(error: str, context: str = "") -> str:
        return f"[ERROR] {error}" + (f"\n→ Contexto: {context}" if context else "")

    @staticmethod
    def format_success(message: str) -> str:
        return f"[OK] {message}"
