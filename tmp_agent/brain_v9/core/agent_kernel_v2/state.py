from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
RUN_ROOT = ROOT / "tmp_agent" / "agent_kernel_v2" / "runs"
ARTIFACT_ROOT = ROOT / "tmp_agent" / "agent_kernel_v2"
CANONICAL_AGENT_VERSION = "agent_kernel_v2.0-langgraph-compatible"
RAW_COT_MARKERS = ["chain-of-thought", "hidden reasoning", "private reasoning", "scratchpad"]
FORBIDDEN_PATH_PARTS = [".env", "trading/", "B8/", "tmp_agent/strategies/", "memory/semantic/semantic_memory_faiss", "memory/semantic/semantic_memory.jsonl"]
RUN_ROOT.mkdir(parents=True, exist_ok=True)
