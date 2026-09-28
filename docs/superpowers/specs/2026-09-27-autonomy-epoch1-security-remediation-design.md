# AUTONOMY_EPOCH_1 Security Remediation Design

Date: 2026-09-27
Status: Owner mandate approved for autonomous implementation
Base commit: `c45421e7539fd63931096904cf4c0051b09c7800`
Branch: `codex/autonomy-epoch1-security-remediation`

## Purpose

Preserve the broad research autonomy introduced by `AUTONOMY_EPOCH_1` while
making broker, credential, kernel, database, process, and network boundaries
structural. Research code remains model-authored and persistent, but it runs in
an isolated worker that cannot inherit Owner authority or contact IBKR.

The remediation also makes stale-lock recovery explicit, introduces truthful
epoch semantics without deleting history, completes first-process research
continuity, derives the execution-kernel manifest, corrects epoch provenance,
and removes stale market PASS reuse.

PAPER remains unarmed throughout remediation. The finalizer and production
experiment are not run.

## Architectural Decision

Use a host-mediated WSL2 research worker as the primary sandbox.

The host validates a typed request, creates a per-run exchange directory under
the autonomy workspace, and invokes a trusted Linux launcher in Ubuntu. The
launcher creates user, mount, PID, and network namespaces. It constructs a
private root, exposes only a read-only trusted worker plus the designated
workspace and scratch mounts, removes Windows drive mounts from the worker's
view, drops capabilities, sets `no_new_privs`, applies resource limits, and
installs a seccomp deny policy before executing model code in-process.

The network namespace has no external interface and loopback remains down.
Seccomp also denies socket creation, process creation, `execve`/`execveat`,
mount operations, ptrace, and namespace changes. Generated code therefore
cannot reach IBKR, invoke host tools, create child processes, or recover host
filesystem access even when it imports `ctypes` or uses absolute paths.

### Alternatives Rejected

- Removing `PATH`, `python -I`, source scanning, and import filtering are only
  language-level controls and were already bypassed.
- A Windows restricted token plus ordinary firewall rules does not provide a
  reliable loopback boundary on this host.
- AppContainer could provide comparable isolation, but requires a separately
  ACLed Python runtime and substantially more fragile native process-launch
  code. WSL2 namespaces are present and runtime-proven on this host.
- Docker would provide a suitable boundary, but the Docker daemon is not
  running and must not become a hidden experiment prerequisite.

If WSL2 isolation cannot be established or verified, `RUN_RESEARCH_SCRIPT`
returns `SANDBOX_UNAVAILABLE`; it never falls back to Owner-context Python.

## Research Worker Contract

The host-side broker accepts only:

- a workspace-relative Python script under `tools/`;
- a bounded list of string arguments;
- cycle identity;
- timeout and resource limits within fixed maxima.

It returns a structured record containing status, return code, stdout, stderr,
elapsed time, peak resource usage when available, script hash, produced
artifact paths and hashes, and a stable failure reason.

The worker may read and write only the mounted autonomy workspace and scratch
directory. Host code revalidates every returned artifact path and hash before
adding it to the append-only registry. A timeout kills the Linux process group.

The workspace registry becomes genuinely hash chained. Reads verify current
content against the latest registered hash. Malformed or truncated tails are
reported, not silently ignored. Existing valid V1 records remain readable and
new V2 records chain from a migration anchor.

## QuantConnect Mediation

`QUANTCONNECT` becomes a typed host operation rather than a status-only tool.
Supported operations are status, selected local backtests/research, approved
historical-data operations, and report inspection. Each operation maps to a
fixed argument builder; raw command arrays are not accepted.

LIVE commands, brokerage configuration, credential output, arbitrary paths,
and shell metacharacters are rejected before process creation. Output is
bounded and redacted. Results use `RUNTIME_AVAILABLE`,
`OPTIONAL_UNAVAILABLE`, `FAILED`, or `UNAUTHORIZED_OPERATION`. Failure never
blocks the core PAPER experiment.

## Execution Lock Recovery

Introduce a read-only inspection result with `FREE`, `ACTIVE`, `STALE`, or
`AMBIGUOUS`. Staleness requires all of:

1. the named mutex can be acquired without abandonment ambiguity;
2. the recorded process identity is absent, including start-time comparison;
3. heartbeat age exceeds the configured threshold;
4. no matching authorized execution process is observed;
5. the DB projection and event history agree.

Recovery uses the already-acquired named mutex as the serialization boundary.
Within one DB transaction it appends a recovery event and changes the old
generation to `RECOVERY_REQUIRED`. The same mutex handle is then used to
acquire the next generation, preventing a second recovery winner. Ambiguous
evidence fails closed. The old generation can no longer heartbeat or release.

The production orphan is proved using a read-only inspection first. A separate
safe proof operates on a copied database and a unique test mutex; canonical
runtime state is not mutated during remediation.

## Epoch And Historical State

Existing launch, cycle, and research records remain immutable historical
evidence. A new `experiment_epochs` projection and append-only epoch events
identify `AUTONOMY_EPOCH_1` with a truthful Monday start and 30-day horizon.
Legacy records are associated with a `PRE_EPOCH_HISTORY` namespace without
rewriting their timestamps or payloads.

