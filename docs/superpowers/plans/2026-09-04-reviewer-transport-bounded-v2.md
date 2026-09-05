# Reviewer Transport Bounded V2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to execute this plan with test-first changes.

**Goal:** Deliver complete immutable reviewer diffs up to 768 KiB through ordered OpenCode attachments, while failing closed above 768 KiB or 16 chunks.

**Architecture:** `reviewManifest()` binds only immutable metadata and the complete-diff hash. `writeReviewAttachments()` calculates UTF-8 bytes, rejects oversized input, splits only at UTF-8 code-point boundaries, rejects more than 16 fragments, and creates deterministic zero-padded files. The reviewer remains no-tool, isolated, exact-base/head bound, and requires its existing strict JSON result.

**Tech Stack:** TypeScript, Node.js `tsx --test`, OpenCode attachment transport.

**Global Constraints:** `MAX_COMPLETE_DIFF_SIZE=768*1024`, `MAX_REVIEW_ATTACHMENT_SIZE=48*1024`, `MAX_DIFF_CHUNKS=16`; no truncation, sampling, summarization, GitHub mutation, scheduler change, canonical sync, trading, or real money.

### Task 1: Red Contract

**Files:**
- Modify: `tests/contract/operator_proxy/opencode_reviewer.test.ts`

- [ ] Add tests whose current implementation fails: a 600 KiB complete diff reaches the model and reassembles byte-exactly; a 768 KiB ASCII diff is accepted only if it fits at most 16 chunks; 768 KiB plus one byte rejects before model invocation; a diff requiring 17 chunks rejects before model invocation; a multibyte diff reassembles byte-exactly; and the manifest contains `COMPLETE_DIFF_SHA256`, `TOTAL_DIFF_BYTES`, `TOTAL_DIFF_CHUNKS`, `CHUNK_SIZE_LIMIT_BYTES`, and ordered numeric filenames.
- [ ] Run: `npx --prefix scripts/operator_proxy tsx --test ../../tests/contract/operator_proxy/opencode_reviewer.test.ts`.
- [ ] Expected before implementation: the 600 KiB and exact-boundary acceptance cases fail with `bounded budget`.

### Task 2: Minimal Bounded Transport

**Files:**
- Modify: `scripts/operator_proxy/opencode_reviewer.ts`

- [ ] Replace the aggregate inline-prompt limit with explicit complete-diff byte, fragment-count, and per-fragment byte checks.
- [ ] Keep all existing error classes and perform rejection before OpenCode invocation.
- [ ] Include the required immutable byte/count/limit fields in the manifest, while retaining the full-diff SHA-256 and numeric chunk ordering.
- [ ] Re-run the focused suite; expected: all existing and new reviewer contracts pass.

### Task 3: Verification and Integration

**Files:**
- Modify: `scripts/operator_proxy/opencode_reviewer.ts`
- Modify: `tests/contract/operator_proxy/opencode_reviewer.test.ts`
- Create: this plan document

- [ ] Run `npm run typecheck` and `npm test` from `scripts/operator_proxy`; capture terminal exit codes.
- [ ] Run `git diff --check`, inspect the three-file scope, and confirm no hard-limit or permission regression.
- [ ] Commit with `fix(operator-proxy): bound large reviewer diff transport`, push normally to the existing PR #277 head branch, wait for exact-head CI, then perform exactly one full-diff DeepSeek Pro review using the repaired backend.
- [ ] Stop at `STATUS: OWNER_AUTHORITY_REQUIRED_NEW_HEAD` after recording new-head CI and DeepSeek receipt evidence; do not merge or install.
