# Brain Agent Tool Gateway V2

Tools return structured `{tool_name, ok, blocked, approval_required, error, result}` outcomes. Safe tools include repo status, file read, grep, route probe, semantic retrieve, and allowlisted smoke tests. Write tools are approval-gated and cannot mutate semantic/FAISS, trading, B8, or strategies by default.
