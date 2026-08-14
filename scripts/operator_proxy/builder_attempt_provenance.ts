import {createHash, randomUUID} from "node:crypto";
import {execFileSync} from "node:child_process";
import {appendFileSync, existsSync, lstatSync, mkdirSync, readFileSync, realpathSync, renameSync, rmSync, writeFileSync} from "node:fs";
import {isAbsolute, join} from "node:path";
import type {BuilderInput, BuilderTransport} from "./builder_backend.js";
import {ELIGIBLE_FALLBACK_FAILURES, INELIGIBLE_FALLBACK_FAILURES, scopeViolations} from "./builder_backend.js";
import {safeJson} from "./redaction.js";

export const LEGACY_NEUTRALIZATION_TRAILER = "LEGACY_NEUTRALIZATION";
export const LEGACY_REBUILD_TRAILER = "LEGACY_REBUILD";
export const PRIOR_UNATTESTED_HEAD_TRAILER = "PRIOR_UNATTESTED_HEAD";
export const RESET_BASE_TRAILER = "RESET_BASE";
export const NEUTRALIZATION_HEAD_TRAILER = "NEUTRALIZATION_HEAD";
export const FRESH_BUILDER_HEAD_TRAILER = "FRESH_BUILDER_HEAD";

const SCHEMA_VERSION = 1;
const ALLOWED_BACKENDS: BuilderTransport[] = ["codex_cli_openai", "opencode_github_copilot", "opencode_ollama"];

const safeFront = /^[A-Z0-9][A-Z0-9._-]{5,127}$/;
const safeSha = /^[0-9a-f]{40}$/;
const safeProviderSession = /^[a-z0-9][a-z0-9._:/-]{2,127}$/;
const safeReceiptId = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
const safeModel = /^[a-z0-9][a-z0-9._:/-]{2,127}$/;
const safeBranch = /^[a-z0-9][a-z0-9._/-]{5,160}$/;
const safeFailureClass = /^[A-Z][A-Z0-9_]{2,63}$/;

export type AttemptState = "STARTED" | "COMPLETED" | "FAILED";
export type QuarantineReason = "BUILDER_PROVENANCE_RECOVERY_REQUIRED";
export type ControlPlaneDefectClass = "BUILDER_PROVENANCE_START_WRITE_FAILED" | "BUILDER_PROVENANCE_COMPLETED_WRITE_FAILED" | "BUILDER_PROVENANCE_FAILED_WRITE_FAILED" | "BUILDER_PROVENANCE_ROOT_UNUSABLE";

export interface BuilderCandidateQuarantineEvent {
  schema_version: 1;
  event_id: string;
  state: "QUARANTINED";
  front_id: string;
  issue: number;
  observed_head: string;
  authorized_base_sha: string;
  canonical_worktree: string;
  work_branch: string;
  repair_cycle: number;
  changed_files: string[];
  changed_files_digest: string;
  reason: QuarantineReason;
  created_utc: string;
}

const safeEventId = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

export interface AttemptStartedReceipt {
  schema_version: 1;
  receipt_id: string;
  front_id: string;
  issue: number;
  base_sha: string;
  canonical_worktree: string;
  work_branch: string;
  builder_session: string;
  backend: BuilderTransport;
  model: string;
  provider_correlation_id: string;
  provider_session?: string;
  attempt_number: number;
  repair_cycle: number;
  scope_fingerprint: string;
  state: "STARTED";
  created_utc: string;
}

export interface AttemptCompletedReceipt {
  schema_version: 1;
  receipt_id: string;
  state: "COMPLETED";
  head_sha: string;
  provider_correlation_id: string;
  native_provider_session?: string;
  changed_files: string[];
  completed_utc: string;
}

export interface AttemptFailedReceipt {
  schema_version: 1;
  receipt_id: string;
  state: "FAILED";
  failure_class: string;
  failed_utc: string;
}

export type AttemptReceipt = AttemptStartedReceipt | AttemptCompletedReceipt | AttemptFailedReceipt;