Authorization, clock, ledger, cycle counters, and terminal-equity horizon are
bound to the epoch identifier. Rebaselining is an explicit Owner-authorized
administrative operation; remediation implements and tests it but does not
activate the epoch or arm PAPER.

## First Codex Bootstrap

The first invocation of each service process receives a bounded bootstrap
object containing epoch identity, remaining horizon, execution constraints,
PAPER identity class, capital/subledger, current broker state, gates, recent
accepted decisions, open research questions, hypotheses, recent workspace
artifacts, tool manifest, QuantConnect status, and a direct distinction between
research authority and order authority.

Continuity uses deterministic recency and size bounds. Model-authored content
is labelled untrusted. Historical development and audit files are never
automatically included. Subsequent turns retain the existing in-cycle history.

## Derived Kernel Manifest

Replace the manually curated tuple with a deterministic authority-closure
builder. Roots are the scheduled PowerShell entrypoint, Day 1 launcher,
finalizer, executor, broker identity/routing, risk/capital, authorization,
kill switch, lock, market gates, ledger, reconciliation, persistence, and
runtime dispatch.

Python imports are parsed with `ast`; relative imports are resolved inside the
package. PowerShell call edges and explicitly dynamic Python dependencies are
declared in a small reviewed root specification. The builder fails on missing,
untracked, out-of-repository, or unhashed authority dependencies. Tests inject
new authority imports and prove they cannot remain outside the manifest.

Research-only modules are excluded unless they influence proposal acceptance,
executor dispatch, or protected state.

## Epoch Manifest Ordering And Hashes

Launch order becomes:

1. identity, authorization, Auditor, market, DB, ledger, and clock gates;
2. safe lock recovery/acquisition;
3. complete kernel verification;
4. construction of the exact model-facing mandate, bootstrap, and tool
   manifest;
5. cryptographic hashing of those exact canonical payloads and all policy and
   receipt bytes;
6. `EPOCH_MANIFEST_CREATED` evidence;
7. service construction and successful initial safety check;
8. `EPOCH_STARTED` evidence;
9. service loop.

The epoch manifest cannot certify service start. Authorization stores a receipt
SHA-256, not an event UUID. Risk policy has its own canonical hash. Optional
capabilities are recorded honestly and never treated as launch gates.

## Market Gate And Scheduler

The PowerShell wrapper never reuses an undated PASS. Scheduled execution always
collects fresh session evidence. A future bounded reuse path would require an
explicit session identity, maximum age, policy hash, account hash, and epoch
binding; this remediation does not need that optimization.

Scheduler validation gains a non-mutating dry-run that verifies the expected
task action, canonical repository, approved HEAD, working directory behavior,
PAPER endpoint, kernel manifest, and lock state. Task overlap remains
`IgnoreNew`, backed by the named mutex. Production task mutation and
re-enablement remain deferred to the Owner after external re-audit.

## Finalizer Decomposition

Separate read-only prerequisite checking from privileged provisioning,
receipt generation, and activation. The existing finalizer remains compatible
but delegates to explicit stages. Activation requires a separate flag and is
never implied by provisioning or receipt refresh. Dry-run reports every
planned mutation and performs none.

## Runtime Provenance

Startup verifies that every importable production module resolves to a tracked
file at the approved commit or to explicitly authorized immutable deployment
material. Runtime state, evidence, Owner configuration, secrets, tests, caches,
and source are classified separately. Untracked Python under the production
package blocks launch.

## Testing And Evidence

Testing follows TDD and includes:

- actual worker attempts against repo, `.git`, Secrets, SQLite, absolute and
  UNC/device paths, symlinks, junction-like paths, environment and user stores;
- socket attempts against PAPER, LIVE, arbitrary localhost, DNS, and external
  TCP/HTTP;
- process attempts for shells, Git, Codex, Lean, registry discovery, and
  arbitrary absolute executables;
- lock races, PID reuse, stale heartbeats, held mutexes, recovery interruption,
  reboot state, and generation exclusivity;
- bootstrap continuity bounds and untrusted-content labelling;
- authority-closure completeness and hash verification;
- epoch hash correctness and launch ordering;
- stale market PASS rejection and scheduler dry-run;
- full tracked and operational suites, PowerShell AST and `git diff --check`.

No test may submit, cancel, modify, or globally cancel an IBKR order. Current
broker state may be inspected read-only. PAPER remains unarmed.

## Success Criteria

- Research worker cannot access broker networking, host credentials, source,
  kernel, authoritative DB, host shells, or arbitrary executables.
- Self-tooling, persistence, bounded continuity, and mediated QuantConnect are
  available without execution authority.
- Stale-lock recovery is race-safe and runtime-proven without touching the
  canonical production lock.
- Monday can be represented as a truthful new epoch without deleting history.
- Kernel and epoch manifests cover and hash the actual authority surfaces.
- Scheduled launch remains frozen or blocked until an independent adversarial
  re-audit approves deployment.
