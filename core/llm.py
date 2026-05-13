"""
Brain Chat V9 — LLMManager v2
Seleccion inteligente de modelos con fallback robusto.
Orden: deepseek-r1:14b (GPU) → deepseek-r1:32b → cloud → llama3.1:8b
"""
import asyncio
import logging
import time
from typing import Dict, List, Optional

from aiohttp import ClientSession, ClientTimeout, ClientConnectorError

from brain_v9.config import (
    API_ENDPOINTS, API_KEYS, LLM_CONFIG, SYSTEM_IDENTITY
)

log = logging.getLogger("LLMManager")


# ── Cadenas de fallback por tipo de tarea ─────────────────────────────────────
CHAINS = {
    # Agente / razonamiento complejo
    "agent":    ["deepseek14b", "deepseek32b", "kimi_cloud", "llama8b"],
    # Codigo
    "code":     ["coder14b",    "deepseek14b", "kimi_cloud", "llama8b"],
    # Conversacion
    "chat":     ["deepseek14b", "kimi_cloud",  "llama8b"],
    # Fallback sin internet
    "offline":  ["deepseek14b", "deepseek32b", "llama8b"],
    # Por nombre explicito (desde la UI)
    "ollama":   ["deepseek14b", "deepseek32b", "llama8b"],
    "gpt4":     ["gpt4",        "deepseek14b", "llama8b"],
    "claude":   ["claude",      "deepseek14b", "llama8b"],
}

# ── Definicion de modelos ──────────────────────────────────────────────────────
MODELS = {
    "deepseek14b": {
        "type":    "ollama",
        "model":   "deepseek-r1:14b",
        "timeout": 90,
        "local":   True,
    },
    "deepseek32b": {
        "type":    "ollama",
        "model":   "deepseek-r1:32b",
        "timeout": 180,
        "local":   True,
    },
    "coder14b": {
        "type":    "ollama",
        "model":   "qwen2.5-coder:14b",
        "timeout": 90,
        "local":   True,
    },
    "llama8b": {
        "type":    "ollama",
        "model":   "llama3.1:8b",
        "timeout": 60,
        "local":   True,
    },
    "kimi_cloud": {
        "type":    "ollama",
        "model":   "kimi-k2.5:cloud",
        "timeout": 30,
        "local":   False,   # requiere internet
    },
    "gpt4": {
        "type":    "openai",
        "timeout": 30,
        "local":   False,
    },
    "claude": {
        "type":    "anthropic",
        "timeout": 30,
        "local":   False,
    },
}