export interface RecoverableStartedAttempt {
  receipt: AttemptStartedReceipt;
  lineIndex: number;
  frontId: string;
}

function operatorProxyRoot(env = process.env): string | undefined {
  const root = env.OPERATOR_PROXY_ROOT;
  if (!root) return undefined;
  if (!isAbsolute(root)) throw new Error("OPERATOR_PROXY_ROOT must be absolute");
  return root;
}

function canonicalPath(path: string): string {
  return realpathSync(path);
}

function validRelativePath(path: string): boolean {
  return !path.includes("..") && !isAbsolute(path) && !path.includes("\\") && path.length > 0;
}

function validatePathScope(paths: string[]): void {
  for (const path of paths) {
    if (!validRelativePath(path)) throw new Error("builder attempt scope path invalid");
  }
}

export function computeScopeFingerprint(baseSha: string, allowedPaths: string[], forbiddenPaths: string[]): string {
  if (!safeSha.test(baseSha)) throw new Error("builder attempt scope base invalid");
  validatePathScope(allowedPaths);
  validatePathScope(forbiddenPaths);
  const canonical = JSON.stringify({
    base_sha: baseSha,
    allowed_paths: [...allowedPaths].sort(),
    forbidden_paths: [...forbiddenPaths].sort(),
  });
  return createHash("sha256").update(canonical).digest("hex");
}

function atomicWrite(path: string, payload: string): void {
  const tmp = `${path}.${process.pid}.tmp`;
  writeFileSync(tmp, payload, {flag: "wx"});
  try {
    renameSync(tmp, path);
  } catch (error) {
    try { rmSync(tmp, {force: true}); } catch {}
    throw error;
  }
}

function safeReadLines(path: string): string[] {
  if (!existsSync(path)) return [];
  const bytes = readFileSync(path, "utf8");
  return bytes.split(/\r?\n/).filter(Boolean);
}

export function readAttemptEvents(frontId: string, env = process.env): AttemptReceipt[] {
  if (!safeFront.test(frontId)) throw new Error("front id invalid");
  const root = operatorProxyRoot(env);
  if (!root) return [];
  const dir = join(root, "state", "builder-attempts", frontId);
  const eventsPath = join(dir, "events.jsonl");
  const lines = safeReadLines(eventsPath);
  return lines.map((line, index) => {
    let parsed: unknown;
    try {
      parsed = JSON.parse(line);
    } catch {
      throw new Error(`builder attempt event corrupt at line ${index}`);
    }
    return parsed as AttemptReceipt;
  });
}

export function isTerminalReceiptFor(receiptId: string, event: AttemptReceipt): boolean {
  return event.receipt_id === receiptId && (event.state === "COMPLETED" || event.state === "FAILED");
}

export class BuilderAttemptProvenance {
  constructor(readonly env = process.env) {}

  static isConfigured(env = process.env): boolean {
    return !!operatorProxyRoot(env);
  }

  isConfigured(): boolean {
    return BuilderAttemptProvenance.isConfigured(this.env);
  }

  requireConfigured(): void {
    if (!this.isConfigured()) throw new Error("OPERATOR_PROXY_ROOT is required");
  }

  requireUsable(front: string): void {
    this.requireConfigured();
    try {
      this.ensureDir(front);
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      throw new Error(`BUILDER_PROVENANCE_ROOT_UNUSABLE: ${message}`);
    }
  }

  private rootDir(front: string): string {
    if (!safeFront.test(front)) throw new Error("front id invalid");
    const root = operatorProxyRoot(this.env);
    if (!root) throw new Error("OPERATOR_PROXY_ROOT is required");
    return join(root, "state", "builder-attempts", front);
  }

  private eventsPath(front: string): string {
    return join(this.rootDir(front), "events.jsonl");
  }

  private activePath(front: string): string {
    return join(this.rootDir(front), "active.json");
  }

  private quarantinePath(front: string): string {
    return join(this.rootDir(front), "quarantine.jsonl");
  }

