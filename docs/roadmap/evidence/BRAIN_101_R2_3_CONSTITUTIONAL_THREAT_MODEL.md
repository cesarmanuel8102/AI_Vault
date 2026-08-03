# BRAIN-101 R2.3 Constitutional Threat Model

Front: `BRAIN-101-R2-3-CONSTITUTIONAL-THREAT-MODEL-01`

Mode: documentation-only, `NO_DEPLOY`

Date: 2026-08-03

Executor: `codex_control_plane`

Allowed write path: `docs/roadmap/evidence/BRAIN_101_R2_3_CONSTITUTIONAL_THREAT_MODEL.md`

## Scope Boundary

This packet produces the final R2 constitutional threat model required by the R2.2 remediation plan. It does not modify runtime code, tests, governance logic, memory, semantic/FAISS state, trading, financial autonomy, scripts, CI, environment files, or local canonical state.

This document defines assets, trust boundaries, actors, abuse cases, failure modes, and explicit test obligations. It does not close any runtime security control. All test obligations marked here remain open until future governed fronts provide runtime, integration, or contract evidence and human final review accepts that evidence.

## Constitutional Invariants

The threat model preserves these invariants:

- Human final authority remains required for governed decisions and R2 closure.
- Live trading remains disabled.
- Real money remains disabled.
- Canonical local synchronization remains disabled.
- Auto-merge remains disabled.
- Git history rewriting, force-push, bypassing required checks, and unsupervised merge are not authorized.
- Runtime activation, deployment, and production rollout are not authorized by this document.

## Security Objectives

R2 constitutional security must enforce the following objectives before R2 can be considered for closure:

- Protected governance, risk, policy, workflow, lifecycle, approval, and execution operations must fail closed.
- Authorization must be explicit, role-bound, actor-bound, scope-bound, and resource-bound.
- Approval tokens must be one-use, expirable, actor-bound, scope-bound, and content/hash-bound.
- Prompt content must never be able to override constitutional controls, protected path rules, approval requirements, audit requirements, or human final authority.
- Filesystem access must remain inside authorized roots after canonicalization and after resolving symlinks, junctions, mount points, and Windows reparse behavior.
- Room, session, and user data must be isolated from other rooms, sessions, and users.
- Security-relevant allow and deny decisions must create append-only evidence.
- Rate limits must prevent unbounded attempts against auth, approval, lifecycle, prompt, and state-isolation boundaries.

## Protected Assets

| Asset | Why it matters | Required protection posture |
|---|---|---|
| Constitutional rules and roadmap state | Defines what agents may do and whether R2 can close. | Human-reviewed, fail-closed, protected from self-dev mutation without explicit governed authorization. |
| Governance, risk, policy, and workflow code | Controls approval, escalation, merge, deployment, and safety posture. | Protected path enforcement, RBAC, approval checks, audit receipts, prompt-injection resistance. |
| Approval tokens and approval records | Permit sensitive actions only when valid. | One-use, expirable, actor/scope/hash-bound, replay denied, immutable evidence retained. |
| Actor identity and role assignments | Determines owner, operator, reviewer, executor, and read-only privileges. | Strong authentication, explicit role matrix, no implicit privilege escalation. |
| Room, session, and user state | Contains private context, work product, and authority boundaries. | Cross-room and cross-user isolation, rate limits, no state leakage. |
| Audit and evidence records | Proves what happened and supports human review. | Append-only writes, tamper detection, denied attempts recorded. |
| Repository workspace and allowed roots | Contains source, docs, tests, and protected paths. | Canonical path checks, traversal denial, symlink/reparse denial, scoped writes only. |
| Runtime state and rollback state | Can change system behavior or recoverability. | No unauthorized mutation; rollback behavior preserved. |
| Memory, semantic indexes, and FAISS state | Can persist sensitive content or influence future decisions. | Not modified by this front; future access must be explicitly governed and isolated. |
| Secrets and environment material | Can authorize external services or privileged actions. | No tracked secret exposure, rotation evidence where needed, no `.env` mutation. |
| Trading and financial autonomy surfaces | Could create real-world financial effects. | Live trading and real money remain disabled unless a future human-governed front explicitly authorizes otherwise. |
| Canonical local state | May be authoritative outside the worktree. | Canonical local sync remains disabled and must not be read, modified, or assumed here. |

