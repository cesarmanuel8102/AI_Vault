# Operator Proxy Reviewer Router

The production review path is local and fail-closed. `ReviewerRouter` invokes independent Ollama Cloud models through the lossless Node.js/OpenCode JavaScript transport. It never requires `OPENAI_API_KEY` and never grants the reviewer write, shell, network, GitHub-token, merge, or policy authority.

Routing is risk-aware and excludes the known builder model. Low-risk changes use Qwen then GLM; medium/control-plane changes use GLM then Qwen; Agent Loop changes use GLM then Nemotron. A second independent verifier is mandatory. Transport or provider failures use a bounded three-model fallback. P0 findings and material verdict disagreements require a third qualified independent arbiter and always escalate as `BLOCKED`.

The 2026-07-29 five-case qualification admitted GLM 5.2, Qwen 3.5 397B, Nemotron 3 Ultra, and Kimi K2.7 Code at 5/5. DeepSeek V4 Flash (3/5) and DeepSeek V4 Pro (4/5) remain explicitly unqualified and are not used in production routing. Qualification evidence is stored outside the repository under the Operator Proxy qualification root.

Every review is bound to repository, PR, base SHA, head SHA, builder session, and a unique reviewer session. The Router creates a detached temporary worktree, verifies a clean exact HEAD before and after review, injects the complete trusted Git diff, and stores an append-only idempotent receipt. Any write attempt, invalid output, identity mismatch, unavailable reviewer pool, or ambiguous result blocks policy and merge.

The GitHub workflow named `Operator Proxy Codex Supervisor` now validates only the deterministic immutable boundary and uploads a receipt explicitly marked `intelligent_review=false`. It is not an intelligent reviewer and cannot authorize merge. Intelligent review evidence must come from the installed local Router.

`codex_reviewer.ts` remains solely for the one-time bootstrap review of the Router itself through the locally authenticated Codex CLI. It is not the production review dependency.