  private ensureDir(front: string): void {
    try {
      mkdirSync(this.rootDir(front), {recursive: true});
    } catch (error) {
      const code = (error as NodeJS.ErrnoException).code;
      if (code === "ENOTDIR" || code === "EEXIST") {
        // Configured root is unusable as a directory; callers must treat provenance as unavailable.
        throw new Error("OPERATOR_PROXY_ROOT is not a usable directory");
      }
      throw error;
    }
  }

  activeStarted(input: BuilderInput): {receipt_id: string; state: string; builder_session: string; repair_cycle: number} | undefined {
    if (!this.isConfigured()) return undefined;
    const activePath = this.activePath(input.front_id);
    if (!existsSync(activePath)) return undefined;
    let parsed: unknown;
    try {
      parsed = JSON.parse(readFileSync(activePath, "utf8"));
    } catch {
      return undefined;
    }
    if (typeof parsed !== "object" || parsed === null) return undefined;
    const p = parsed as Record<string, unknown>;
    if (p.state !== "STARTED") return undefined;
    if (!safeReceiptId.test(String(p.receipt_id ?? ""))) return undefined;
    const session = String(p.builder_session ?? "");
    const cycle = Number(p.repair_cycle);
    if (!/^[a-z0-9][a-z0-9._:/-]{2,127}$/i.test(session) || !Number.isInteger(cycle) || cycle < 0) return undefined;
    return {receipt_id: String(p.receipt_id), state: "STARTED", builder_session: session, repair_cycle: cycle};
  }

  recordAttemptStart(input: BuilderInput, config: {backend: BuilderTransport; model: string; attemptNumber: number; providerCorrelationId: string; providerSession?: string}): AttemptStartedReceipt {
    if (!this.isConfigured()) throw new Error("OPERATOR_PROXY_ROOT is required");
    this.requireUsable(input.front_id);
    if (!safeFront.test(input.front_id)) throw new Error("builder attempt front invalid");
    if (!safeSha.test(input.base_sha)) throw new Error("builder attempt base invalid");
    if (!ALLOWED_BACKENDS.includes(config.backend)) throw new Error("builder attempt backend invalid");
    if (!safeModel.test(config.model)) throw new Error("builder attempt model invalid");
    if (!Number.isInteger(input.issue) || input.issue <= 0) throw new Error("builder attempt issue invalid");
    if (!safeBranch.test(input.work_branch)) throw new Error("builder attempt work branch invalid");
    if (!Number.isInteger(input.repair_cycle) || input.repair_cycle < 0) throw new Error("builder attempt repair cycle invalid");
    if (!Number.isInteger(config.attemptNumber) || config.attemptNumber < 1) throw new Error("builder attempt number invalid");
    if (!safeProviderSession.test(config.providerCorrelationId)) throw new Error("builder attempt provider correlation id invalid");
    if (config.providerSession !== undefined && !safeProviderSession.test(config.providerSession)) throw new Error("builder attempt provider session invalid");

    let canonicalWorktree: string;
    try {
      canonicalWorktree = canonicalPath(input.worktree);
    } catch {
      throw new Error("builder attempt worktree invalid");
    }
    if (!existsSync(canonicalWorktree) || !lstatSync(canonicalWorktree).isDirectory()) {
      throw new Error("builder attempt worktree invalid");
    }

    const scopeFingerprint = computeScopeFingerprint(input.base_sha, input.allowed_paths, input.forbidden_paths);

    const receipt: AttemptStartedReceipt = {
      schema_version: SCHEMA_VERSION,
      receipt_id: randomUUID(),
      front_id: input.front_id,
      issue: input.issue,
      base_sha: input.base_sha,
      canonical_worktree: canonicalWorktree,
      work_branch: input.work_branch,
      builder_session: input.session,
      backend: config.backend,
      model: config.model,
      provider_correlation_id: config.providerCorrelationId,
      provider_session: config.providerSession,
      attempt_number: config.attemptNumber,
      repair_cycle: input.repair_cycle,
      scope_fingerprint: scopeFingerprint,
      state: "STARTED",
      created_utc: new Date().toISOString(),
    };

    this.ensureDir(input.front_id);
    appendFileSync(this.eventsPath(input.front_id), `${safeJson(receipt)}\n`);

    const active = {
      schema_version: SCHEMA_VERSION,
      receipt_id: receipt.receipt_id,
      state: "STARTED",
      front_id: receipt.front_id,
      issue: receipt.issue,
      base_sha: receipt.base_sha,
      canonical_worktree: receipt.canonical_worktree,
      work_branch: receipt.work_branch,
      builder_session: receipt.builder_session,
      backend: receipt.backend,
      model: receipt.model,
      provider_correlation_id: receipt.provider_correlation_id,
      attempt_number: receipt.attempt_number,
      repair_cycle: receipt.repair_cycle,
      scope_fingerprint: receipt.scope_fingerprint,
      created_utc: receipt.created_utc,
    };
    atomicWrite(this.activePath(input.front_id), `${safeJson(active)}\n`);

    return receipt;
  }