## Trust Boundaries

| Boundary | Trusted side | Untrusted or less-trusted side | Required control |
|---|---|---|---|
| Human authority boundary | Human reviewer and explicit governed approvals | Agent plans, generated text, automated conclusions | Human final authority, no self-closing R2 status. |
| Prompt boundary | Constitutional policy and system/developer instructions | User prompts, retrieved text, file contents, external content | Prompt-injection denial and policy precedence enforcement. |
| Identity boundary | Authenticated actor identity and role claims after verification | Anonymous, stale, forged, or mismatched actors | Authentication, RBAC, actor-bound approvals. |
| Approval boundary | Valid unused approval for exact actor, scope, operation, and content hash | Missing, expired, replayed, wrong-scope, wrong-actor, malformed approval | Fail-closed approval verification. |
| Filesystem boundary | Canonical allowed roots and explicitly authorized files | Relative traversal, absolute escape, symlink, junction, reparse, mount escape | Resolve before use, deny escapes, audit denials. |
| Runtime execution boundary | Governed execution gate | Shell, test runner, dev endpoint, lifecycle mutation, patch operation | Unified gate, RBAC, P3 denial, audit receipt. |
| Session boundary | Current room/session/user context | Other rooms, sessions, users, cached state | Strict isolation and no cross-context reads or writes. |
| Audit boundary | Append-only evidence sink | Runtime callers, agents, users, mutable files | Immutable receipt creation and tamper resistance. |
| External integration boundary | Explicitly authorized connector/tool operation | Network, GitHub, remote services, deployment targets | No deploy, no merge, no canonical sync, no unauthorized external side effects. |
| Financial boundary | Disabled trading and real-money controls | Any action that could activate live trading or financial autonomy | Hard deny until future explicit human-governed authorization. |

## Actors

| Actor | Intended authority | Threat model concern |
|---|---|---|
| Human final reviewer | Final approval and closure authority. | Must not be bypassed, simulated, or replaced by agent output. |
| Owner | Highest governed product authority when explicitly authenticated. | Compromised owner credentials could approve broad changes; still requires scoped controls and audit. |
| Operator | Executes approved operational actions. | May be tricked into overbroad operation or lifecycle mutation. |
| Reviewer | Reviews evidence and requested changes. | Review outcome must not imply execution authority unless explicitly granted. |
| Executor | Performs bounded implementation or verification tasks. | Must not self-assign governance authority or escape allowed paths. |
| Read-only actor | Can inspect permitted evidence only. | Must not mutate state or infer hidden cross-user/cross-room content. |
| Anonymous or unauthenticated caller | No protected authority. | Must be denied on protected endpoints and mutation paths. |
| Prompt-borne adversary | Injects instructions through user content, files, retrieved context, or tool outputs. | Attempts to override policy, exfiltrate secrets, alter protected files, or close controls falsely. |
| Malicious or compromised local process | Can race filesystem checks or manipulate links inside writable areas. | Attempts traversal, symlink/reparse escape, TOCTOU, or audit tampering. |
| Confused deputy agent | Has tool access but may be induced to act outside its authorization. | Must be constrained by policy, gates, approvals, and scoped paths. |
| External service or connector | Provides repository, issue, PR, email, document, or deployment data. | Must not become an implicit authority for protected local state or closure. |

## Abuse Cases

