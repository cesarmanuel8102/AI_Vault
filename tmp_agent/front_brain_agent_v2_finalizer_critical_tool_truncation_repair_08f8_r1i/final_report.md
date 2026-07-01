# FRONT_BRAIN_AGENT_V2_FINALIZER_CRITICAL_TOOL_TRUNCATION_REPAIR_08F8_R1I

Status: IMPLEMENTED

Root cause: uild_finalizer_prompt() only exposed the first 10 	ool_results. In the live failed run, promotion_queue_status was the 11th result, so Kimi saw it as scheduled/executed but did not see the payload.

Fix: preserve critical diagnostic tools in finalizer prompt even when they occur after generic supporting tools.

Validation:
- py_compile: PASS
- smoke: 11 passed
- no memory/semantic writes
- no FAISS writes
- no trading touched