  private findStartedReceipt(frontId: string, receiptId: string): {receipt: AttemptStartedReceipt; lineIndex: number} | undefined {
    if (!safeFront.test(frontId)) throw new Error("front id invalid");
    if (!safeReceiptId.test(receiptId)) throw new Error("receipt id invalid");
    const eventsPath = this.eventsPath(frontId);
    if (!this.isConfigured() || !existsSync(eventsPath)) return undefined;
    const lines = safeReadLines(eventsPath);
    let result: {receipt: AttemptStartedReceipt; lineIndex: number} | undefined;
    for (let i = 0; i < lines.length; i++) {
      let parsed: AttemptReceipt;
      try {
        parsed = JSON.parse(lines[i]) as AttemptReceipt;
      } catch {
        throw new Error(`builder attempt event corrupt at line ${i}`);
      }
      if (parsed.receipt_id !== receiptId) continue;
      if (parsed.state === "STARTED") {
        if (result) throw new Error("duplicate STARTED attempt receipt");
        result = {receipt: parsed as AttemptStartedReceipt, lineIndex: i};
      } else if (parsed.state === "COMPLETED" || parsed.state === "FAILED") {
        return undefined;
      }
    }
    return result;
  }

  recordAttemptCompleted(receiptId: string, frontId: string, head: string, files: string[], providerCorrelationId: string, nativeProviderSession?: string): void {
    if (!safeFront.test(frontId)) throw new Error("builder attempt front invalid");
    if (!safeSha.test(head)) throw new Error("builder attempt completed head invalid");
    if (!Array.isArray(files) || files.length === 0) throw new Error("builder attempt completed files invalid");
    if (!safeProviderSession.test(providerCorrelationId)) throw new Error("builder attempt completed provider correlation id invalid");
    if (nativeProviderSession !== undefined && !safeProviderSession.test(nativeProviderSession)) throw new Error("builder attempt completed native provider session invalid");

    const located = this.findStartedReceipt(frontId, receiptId);
    if (!located) throw new Error("builder attempt STARTED receipt not found");
    if (located.receipt.provider_correlation_id !== providerCorrelationId) throw new Error("builder attempt provider correlation mismatch");

    const completed: AttemptCompletedReceipt = {
      schema_version: SCHEMA_VERSION,
      receipt_id: receiptId,
      state: "COMPLETED",
      head_sha: head,
      provider_correlation_id: providerCorrelationId,
      native_provider_session: nativeProviderSession,
      changed_files: [...files].sort(),
      completed_utc: new Date().toISOString(),
    };

    this.ensureDir(frontId);
    appendFileSync(this.eventsPath(frontId), `${safeJson(completed)}\n`);
    this.clearActiveIf(frontId, receiptId);
  }

