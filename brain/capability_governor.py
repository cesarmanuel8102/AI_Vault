"""
CAPABILITY_GOVERNOR.PY - Gobernanza de capacidades y carencias del Brain

Objetivos:
- Mantener un inventario vivo de tools disponibles.
- Resolver drift entre nombres de tools viejos y actuales.
- Detectar carencias operativas reales desde telemetria y fallos.
- Proponer remediacion segura sin degradar el sistema.
"""
from __future__ import annotations

import json
import platform
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from difflib import get_close_matches
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from core.settings import get_settings


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


@dataclass
class CapabilityIncident:
    requested_tool: str
    reason: str
    resolved_tool: Optional[str] = None
    blocker: bool = True
    install_candidates: List[str] = field(default_factory=list)
    os_packages: List[str] = field(default_factory=list)
    native_alternative: Optional[Dict[str, str]] = None
    evidence: Dict[str, Any] = field(default_factory=dict)
    created_utc: str = field(default_factory=_utc_now)


class CapabilityGovernor:
    """
    Mantiene el estado de capacidades y carencias detectadas.

    No instala nada automaticamente salvo que el caller lo pida explicitamente y
    la configuracion lo permita. El comportamiento por defecto es diagnosticar,
    resolver aliases seguros y preparar remediacion gobernada.
    """

    TOOL_ALIASES: Dict[str, str] = {
        "execute_command": "run_command",
        "analyze_python_file": "analyze_python",
        "get_system_metrics": "get_system_info",
        "check_brain_health": "run_diagnostic",
        "ask_user_for_objective": "request_clarification",
    }

    PACKAGE_HINTS: Dict[str, List[str]] = {
        "chroma": ["chromadb"],
        "faiss": ["faiss-cpu"],
        "psutil": ["psutil"],
        "ib_insync": ["ib-insync"],
        "sklearn": ["scikit-learn"],
        "yaml": ["pyyaml"],
        "bs4": ["beautifulsoup4"],
    }

    # Catalogo semantico: tokens en nombre de tool/intent -> paquetes pip recomendados.
    # Permite identificar que instalar para tools que no existen aun pero cuya
    # intencion es inferible (scrape, pdf, plot, etc.).
    CAPABILITY_CATALOG: Dict[str, List[str]] = {
        # Web scraping / HTTP
        "scrape": ["requests", "beautifulsoup4", "lxml"],
        "scraping": ["requests", "beautifulsoup4", "lxml"],
        "crawl": ["scrapy"],
        "html": ["beautifulsoup4", "lxml"],
        "http": ["requests", "httpx"],
        "fetch_url": ["requests", "httpx"],
        "browser": ["playwright"],
        "selenium": ["selenium"],
        # PDF / docs
        "pdf": ["reportlab", "pypdf"],
        "generate_pdf": ["reportlab"],
        "read_pdf": ["pypdf", "pdfplumber"],
        "docx": ["python-docx"],
        "excel": ["openpyxl", "pandas"],
        "xlsx": ["openpyxl"],
        "csv": ["pandas"],
        # Charts / plots
        "chart": ["matplotlib", "plotly"],
        "plot": ["matplotlib"],
        "plotly": ["plotly", "kaleido"],
        "render_chart": ["plotly", "kaleido"],
        "graph": ["matplotlib", "networkx"],
        # ML / NLP / embeddings
        "embedding": ["sentence-transformers"],
        "transformer": ["transformers"],
        "torch": ["torch"],
        "tensorflow": ["tensorflow"],
        "spacy": ["spacy"],
        "nltk": ["nltk"],
        # Data / numeric
        "numpy": ["numpy"],
        "pandas": ["pandas"],
        "scipy": ["scipy"],
        # Image
        "image": ["pillow"],
        "ocr": ["pytesseract"],
        "cv2": ["opencv-python"],
        # Audio
        "audio": ["pydub", "librosa"],
        "speech": ["speechrecognition"],
        "tts": ["gtts", "pyttsx3"],
        # DB
        "redis": ["redis"],
        "mongo": ["pymongo"],
        "postgres": ["psycopg2-binary"],
        "sqlite": [],  # stdlib
        # Concurrency / async
        "websocket": ["websockets"],
        "celery": ["celery"],
        # Trading / finance
        "yfinance": ["yfinance"],
        "ccxt": ["ccxt"],
        # Misc utility
        "schedule": ["schedule", "apscheduler"],
        "qrcode": ["qrcode"],
        "encrypt": ["cryptography"],
        "git": ["gitpython"],
        "docker": ["docker"],
        "boto3": ["boto3"],
        "azure": ["azure-identity"],
        "google": ["google-cloud-storage"],
        # Network / security (added 2026-04-30)
        "network_scan": ["python-nmap", "scapy"],
        "port_scan": ["python-nmap"],
        "nmap": ["python-nmap"],
        "vuln_scan": ["python-nmap", "vulners"],
        "vulnerability": ["python-nmap", "vulners"],
        "cve": ["vulners"],
        "network_probe": ["scapy", "ping3"],
        "ping": ["ping3"],
        "dns_lookup": ["dnspython"],
        "dns_enum": ["dnspython", "sublist3r"],
        "subdomain": ["sublist3r", "dnspython"],
        "ssh_exec": ["paramiko", "fabric"],
        "ssh": ["paramiko"],
        "shodan": ["shodan"],
        "censys": ["censys"],
        "wireshark": ["pyshark"],
        "packet": ["scapy"],
    }

    # OS-level packages required by certain capabilities. The pip wrapper alone
    # is useless without these (e.g. python-nmap needs the nmap binary; scapy
    # needs Npcap on Windows). Keys are tokens matched against tool/intent.
    # Values map OS family ("windows","linux","darwin") to install hints.
    OS_PACKAGE_HINTS: Dict[str, Dict[str, List[str]]] = {
        "nmap": {
            "windows": ["choco install nmap -y", "winget install -e --id Insecure.Nmap"],
            "linux":   ["sudo apt-get install -y nmap"],
            "darwin":  ["brew install nmap"],
        },
        "network_scan": {
            "windows": ["choco install nmap -y"],
            "linux":   ["sudo apt-get install -y nmap"],
            "darwin":  ["brew install nmap"],
        },
        "port_scan": {
            "windows": ["choco install nmap -y"],
            "linux":   ["sudo apt-get install -y nmap"],
            "darwin":  ["brew install nmap"],
        },
        "vuln_scan": {
            "windows": ["choco install nmap -y"],
            "linux":   ["sudo apt-get install -y nmap"],
            "darwin":  ["brew install nmap"],
        },
        "scapy": {
            "windows": ["winget install -e --id Insecure.Npcap (Npcap requerido para sniffing)"],
            "linux":   ["sudo apt-get install -y libpcap-dev"],
            "darwin":  ["brew install libpcap"],
        },
        "packet": {
            "windows": ["winget install -e --id Insecure.Npcap"],
            "linux":   ["sudo apt-get install -y libpcap-dev"],
            "darwin":  ["brew install libpcap"],
        },
        "wireshark": {
            "windows": ["choco install wireshark -y"],
            "linux":   ["sudo apt-get install -y wireshark tshark"],
            "darwin":  ["brew install wireshark"],
        },
        "ocr": {
            "windows": ["choco install tesseract -y"],
            "linux":   ["sudo apt-get install -y tesseract-ocr"],
            "darwin":  ["brew install tesseract"],
        },
        "browser": {
            "windows": ["python -m playwright install chromium"],
            "linux":   ["python -m playwright install chromium"],
            "darwin":  ["python -m playwright install chromium"],
        },
        "docker": {
            "windows": ["winget install -e --id Docker.DockerDesktop"],
            "linux":   ["curl -fsSL https://get.docker.com | sh"],
            "darwin":  ["brew install --cask docker"],
        },
    }

    # Capabilities that have a NATIVE implementation in agent/tools.py (no
    # install needed). Used to short-circuit install proposals.
    NATIVE_CAPABILITIES: Dict[str, str] = {
        "detect_local_network": "Native stdlib+psutil. No install required.",
        "scan_local_network":   "Native TCP sweep stdlib. No install required.",
        "network_probe":        "Use detect_local_network + scan_local_network.",
        "ping":                 "Use scan_local_network or run_command 'ping'.",
        "dns_lookup":           "Use socket.gethostbyname stdlib via run_command.",
    }

    def __init__(self):
        settings = get_settings()
        self._state_dir = settings.state_path / "capability_governor"
        self._state_dir.mkdir(parents=True, exist_ok=True)
        self._status_path = self._state_dir / "status_latest.json"
        self._incidents_path = self._state_dir / "incidents.jsonl"
        self._tool_inventory: List[str] = []
        self._incidents: List[CapabilityIncident] = []
        self._load()

    def _load(self) -> None:
        try:
            if self._status_path.exists():
                payload = json.loads(self._status_path.read_text(encoding="utf-8"))
                self._tool_inventory = list(payload.get("tool_inventory", []))
        except Exception:
            self._tool_inventory = []

    def register_runtime_tools(self, tool_names: Iterable[str]) -> None:
        incoming = {str(t) for t in tool_names if t}
        self._tool_inventory = sorted(set(self._tool_inventory).union(incoming))
        self._persist()

    def resolve_tool_name(self, requested: str, available_tools: Optional[Iterable[str]] = None) -> Dict[str, Any]:
        requested = (requested or "").strip()
        available = sorted(set(available_tools or self._tool_inventory))
        if not requested:
            return {"ok": False, "reason": "empty_tool_name"}
        if requested in available:
            return {"ok": True, "tool": requested, "resolution": "exact"}

        alias = self.TOOL_ALIASES.get(requested)
        if alias and alias in available:
            return {"ok": True, "tool": alias, "resolution": "alias", "alias_from": requested}

        close = get_close_matches(requested, available, n=3, cutoff=0.55)
        if close:
            return {
                "ok": False,
                "reason": "unknown_tool",
                "suggestions": close,
                "resolution": "fuzzy_suggestions",
            }
        return {"ok": False, "reason": "unknown_tool", "suggestions": []}

    def record_tool_failure(
        self,
        requested_tool: str,
        reason: str,
        *,
        available_tools: Optional[Iterable[str]] = None,
        error: str = "",
    ) -> Dict[str, Any]:
        resolution = self.resolve_tool_name(requested_tool, available_tools)
        resolved_tool = resolution.get("tool") if resolution.get("ok") else None
        install_candidates = self._infer_install_candidates(requested_tool, error)
        os_packages = self._infer_os_packages(requested_tool, error)
        native_alt = self._infer_native_alternative(requested_tool)
        incident = CapabilityIncident(
            requested_tool=requested_tool,
            reason=reason,
            resolved_tool=resolved_tool,
            blocker=resolved_tool is None and native_alt is None,
            install_candidates=install_candidates,
            os_packages=os_packages,
            native_alternative=native_alt,
            evidence={
                "resolution": resolution,
                "error": error[:500],
                "available_tools_count": len(list(available_tools or self._tool_inventory)),
            },
        )
        self._incidents.append(incident)
        self._append_incident(incident)
        self._persist()
        return self._incident_to_report(incident)

    def diagnose_runtime_health(self) -> Dict[str, Any]:
        state_dir = get_settings().state_path
        metrics_path = state_dir / "brain_metrics" / "chat_metrics_latest.json"
        self_test_path = state_dir / "brain_metrics" / "self_test_latest.json"

        chat_metrics: Dict[str, Any] = {}
        self_test: Dict[str, Any] = {}
        try:
            if metrics_path.exists():
                chat_metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
        except Exception:
            chat_metrics = {}
        try:
            if self_test_path.exists():
                self_test = json.loads(self_test_path.read_text(encoding="utf-8"))
        except Exception:
            self_test = {}

        gaps: List[Dict[str, Any]] = []
        avg_latency = float(chat_metrics.get("avg_latency_ms") or 0.0)
        total_conversations = int(chat_metrics.get("total_conversations") or 0)
        tool_fail = int(chat_metrics.get("agent_tool_calls_fail") or 0)
        tool_ok = int(chat_metrics.get("agent_tool_calls_ok") or 0)
        tool_total = tool_ok + tool_fail
        self_test_score = float(self_test.get("score") or 0.0)
        memory_health = self._memory_health()

        if avg_latency and avg_latency > 15000:
            gaps.append({
                "kind": "latency",
                "severity": "high" if avg_latency > 25000 else "medium",
                "description": f"latencia media alta: {avg_latency:.0f}ms",
                "recommended_actions": ["reducir path conversacional lento", "despriorizar providers con timeout"],
            })
        if tool_total >= 5 and tool_fail / max(tool_total, 1) > 0.25:
            gaps.append({
                "kind": "tool_reliability",
                "severity": "medium",
                "description": f"fallos de tools altos: {tool_fail}/{tool_total}",
                "recommended_actions": ["auditar tool registry", "corregir aliases y firmas"],
            })
        if self_test and self_test_score < 0.7:
            gaps.append({
                "kind": "self_test",
                "severity": "high",
                "description": f"self-test bajo: score={self_test_score:.2f}",
                "recommended_actions": ["revisar casos fallidos", "no promover cambios hasta recuperar score"],
            })
        if total_conversations and not self_test:
            gaps.append({
                "kind": "observability",
                "severity": "medium",
                "description": "hay conversaciones pero no snapshot reciente de self-test",
                "recommended_actions": ["ejecutar self-test del chat", "persistir acceptance operacional"],
            })
        episodic_duplicates = int(memory_health.get("episodic", {}).get("duplicate_exact_count") or 0)
        if episodic_duplicates > 0:
            gaps.append({
                "kind": "memory_hygiene",
                "severity": "medium",
                "description": f"memoria episodica con duplicados exactos: {episodic_duplicates}",
                "recommended_actions": ["compactar memoria episodica", "reparar ids y descartar stale duplicates"],
            })

        report = {
            "updated_utc": _utc_now(),
            "tool_inventory_count": len(self._tool_inventory),
            "recent_incident_count": len(self._incidents[-20:]),
            "runtime_gaps": gaps,
            "chat_metrics": {
                "avg_latency_ms": avg_latency,
                "total_conversations": total_conversations,
                "agent_tool_calls_ok": tool_ok,
                "agent_tool_calls_fail": tool_fail,
            },
            "self_test": {
                "score": self_test_score if self_test else None,
                "passed": self_test.get("passed"),
                "failed": self_test.get("failed"),
            },
            "memory_health": memory_health,
        }
        self._persist(extra=report)
        return report

    async def remediate_tool_gap(
        self,
        requested_tool: str,
        *,
        executor: Any = None,
        allow_install: bool = False,
        god_override: bool = False,
    ) -> Dict[str, Any]:
        resolution = self.resolve_tool_name(requested_tool)
        if resolution.get("ok"):
            return {
                "success": True,
                "status": "resolved",
                "requested_tool": requested_tool,
                "resolved_tool": resolution.get("tool"),
                "resolution": resolution.get("resolution"),
            }

        # Antes de proponer instalacion, mira si hay capacidad nativa equivalente
        native_alt = self._infer_native_alternative(requested_tool)
        if native_alt:
            return {
                "success": True,
                "status": "use_native_capability",
                "requested_tool": requested_tool,
                "native_alternative": native_alt,
                "policy": {"install_skipped": "native_capability_available"},
            }

        install_candidates = self._infer_install_candidates(requested_tool, "")
        os_packages = self._infer_os_packages(requested_tool, "")
        settings = get_settings()
        # En GOD MODE el override del usuario PAD anula require_approval
        approval_ok = god_override or (settings.self_dev_enabled and not settings.self_dev_require_approval)
        if (
            allow_install
            and executor is not None
            and approval_ok
            and install_candidates
        ):
            attempts = []
            for package in install_candidates:
                # En god override, pasamos _bypass_gate=True para saltarse el ExecutionGate de install_package (P2)
                result = await executor.execute("install_package", package=package, upgrade=False, _bypass_gate=bool(god_override))
                attempts.append({"package": package, "result": result})
                if isinstance(result, dict) and result.get("success"):
                    return {
                        "success": True,
                        "status": "installed",
                        "requested_tool": requested_tool,
                        "install_candidates": install_candidates,
                        "attempts": attempts,
                        "god_override": bool(god_override),
                    }
            return {
                "success": False,
                "status": "install_attempt_failed",
                "requested_tool": requested_tool,
                "install_candidates": install_candidates,
                "attempts": attempts,
                "god_override": bool(god_override),
            }

        return {
            "success": False,
            "status": "requires_governed_remediation",
            "requested_tool": requested_tool,
            "suggestions": resolution.get("suggestions", []),
            "install_candidates": install_candidates,
            "os_packages": os_packages,
            "os_family": self._current_os(),
            "policy": {
                "self_dev_enabled": settings.self_dev_enabled,
                "self_dev_require_approval": settings.self_dev_require_approval,
                "god_override_available": True,
            },
        }

    def status(self) -> Dict[str, Any]:
        recent = [self._incident_to_report(i) for i in self._incidents[-10:]]
        return {
            "updated_utc": _utc_now(),
            "tool_inventory_count": len(self._tool_inventory),
            "known_aliases": self.TOOL_ALIASES,
            "recent_incidents": recent,
            "self_dev_policy": {
                "enabled": get_settings().self_dev_enabled,
                "require_approval": get_settings().self_dev_require_approval,
                "max_risk": get_settings().self_dev_max_risk,
            },
        }

    def _persist(self, *, extra: Optional[Dict[str, Any]] = None) -> None:
        payload = {
            "updated_utc": _utc_now(),
            "tool_inventory": self._tool_inventory,
            "recent_incidents": [self._incident_to_report(i) for i in self._incidents[-25:]],
        }
        if extra:
            payload.update(extra)
        self._status_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    def _append_incident(self, incident: CapabilityIncident) -> None:
        with self._incidents_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(asdict(incident), ensure_ascii=False) + "\n")

    def _current_os(self) -> str:
        sys_name = platform.system().lower()
        if "windows" in sys_name:
            return "windows"
        if "darwin" in sys_name:
            return "darwin"
        return "linux"

    def _infer_native_alternative(self, requested_tool: str) -> Optional[Dict[str, str]]:
        """Si la capacidad pedida tiene implementacion nativa registrada,
        devuelve un hint para que el orchestrator use la nativa en vez de instalar."""
        lower = requested_tool.lower()
        for cap, note in self.NATIVE_CAPABILITIES.items():
            if cap.lower() in lower or lower in cap.lower():
                return {"capability": cap, "note": note}
        return None

    def _infer_os_packages(self, requested_tool: str, error: str) -> List[str]:
        """Devuelve comandos de instalacion a nivel de SO (choco/winget/apt/brew)
        necesarios para que la capacidad funcione. Filtra por SO actual."""
        lower = f"{requested_tool} {error}".lower()
        os_key = self._current_os()
        cmds: List[str] = []
        seen = set()
        for token, by_os in self.OS_PACKAGE_HINTS.items():
            if token.lower() in lower:
                for cmd in by_os.get(os_key, []):
                    if cmd not in seen:
                        seen.add(cmd)
                        cmds.append(cmd)
        return cmds

    def _extract_missing_binaries(self, error: str) -> List[str]:
        """R27: parse stderr-style errors to extract the name of a missing binary.

        When a tool like run_command fails with stderr containing
        "'nmap' is not recognized" or "nmap: command not found", the requested
        tool is run_command (always present), but the *real* missing capability
        is the binary mentioned in the error. This helper recovers it.
        """
        if not error:
            return []
        import re as _re
        bins: List[str] = []
        seen = set()
        patterns = (
            # Windows: 'nmap' is not recognized
            r"'([A-Za-z0-9_.\-]+)'\s+is\s+not\s+recognized",
            # Windows alt: "nmap" is not recognized
            r'"([A-Za-z0-9_.\-]+)"\s+is\s+not\s+recognized',
            # Unix: nmap: command not found
            r"([A-Za-z0-9_.\-]+):\s*command\s+not\s+found",
            # Unix bash: command not found: nmap
            r"command\s+not\s+found:\s*([A-Za-z0-9_.\-]+)",
            # exec: "nmap": executable file not found
            r'exec:\s*"?([A-Za-z0-9_.\-]+)"?:\s*executable\s+file\s+not\s+found',
            # Generic: No such file or directory: nmap
            r"No\s+such\s+file\s+or\s+directory:\s*([A-Za-z0-9_./\\-]+)",
        )
        for pat in patterns:
            for m in _re.finditer(pat, error):
                name = m.group(1)
                # strip path if present
                if "/" in name or "\\" in name:
                    name = name.replace("\\", "/").rsplit("/", 1)[-1]
                # strip extension
                if name.lower().endswith(".exe"):
                    name = name[:-4]
                name_low = name.lower()
                if name_low and name_low not in seen and len(name_low) > 1:
                    seen.add(name_low)
                    bins.append(name_low)
        return bins

    def _infer_install_candidates(self, requested_tool: str, error: str) -> List[str]:
        """
        Infiere paquetes pip a instalar para resolver una capacidad faltante.
        Combina:
         1. PACKAGE_HINTS (modulos python literales en error/nombre)
         2. CAPABILITY_CATALOG (conceptos semanticos por tokens del nombre del tool)
         3. R27: binarios extraidos de stderr (nmap, git, curl, etc.) mapeados via OS_PACKAGE_HINTS
        """
        lower = f"{requested_tool} {error}".lower()
        # Tokenizacion simple del nombre del tool (snake_case, kebab-case, camelCase)
        import re as _re
        tokens = set(_re.findall(r"[a-z0-9]+", _re.sub(r"([A-Z])", r"_\1", requested_tool).lower()))
        candidates: List[str] = []
        # 1. Module hints literales
        for module_name, packages in self.PACKAGE_HINTS.items():
            if module_name.lower() in lower:
                candidates.extend(packages)
        # 2. Capability catalog por tokens
        for concept, packages in self.CAPABILITY_CATALOG.items():
            concept_low = concept.lower()
            # match exacto de token, o substring del concepto en el nombre completo
            if concept_low in tokens or concept_low in lower:
                candidates.extend(packages)
        # 3. R27: binarios faltantes detectados en stderr
        os_key = self._current_os()
        for missing_bin in self._extract_missing_binaries(error):
            for token, by_os in self.OS_PACKAGE_HINTS.items():
                if token.lower() == missing_bin or missing_bin in token.lower():
                    for cmd in by_os.get(os_key, []):
                        candidates.append(cmd)
        # Filtrar vacios y deduplicar preservando orden de aparicion
        seen = set()
        ordered: List[str] = []
        for c in candidates:
            if c and c not in seen:
                seen.add(c)
                ordered.append(c)
        return ordered

    @staticmethod
    def _memory_health() -> Dict[str, Any]:
        try:
            from brain_v9.core.knowledge import EpisodicMemory
            episodic = EpisodicMemory().get_stats()
        except Exception as exc:
            episodic = {"ok": False, "error": str(exc)}
        try:
            from brain_v9.core.semantic_memory import get_semantic_memory
            semantic = get_semantic_memory()
            if hasattr(semantic, "_memory_stats") and hasattr(semantic, "_read_records"):
                semantic_stats = semantic._memory_stats(semantic._read_records())
            else:
                semantic_stats = semantic.status()
        except Exception as exc:
            semantic_stats = {"ok": False, "error": str(exc)}
        return {
            "episodic": episodic,
            "semantic": semantic_stats,
        }

    @staticmethod
    def _incident_to_report(incident: CapabilityIncident) -> Dict[str, Any]:
        return {
            "requested_tool": incident.requested_tool,
            "reason": incident.reason,
            "resolved_tool": incident.resolved_tool,
            "blocker": incident.blocker,
            "install_candidates": incident.install_candidates,
            "os_packages": incident.os_packages,
            "native_alternative": incident.native_alternative,
            "created_utc": incident.created_utc,
            "evidence": incident.evidence,
        }


_GOVERNOR: Optional[CapabilityGovernor] = None


def get_capability_governor() -> CapabilityGovernor:
    global _GOVERNOR
    if _GOVERNOR is None:
        _GOVERNOR = CapabilityGovernor()
    return _GOVERNOR