class LLMManager:

    def __init__(self):
        self.session: Optional[ClientSession] = None
        self._internet: Optional[bool] = None   # cache de conectividad
        self._internet_checked_at: float = 0
        self.metrics = {
            "total":      0,
            "success":    0,
            "failed":     0,
            "fallbacks":  0,
            "avg_latency": 0.0,
        }

    # ── Sesion HTTP lazy ───────────────────────────────────────────────────────
    async def _get_session(self, timeout: int = 60) -> ClientSession:
        if self.session is None or self.session.closed:
            self.session = ClientSession(
                timeout=ClientTimeout(total=timeout)
            )
        return self.session

    # ── Deteccion de internet (cacheada 60s) ────────────────────────────────────
    async def _has_internet(self) -> bool:
        now = time.time()
        if now - self._internet_checked_at < 60 and self._internet is not None:
            return self._internet
        try:
            s = await self._get_session(5)
            async with s.get(
                "http://ollama.com", allow_redirects=False
            ) as r:
                self._internet = r.status < 500
        except Exception:
            self._internet = False
        self._internet_checked_at = now
        log.debug("Conectividad: %s", "online" if self._internet else "offline")
        return self._internet

    # ── API publica ────────────────────────────────────────────────────────────
    async def query(
        self,
        messages:       List[Dict],
        tools_context:  Optional[Dict] = None,
        model_priority: str = "ollama",
    ) -> Dict:
        """
        Consulta al LLM usando la cadena de fallback adecuada.
        Nunca falla mientras Ollama este corriendo localmente.
        """
        self.metrics["total"] += 1
        start = time.time()

        chain = CHAINS.get(model_priority, CHAINS["ollama"])
        has_net = await self._has_internet()

        last_error = None
        for idx, model_key in enumerate(chain):
            cfg = MODELS.get(model_key)
            if cfg is None:
                continue

            # Saltar modelos cloud si no hay internet
            if not cfg["local"] and not has_net:
                log.debug("Sin internet — saltando %s", model_key)
                continue

            try:
                if idx > 0:
                    self.metrics["fallbacks"] += 1
                    log.info("Fallback a %s (%s)", model_key, cfg.get("model",""))

                result = await self._query_model(
                    cfg, messages, tools_context
                )
                latency = time.time() - start
                self._update_latency(latency)
                self.metrics["success"] += 1
                result["model_key"] = model_key
                result["latency"]   = latency
                result["fallback"]  = idx > 0
                return result

            except asyncio.TimeoutError:
                last_error = f"{model_key}: timeout ({cfg['timeout']}s)"
                log.warning("Timeout en %s", model_key)
            except ClientConnectorError:
                last_error = f"{model_key}: no se puede conectar"
                log.warning("Sin conexion a %s", model_key)
            except Exception as e:
                last_error = f"{model_key}: {e}"
                log.warning("Error en %s: %s", model_key, e)

            # Pequena pausa antes del siguiente modelo
            if idx < len(chain) - 1:
                await asyncio.sleep(0.5)

        self.metrics["failed"] += 1
        return {
            "success": False,
            "error":   last_error or "Todos los modelos fallaron",
            "content": None,
            "response": None,
        }

    # ── Dispatcher de backends ────────────────────────────────────────────────
    async def _query_model(
        self, cfg: Dict, messages: List[Dict],
        tools_context: Optional[Dict]
    ) -> Dict:
        t = cfg["type"]
        if t == "ollama":
            content = await self._ollama(
                cfg["model"], cfg["timeout"], messages, tools_context
            )
        elif t == "openai":
            content = await self._openai(messages, tools_context)
        elif t == "anthropic":
            content = await self._anthropic(messages, tools_context)
        else:
            raise ValueError(f"Tipo desconocido: {t}")

        return {
            "success":  True,
            "content":  content,
            "response": content,
            "model":    cfg.get("model", t),
            "model_used": cfg.get("model", t),
        }

    # ── Ollama ────────────────────────────────────────────────────────────────
    async def _ollama(
        self, model: str, timeout: int,
        messages: List[Dict], tools_context: Optional[Dict]
    ) -> str:
        system = SYSTEM_IDENTITY + self._fmt_tools(tools_context)
        convo  = "\n".join(
            f"{'User' if m['role']=='user' else 'Assistant'}: {m['content']}"
            for m in messages if m.get("role") in ("user", "assistant")
        )
        prompt = f"{system}\n\n{convo}\nAssistant:"

        s = await self._get_session(timeout)
        async with s.post(
            API_ENDPOINTS["ollama"],
            json={
                "model":   model,
                "prompt":  prompt,
                "stream":  False,
                "options": {
                    "temperature": LLM_CONFIG["temperature"],
                    "num_predict": LLM_CONFIG["max_tokens"],
                    "num_ctx":     8192,    # contexto amplio con 64GB RAM
                },
            },
            timeout=ClientTimeout(total=timeout),
        ) as r:
            if r.status != 200:
                raise RuntimeError(f"Ollama HTTP {r.status}")
            data = await r.json()
            resp = data.get("response", "")
            if not resp:
                raise RuntimeError("Ollama devolvio respuesta vacia")
            return resp

    # ── OpenAI ────────────────────────────────────────────────────────────────
    async def _openai(
        self, messages: List[Dict], tools_context: Optional[Dict]
    ) -> str:
        key = API_KEYS.get("openai", "")
        if not key:
            raise ValueError("OPENAI_API_KEY no configurada")
        system = SYSTEM_IDENTITY + self._fmt_tools(tools_context)
        msgs   = [{"role":"system","content":system}] + [
            m for m in messages if m.get("role") in ("user","assistant")
        ]
        s = await self._get_session(30)
        async with s.post(
            API_ENDPOINTS["gpt4"],
            headers={"Authorization":f"Bearer {key}",
                     "Content-Type":"application/json"},
            json={"model":"gpt-4","messages":msgs,
                  "temperature":LLM_CONFIG["temperature"],
                  "max_tokens":LLM_CONFIG["max_tokens"]},
        ) as r:
            if r.status != 200:
                raise RuntimeError(f"OpenAI HTTP {r.status}: {await r.text()}")
            return (await r.json())["choices"][0]["message"]["content"]

    # ── Anthropic ─────────────────────────────────────────────────────────────
    async def _anthropic(
        self, messages: List[Dict], tools_context: Optional[Dict]
    ) -> str:
        key = API_KEYS.get("anthropic", "")
        if not key:
            raise ValueError("ANTHROPIC_API_KEY no configurada")
        system = SYSTEM_IDENTITY + self._fmt_tools(tools_context)
        convo  = [m for m in messages if m.get("role") in ("user","assistant")]
        s = await self._get_session(30)
        async with s.post(
            API_ENDPOINTS["claude"],
            headers={"x-api-key":key,"anthropic-version":"2023-06-01",
                     "Content-Type":"application/json"},
            json={"model":"claude-3-opus-20240229","system":system,
                  "messages":convo,"max_tokens":LLM_CONFIG["max_tokens"],
                  "temperature":LLM_CONFIG["temperature"]},
        ) as r:
            if r.status != 200:
                raise RuntimeError(f"Anthropic HTTP {r.status}: {await r.text()}")
            return (await r.json())["content"][0]["text"]

    # ── Helpers ───────────────────────────────────────────────────────────────
    def _fmt_tools(self, ctx: Optional[Dict]) -> str:
        if not ctx:
            return ""
        parts = ["\nHERRAMIENTAS:"]
        for t in ctx.get("available_tools", []):
            parts.append(f"- {t['name']}: {t.get('description','')}")
        return "\n".join(parts)

    def _update_latency(self, new: float):
        n = self.metrics["success"]
        if n <= 1:
            self.metrics["avg_latency"] = new
        else:
            self.metrics["avg_latency"] = (
                self.metrics["avg_latency"] * (n-1) + new
            ) / n

    def get_metrics(self) -> Dict:
        return self.metrics.copy()

    async def close(self):
        if self.session and not self.session.closed:
            await self.session.close()