  recordAttemptFailed(receiptId: string, frontId: string, failureClass: string): void {
    if (!safeFront.test(frontId)) throw new Error("front id invalid");
    if (!safeFailureClass.test(failureClass)) throw new Error("builder attempt failure class invalid");
    if (!ELIGIBLE_FALLBACK_FAILURES.has(failureClass) && !INELIGIBLE_FALLBACK_FAILURES.has(failureClass) && failureClass !== "UNKNOWN_BUILD_FAILURE") {
      throw new Error("builder attempt failure class unclassified");
    }

    const located = this.findStartedReceipt(frontId, receiptId);
    if (!located) {
      throw new Error("builder attempt STARTED receipt not found");
    }

    const failed: AttemptFailedReceipt = {
      schema_version: SCHEMA_VERSION,
      receipt_id: receiptId,
      state: "FAILED",
      failure_class: failureClass,
      failed_utc: new Date().toISOString(),
    };

    this.ensureDir(frontId);
    appendFileSync(this.eventsPath(frontId), `${safeJson(failed)}\n`);
    this.clearActiveIf(frontId, receiptId);
  }

  private clearActiveIf(front: string, receiptId: string): void {
    const activePath = this.activePath(front);
    if (!existsSync(activePath)) return;
    let active: {receipt_id?: string};
    try {
      active = JSON.parse(readFileSync(activePath, "utf8"));
    } catch {
      return;
    }
    if (active?.receipt_id === receiptId) {
      const cleared = {schema_version: SCHEMA_VERSION, state: "NONE", cleared_utc: new Date().toISOString()};
      atomicWrite(activePath, `${safeJson(cleared)}\n`);
    }
  }

  recordQuarantine(input: BuilderInput, observedHead: string, authorizedBaseSha: string, reason: QuarantineReason): BuilderCandidateQuarantineEvent {
    if (!this.isConfigured()) throw new Error("OPERATOR_PROXY_ROOT is required");
    if (!safeFront.test(input.front_id)) throw new Error("builder quarantine front invalid");
    if (!safeSha.test(observedHead)) throw new Error("builder quarantine observed head invalid");
    if (!safeSha.test(authorizedBaseSha)) throw new Error("builder quarantine authorized base invalid");
    if (!Number.isInteger(input.issue) || input.issue <= 0) throw new Error("builder quarantine issue invalid");
    if (!safeBranch.test(input.work_branch)) throw new Error("builder quarantine work branch invalid");
    if (!Number.isInteger(input.repair_cycle) || input.repair_cycle < 0) throw new Error("builder quarantine repair cycle invalid");

    let canonicalWorktree: string;
    try {
      canonicalWorktree = canonicalPath(input.worktree);
    } catch {
      throw new Error("builder quarantine worktree invalid");
    }
    if (!existsSync(canonicalWorktree) || !lstatSync(canonicalWorktree).isDirectory()) {
      throw new Error("builder quarantine worktree invalid");
    }

    const evidence = this.worktreeChangeEvidence(canonicalWorktree, authorizedBaseSha);
    const changedFiles = [...new Set([
      ...evidence.committed.names,
      ...evidence.staged.names,
      ...evidence.unstaged.names,
      ...evidence.untracked.map(f => f.path),
    ])].sort();
    const digest = this.computeQuarantineDigest(canonicalWorktree, authorizedBaseSha, observedHead);

    const event: BuilderCandidateQuarantineEvent = {
      schema_version: SCHEMA_VERSION,
      event_id: randomUUID(),
      state: "QUARANTINED",
      front_id: input.front_id,
      issue: input.issue,
      observed_head: observedHead,
      authorized_base_sha: authorizedBaseSha,
      canonical_worktree: canonicalWorktree,
      work_branch: input.work_branch,
      repair_cycle: input.repair_cycle,
      changed_files: changedFiles,
      changed_files_digest: digest,
      reason,
      created_utc: new Date().toISOString(),
    };

    this.ensureDir(input.front_id);
    appendFileSync(this.quarantinePath(input.front_id), `${safeJson(event)}\n`);
    return event;
  }