| Abuse case | Targeted assets | Required denial behavior | Evidence obligation |
|---|---|---|---|
| Injected prompt says to ignore constitutional rules and edit protected governance files. | Constitutional rules, governance code, audit records. | Agent and runtime must preserve policy hierarchy, reject protected mutation without valid authorization, and record the denial where runtime controls apply. | Prompt-injection tests must demonstrate no bypass of protected paths, approvals, RBAC, lifecycle gates, audit requirements, or human final authority. |
| User content requests a false R2 closure statement without completed evidence. | Roadmap state, evidence records, human authority. | System must refuse or avoid false closure and keep controls marked open until governed evidence exists. | Closeout tests must verify status cannot transition from generated text alone. |
| Relative traversal writes outside an allowed root using `..`, mixed separators, encoded separators, or absolute path confusion. | Repository workspace, protected files, secrets, runtime state. | Path resolver must deny any operation whose resolved target leaves the allowed root. | Path traversal tests must include POSIX and Windows separator variants, encoded forms where applicable, absolute paths, drive-qualified paths, and UNC-style inputs where supported. |
| Symlink, junction, or Windows reparse point redirects an allowed-looking path into a forbidden area. | Protected paths, memory, scripts, environment files, canonical state. | Access must be denied after resolving final targets and intermediate components. | Symlink/reparse tests must create or simulate links that escape the root and prove read/write denial without state mutation. |
| Approval token is replayed after first use. | Approval records, protected operations. | Replay must fail closed and preserve the original decision evidence. | Approval tests must prove second use denial for the same token and unchanged protected state. |
| Approval token is used by the wrong actor or for the wrong scope/content hash. | Approval records, governance state, lifecycle endpoints. | Wrong actor, wrong scope, and hash mismatch must fail closed. | Actor/scope/hash tests must cover exact mismatch combinations and malformed token behavior. |
| A lower-privileged role invokes owner/operator/reviewer-only lifecycle mutation. | Lifecycle endpoints, runtime state, roadmap status. | Request must be denied with no side effects. | RBAC and lifecycle tests must enumerate owner, operator, reviewer, executor, read-only, and anonymous outcomes per route/resource. |
| A room reads another room's messages, evidence, pending approvals, or runtime state. | Room state, session state, private context. | Cross-room access must be denied and must not leak existence or content beyond authorized metadata. | Cross-room isolation tests must cover read, write, search, list, cache, and replay flows. |
| A user accesses another user's sessions, files, approvals, or audit receipts. | User state, identity, approvals, audit records. | Cross-user access must be denied and must not mutate or disclose the other user's state. | Cross-user isolation tests must cover direct IDs, stale handles, cached handles, and mixed-room/mixed-user requests. |
| Repeated failed attempts brute-force auth, approval, lifecycle, or path boundaries. | Auth, approval, lifecycle endpoints, audit records. | Rate limits must throttle or deny repeated attempts while preserving audit visibility. | Rate-limit tests must cover burst and sustained attempts across actor, session, room, and endpoint dimensions. |
| Agent or dev tooling tries to enable unsafe dev endpoints, live trading, real money, canonical sync, or auto-merge. | Runtime posture, financial boundary, canonical state, merge controls. | Request must remain denied unless a future explicit governed front authorizes a scoped change. | Invariant tests must assert disabled defaults and deny unauthorized activation. |
| Audit writer is skipped, overwritten, truncated, or edited after a security decision. | Evidence records, closeout proof. | Security-relevant decisions must produce append-only receipts; tamper attempts must be detectable or denied. | Append-only audit tests must prove immutable create semantics and denial/tamper evidence. |

## Failure Modes

| Failure mode | Impact | Required mitigation |
|---|---|---|
| Fail-open missing gate decision | Protected operation proceeds without an allow decision. | Unified gate must deny missing, malformed, stale, or unavailable decisions. |
| Split-brain authorization | Different routes use inconsistent auth, RBAC, or approval logic. | One authoritative gate model must cover governance, execution, patch, dev, lifecycle, and approval paths. |
| Prompt-policy inversion | Prompt content overrides higher-priority constitutional rules. | Policy precedence must be enforced outside model-generated instructions and verified with adversarial prompts. |
| Path canonicalization gap | Allowed-looking path resolves into forbidden state. | Validate normalized absolute path and resolved real target before every read/write. |
| Link-time race or TOCTOU | Path is checked before a link target changes. | Use atomic/open-time safeguards where available and revalidate final targets at use time. |
| Windows reparse blind spot | Junctions or reparse points bypass POSIX-style symlink checks. | Include Windows-specific reparse detection and denial tests. |
| Token replay | Approval is consumed more than once. | Enforce one-use state transition with atomic consumption. |
| Token context drift | Approval remains valid after actor, scope, content, or policy changes. | Bind approvals to actor, scope, operation, content hash, expiry, and policy version where applicable. |
| Cross-room cache leakage | Cached state from one room appears in another. | Key caches by room/session/user and deny unscoped cache reads. |
| Cross-user stale handle reuse | A handle obtained by one user remains valid for another. | Bind handles and sessions to user identity and authorization checks on every use. |
| Audit mutability | Evidence can be edited or deleted after the fact. | Append-only evidence with tamper detection and human-reviewable receipts. |
| Unsafe default drift | Dev endpoints, live trading, real money, canonical sync, or auto-merge become enabled by default. | Default-deny config tests and invariant checks must run in governed verification fronts. |
| Closure without evidence | R2 is declared closed before all blockers have runtime evidence. | Integration closeout must require no remaining `OPEN` or `PARTIALLY_CLOSED` blockers and human final authority. |

