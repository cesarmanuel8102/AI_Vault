# Dogfood Agent V2 Runs

## Run 1: Baseline Verification
- **Endpoint:** POST http://127.0.0.1:8091/v2/chat/agent
- **Run ID:** agv2_4e81f46dc2022b4b
- **Message:** "Audit whether Agent V2 is live and canonical. Use repo status, route probes, and memory retrieval if useful."
- **Model:** kimi-k2.6:cloud
- **Provider:** ollama_cloud
- **Provider degraded:** false
- **Latency:** 3589ms
- **Status:** 200 OK
- **Raw CoT exposed:** false
- **Unauthorized writes:** 0
- **Result:** Agent V2 confirmed live and canonical

## Run 2: Final Verification
- **Endpoint:** POST http://127.0.0.1:8091/v2/chat/agent
- **Run ID:** agv2_437724e3f34dc5b8
- **Message:** "Verify Brain Agent V2 is alive and canonical."
- **Model:** kimi-k2.6:cloud
- **Provider:** ollama_cloud
- **Provider degraded:** false
- **Status:** 200 OK
- **Result:** Confirmed operational

## Summary
- **Total runs:** 2
- **Successful:** 2
- **Kimi finalized:** 2
- **Provider degraded:** 0
- **Raw CoT:** 0
- **Unauthorized writes:** 0