  readQuarantineEvents(frontId: string): BuilderCandidateQuarantineEvent[] {
    if (!safeFront.test(frontId)) throw new Error("front id invalid");
    const path = this.quarantinePath(frontId);
    if (!existsSync(path)) return [];
    const lines = safeReadLines(path);
    return lines.map((line, index) => {
      let parsed: unknown;
      try {
        parsed = JSON.parse(line);
      } catch {
        throw new Error(`builder quarantine event corrupt at line ${index}`);
      }
      return parsed as BuilderCandidateQuarantineEvent;
    });
  }

  private git(worktree: string, args: string[]): string {
    return execFileSync(process.env.GIT_PATH ?? "git", ["-C", worktree, ...args], {encoding: "utf8", timeout: 120000, windowsHide: true}).trim();
  }

  private diffNamesAndContent(worktree: string, left: string, right: string): {names: string[]; content_sha256: string} {
    const names = this.git(worktree, ["diff", "--name-only", `${left}..${right}`]).split(/\r?\n/).filter(Boolean).sort();
    const patch = this.git(worktree, ["diff", `${left}..${right}`]);
    const contentSha = createHash("sha256").update(patch).digest("hex");
    return {names, content_sha256: contentSha};
  }

  private worktreeChangeEvidence(worktree: string, authorizedBaseSha: string): {
    committed: {names: string[]; content_sha256: string};
    staged: {names: string[]; content_sha256: string};
    unstaged: {names: string[]; content_sha256: string};
    untracked: {path: string; content_sha256: string}[];
  } {
    const head = this.git(worktree, ["rev-parse", "HEAD"]);
    const committed = this.diffNamesAndContent(worktree, authorizedBaseSha, head);
    const stagedPatch = this.git(worktree, ["diff", "--cached"]);
    const stagedNames = this.git(worktree, ["diff", "--cached", "--name-only"]).split(/\r?\n/).filter(Boolean).sort();
    const unstagedPatch = this.git(worktree, ["diff"]);
    const unstagedNames = this.git(worktree, ["diff", "--name-only"]).split(/\r?\n/).filter(Boolean).sort();
    const untrackedPaths = this.git(worktree, ["ls-files", "--others", "--exclude-standard"]).split(/\r?\n/).filter(Boolean).sort();
    const untracked: {path: string; content_sha256: string}[] = [];
    for (const path of untrackedPaths) {
      try {
        const bytes = readFileSync(join(worktree, path));
        untracked.push({path, content_sha256: createHash("sha256").update(bytes).digest("hex")});
      } catch {
        untracked.push({path, content_sha256: ""});
      }
    }
    return {
      committed,
      staged: {names: stagedNames, content_sha256: createHash("sha256").update(stagedPatch).digest("hex")},
      unstaged: {names: unstagedNames, content_sha256: createHash("sha256").update(unstagedPatch).digest("hex")},
      untracked,
    };
  }

  computeQuarantineDigest(worktree: string, authorizedBaseSha: string, observedHead: string): string {
    if (!safeSha.test(authorizedBaseSha)) throw new Error("builder quarantine base invalid");
    if (!safeSha.test(observedHead)) throw new Error("builder quarantine observed head invalid");
    const evidence = this.worktreeChangeEvidence(worktree, authorizedBaseSha);
    const canonical = JSON.stringify({
      authorized_base_sha: authorizedBaseSha,
      observed_head: observedHead,
      committed_files: evidence.committed.names,
      committed_content_sha256: evidence.committed.content_sha256,
      staged_files: evidence.staged.names,
      staged_content_sha256: evidence.staged.content_sha256,
      unstaged_files: evidence.unstaged.names,
      unstaged_content_sha256: evidence.unstaged.content_sha256,
      untracked_files: evidence.untracked.map(f => ({path: f.path, content_sha256: f.content_sha256})),
    });
    return createHash("sha256").update(canonical).digest("hex");
  }