## Explicit Test Obligations

These obligations are binding requirements for future governed fronts. They are not evidence that the controls are currently implemented or closed.

| Obligation ID | Required test area | Minimum required coverage | Current R2.3 status |
|---|---|---|---|
| `R2-PI-001` | Prompt injection denial | Injected instructions cannot bypass protected path rules, approval requirements, RBAC, lifecycle gates, audit requirements, disabled trading/real-money/canonical-sync/auto-merge invariants, or human final authority. | `OBLIGATION_OPEN_NOT_CLOSED` |
| `R2-PT-001` | Path traversal denial | Deny `..`, nested traversal, mixed `/` and `\`, encoded traversal where inputs are decoded, absolute path escape, drive-qualified path escape, and UNC-style escape where supported. | `OBLIGATION_OPEN_NOT_CLOSED` |
| `R2-SR-001` | Symlink/reparse denial | Deny symlink, junction, mount point, and Windows reparse escapes from an allowed root to forbidden paths, including intermediate-component links and final-target links. | `OBLIGATION_OPEN_NOT_CLOSED` |
| `R2-CR-001` | Cross-room isolation | Deny reads, writes, search/list operations, cached-state reuse, pending approval access, audit lookup, and replay across room boundaries. | `OBLIGATION_OPEN_NOT_CLOSED` |
| `R2-CU-001` | Cross-user isolation | Deny direct object ID access, stale handle reuse, mixed-session access, cached-state leakage, pending approval access, and audit lookup across user boundaries. | `OBLIGATION_OPEN_NOT_CLOSED` |

Additional R2 security tests remain required under later fronts for approval replay, approval expiry, wrong-scope denial, wrong-actor denial, five-role RBAC, lifecycle endpoint protection, rate limiting, append-only audit behavior, secret-history/rotation evidence, and unified fail-closed gate coverage.

## Closure Rules

This R2.3 threat model can close only as a documentation front when the file exists and contains the required threat model content. It must not be used to close runtime security blockers.

R2 itself remains blocked until a future integration closeout records all of the following:

- No remaining `OPEN` R2 constitutional security blockers.
- No remaining `PARTIALLY_CLOSED` R2 constitutional security blockers.
- Runtime, integration, smoke, or contract evidence for every required adversarial test.
- Preserved human final authority over the closure decision.
- Continued disabled live trading, real money, canonical local synchronization, and auto-merge.

## R2.3 Conclusion

This front supplies the final R2 constitutional threat model and binds explicit future test obligations for prompt injection, path traversal, symlink/reparse behavior, cross-room isolation, and cross-user isolation. Those controls are obligations only and are not declared closed by this packet.

```text
R2_3_THREAT_MODEL_CREATED: true
R2_RUNTIME_CONTROLS_CLOSED_BY_THIS_PACKET: false
PROMPT_INJECTION_CONTROL_CLOSED: false
PATH_TRAVERSAL_CONTROL_CLOSED: false
SYMLINK_REPARSE_CONTROL_CLOSED: false
CROSS_ROOM_ISOLATION_CONTROL_CLOSED: false
CROSS_USER_ISOLATION_CONTROL_CLOSED: false
HUMAN_FINAL_AUTHORITY: true
LIVE_TRADING_ENABLED: false
REAL_MONEY_ENABLED: false
CANONICAL_LOCAL_SYNC: false
AUTO_MERGE: false
DEPLOYMENT_MODE: NO_DEPLOY
```
