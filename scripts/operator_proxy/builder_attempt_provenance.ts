import {createHash, randomUUID} from "node:crypto";
import {execFileSync} from "node:child_process";
import {appendFileSync, existsSync, lstatSync, mkdirSync, readFileSync, realpathSync, renameSync, rmSync, writeFileSync} from "node:fs";
import {isAbsolute, join} from "node:path";
import type {BuilderInput, BuilderTransport} from "./builder_backend.js";
import {ELIGIBLE_FALLBACK_FAILURES, INELIGIBLE_FALLBACK_FAILURES, scopeViolations} from "./builder_backend.js";
import {safeJson} from "./redaction.js";

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

function operatorProxyRoot(env = process.env): string {
  const root = env.OPERATOR_PROXY_ROOT;
  if (!root) throw new Error("OPERATOR_PROXY_ROOT is required");
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
  const dir = join(operatorProxyRoot(env), "state", "builder-attempts", frontId);
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

  private rootDir(front: string): string {
    if (!safeFront.test(front)) throw new Error("front id invalid");
    return join(operatorProxyRoot(this.env), "state", "builder-attempts", front);
  }

  private eventsPath(front: string): string {
    return join(this.rootDir(front), "events.jsonl");
  }

  private activePath(front: string): string {
    return join(this.rootDir(front), "active.json");
  }

  private ensureDir(front: string): void {
    mkdirSync(this.rootDir(front), {recursive: true});
  }

  recordAttemptStart(input: BuilderInput, config: {backend: BuilderTransport; model: string; attemptNumber: number; providerCorrelationId: string; providerSession?: string}): AttemptStartedReceipt {
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
    if (!existsSync(eventsPath)) return undefined;
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

  private currentWorktreeFiles(worktree: string): string[] {
    const git = (args: string[]) => execFileSync(process.env.GIT_PATH ?? "git", ["-C", worktree, ...args], {encoding: "utf8", timeout: 120000, windowsHide: true}).trim();
    const tracked = git(["diff", "--name-only", "HEAD"]);
    const staged = git(["diff", "--cached", "--name-only"]);
    const untracked = git(["ls-files", "--others", "--exclude-standard"]);
    return [...new Set([tracked, staged, untracked].flatMap(x => x ? x.split(/\r?\n/) : []).filter(Boolean))].sort();
  }

  findRecoverableStartedAttempt(input: BuilderInput): RecoverableStartedAttempt | undefined {
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

    const files = this.currentWorktreeFiles(canonicalWorktree);
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