  quarantinedPaths(worktree: string, authorizedBaseSha: string): {tracked: string[]; untracked: string[]} {
    const head = this.git(worktree, ["rev-parse", "HEAD"]);
    const tracked = [...new Set([
      ...this.git(worktree, ["diff", "--name-only", `${authorizedBaseSha}..${head}`]).split(/\r?\n/),
      ...this.git(worktree, ["diff", "--cached", "--name-only"]).split(/\r?\n/),
      ...this.git(worktree, ["diff", "--name-only"]).split(/\r?\n/),
    ].filter(Boolean))].sort();
    const untracked = this.git(worktree, ["ls-files", "--others", "--exclude-standard"]).split(/\r?\n/).filter(Boolean).sort();
    return {tracked, untracked};
  }

  findRecoverableStartedAttempt(input: BuilderInput): RecoverableStartedAttempt | undefined {
    if (!this.isConfigured()) return undefined;
    if (!safeFront.test(input.front_id)) throw new Error("front id invalid");
    if (!safeSha.test(input.base_sha)) throw new Error("base invalid");

    let canonicalWorktree: string;
    try {
      canonicalWorktree = canonicalPath(input.worktree);
    } catch {
      return undefined;
    }

    const expectedFingerprint = computeScopeFingerprint(input.base_sha, input.allowed_paths, input.forbidden_paths);

    const eventsPath = this.eventsPath(input.front_id);
    if (!existsSync(eventsPath)) return undefined;
    const lines = safeReadLines(eventsPath);
    let candidate: RecoverableStartedAttempt | undefined;

    for (let i = 0; i < lines.length; i++) {
      let parsed: AttemptReceipt;
      try {
        parsed = JSON.parse(lines[i]) as AttemptReceipt;
      } catch {
        throw new Error(`builder attempt event corrupt at line ${i}`);
      }
      if (parsed.state !== "STARTED") continue;
      const started = parsed as AttemptStartedReceipt;
      if (started.front_id !== input.front_id) continue;
      if (started.issue !== input.issue) continue;
      if (started.base_sha !== input.base_sha) continue;
      if (started.canonical_worktree !== canonicalWorktree) continue;
      if (started.work_branch !== input.work_branch) continue;
      if (started.scope_fingerprint !== expectedFingerprint) continue;
      if ("provider_correlation_id" in input && input.provider_correlation_id === undefined) throw new Error("BUILDER_PROVENANCE_RECOVERY_REQUIRED: durable provider correlation missing");
      if (input.provider_correlation_id !== undefined && started.provider_correlation_id !== input.provider_correlation_id) continue;
      if (input.session !== started.builder_session) continue;
      if (input.repair_cycle !== started.repair_cycle) continue;

      const laterTerminal = lines.slice(i + 1).some(line => {
        let later: AttemptReceipt;
        try {
          later = JSON.parse(line) as AttemptReceipt;
        } catch {
          return false;
        }
        return later.receipt_id === started.receipt_id && (later.state === "COMPLETED" || later.state === "FAILED");
      });
      if (laterTerminal) continue;

      if (candidate) throw new Error("ambiguous builder attempt provenance");
      candidate = {receipt: started, lineIndex: i, frontId: input.front_id};
    }

    if (!candidate) return undefined;

    const paths = this.quarantinedPaths(canonicalWorktree, input.base_sha);
    const files = [...new Set([...paths.tracked, ...paths.untracked])].sort();
    const violations = scopeViolations(files, {
      schema_version: 1,
      authorization_id: "",
      repository: input.repository,
      roadmap_id: "",
      roadmap_version: "",
      roadmap_item_id: input.front_id,
      expected_base_sha: input.base_sha,
      executor: "codex_control_plane",
      risk: input.risk,
      allowed_paths: input.allowed_paths,
      forbidden_paths: input.forbidden_paths,
      acceptance: input.acceptance,
      test_commands: input.test_commands,
      deployment_allowed: false,
      deployment_mode: input.deployment_mode,
      front_id: input.front_id,
    });
    if (violations.length > 0) {
      throw new Error(`recoverable attempt files violate scope: ${violations.join(", ")}`);
    }

    return candidate;
  }
}
