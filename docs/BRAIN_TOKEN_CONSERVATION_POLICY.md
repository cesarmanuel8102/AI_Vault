# Brain Token Conservation Policy

Updated: 2026-06-12T22:37:56.962823+00:00

## Purpose

Brain must reduce token waste while preserving evidence, safety and operator clarity.

## Policy

- Max prompt size per autonomy cycle: 1200 characters by default.
- Max response size per Brain cycle: 1200 characters by default.
- Use compact summaries for console output.
- Store evidence in files, not repeated console logs.
- Capture only error tails unless full logs are explicitly required.
- Prefer JSONL event summaries for cycle telemetry.
- Produce concise executive Markdown reports for Cesar.
- Do not duplicate long context already present in evidence artifacts.

## Runtime Contract

- `compact_mode` is enabled by default.
- `raw_log_dump_default` is disabled.
- Every cycle result must link evidence paths instead of copying full logs.
- Provider prompts must be decision-oriented and compressed.
