import type {ProxySpec} from "./types.js";
import type {BuilderInput, BuilderResult, BuilderTransport} from "./builder_backend.js";
import { isEligibleFallback, isEqualOrDescendantPath, validateWorktree, scopeViolations, ELIGIBLE_FALLBACK_FAILURES, INELIGIBLE_FALLBACK_FAILURES } from "./builder_backend.js";
import { resolveCodexConfig, resolveCopilotConfig, resolveOllamaConfig, type BackendConfig } from "./builder_config.js";
import { runCodexBuilder } from "./codex_builder.js";
import { runOpenCodeBuilder } from "./opencode_builder.js";
import { BuilderAttemptProvenance } from "./builder_attempt_provenance.js";
import { createHash, randomUUID } from "node:crypto";
import { execFileSync } from "node:child_process";
import { redactedError, redactString } from "./redaction.js";
import { existsSync, lstatSync, mkdirSync, readFileSync, readlinkSync, readdirSync, realpathSync, rmdirSync, rmSync, statSync, writeFileSync } from "node:fs";
import { dirname, isAbsolute, join, resolve } from "node:path";


function forbiddenWorktreeRoots(env = process.env): string[] {
  const configured = env.OPERATOR_PROXY_FORBIDDEN_ROOTS;
  if (configured) return configured.split(/[,;]/).map(s => s.trim()).filter(Boolean);
  if (process.platform === "win32") return ["C:\\Windows\\System32", "C:\\AI_VAULT"];
  return ["/mnt/c/Windows/System32", "/mnt/c/AI_VAULT", "/AI_VAULT"];
}

function operatorProxyRoot(env = process.env): string {
  const root = env.OPERATOR_PROXY_ROOT;
  if (!root) throw new Error("OPERATOR_PROXY_ROOT is required");
  if (!isAbsolute(root)) throw new Error("OPERATOR_PROXY_ROOT must be absolute");
  return root;
}

export interface RouterOptions {
  env?: NodeJS.ProcessEnv;
  forceBackend?: "codex_cli_openai" | "opencode_github_copilot" | "opencode_ollama";
  baseSha?: string;
}

function isExact40CharSha(value: string): boolean {
  return /^[0-9a-f]{40}$/.test(value);
}

function buildInputFromSpec(spec: ProxySpec, issue: number, session: string, repairCycle: number, prompt: string, env: NodeJS.ProcessEnv, worktree?: string, baseSha?: string): BuilderInput {
  if (!spec.front_id || !spec.work_branch || !spec.expected_base_sha) throw new Error("builder spec incomplete");
  const effectiveBase = baseSha ?? spec.expected_base_sha;
  if (!isExact40CharSha(effectiveBase)) throw new Error("builder base identity invalid");
  return {
    repository: spec.repository,
    worktree: worktree ?? join(operatorProxyRoot(env), "worktrees", spec.front_id),
    front_id: spec.front_id,
    issue,
    base_sha: effectiveBase,
    work_branch: spec.work_branch,
    allowed_paths: spec.allowed_paths,
    forbidden_paths: spec.forbidden_paths,
    acceptance: spec.acceptance,
    test_commands: spec.test_commands,
    repair_cycle: repairCycle,
    risk: spec.risk,
    deployment_mode: spec.deployment_mode ?? "NO_DEPLOY",
    prompt,
    session,
  };
}

function sameFileSystemObject(a: string, b: string): boolean {
  try {
    const sa = statSync(a), sb = statSync(b);
    return sa.dev === sb.dev && sa.ino === sb.ino;
  } catch {
    return false;
  }
}

function validateWorktreeIdentity(worktree: string, env: NodeJS.ProcessEnv) {
  const forbiddenRoots = forbiddenWorktreeRoots(env);
  const top = execFileSync(env.GIT_PATH ?? "git", ["-C", worktree, "rev-parse", "--show-toplevel"], { encoding: "utf8", timeout: 30000 }).trim();
  const resolvedTop = realpathSync(top), resolvedWorktree = realpathSync(worktree);
  if (!sameFileSystemObject(resolvedTop, resolvedWorktree)) throw new Error("builder worktree identity mismatch");
  for (const root of forbiddenRoots) {
    if (isEqualOrDescendantPath(root, resolvedTop)) throw new Error("builder worktree root denied");
  }
}

function specFromInput(input: BuilderInput): ProxySpec {
  return {
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
  };
}

async function validateBuilderOutput(input: BuilderInput, result: BuilderResult, env: NodeJS.ProcessEnv): Promise<void> {
  validateWorktreeIdentity(input.worktree, env);
  const head = execFileSync(env.GIT_PATH ?? "git", ["-C", input.worktree, "rev-parse", "HEAD"], { encoding: "utf8", timeout: 30000 }).trim();
  if (head !== result.head_sha) throw new Error("builder result head mismatch");
  const committedFiles = execFileSync(env.GIT_PATH ?? "git", ["-C", input.worktree, "diff", "--name-only", `${input.base_sha}..${head}`], { encoding: "utf8", timeout: 30000 }).split(/\r?\n/).filter(Boolean);
  const workingTreeFiles = execFileSync(env.GIT_PATH ?? "git", ["-C", input.worktree, "status", "--porcelain", "--untracked-files=all"], { encoding: "utf8", timeout: 30000 }).split(/\r?\n/).filter(Boolean).map(line => line.slice(3).trim()).filter(Boolean);
  const files = [...new Set([...committedFiles, ...workingTreeFiles])];
  if (files.length === 0) throw new Error("builder produced no changes");
  const violations = scopeViolations(files, specFromInput(input));
  if (violations.length > 0) throw new Error(`builder changed forbidden paths: ${violations.join(", ")}`);
}

const safeModel = /^[a-z0-9][a-z0-9._:/-]{2,127}$/;
const safeFront = /^[A-Z0-9][A-Z0-9._-]{5,127}$/;
function recordHealth(healthDir: string, record: { backend: string; model: string; failure_class: string; attempt: number; front_id: string; base_sha: string; created_utc: string }) {
  try {
    if (!ALLOWED_BACKENDS.includes(record.backend as BuilderTransport) || !safeModel.test(record.model) || !ELIGIBLE_FALLBACK_FAILURES.has(record.failure_class.replace(/^retry:/, "")) && !INELIGIBLE_FALLBACK_FAILURES.has(record.failure_class.replace(/^retry:/, "")) && record.failure_class !== "UNKNOWN_BUILD_FAILURE" || !safeFront.test(record.front_id) || !/^[0-9a-f]{40}$/.test(record.base_sha) || !Number.isInteger(record.attempt) || record.attempt < 1 || record.attempt > 3 || Number.isNaN(Date.parse(record.created_utc))) return;
    mkdirSync(healthDir, { recursive: true });
    const path = join(healthDir, `${record.backend}-${record.attempt}-${Date.now()}.json`);
    writeFileSync(path, `${JSON.stringify({schema_version:1,...record})}\n`);
  } catch {
    // health logging is best-effort; do not block build flow
  }
}

const ALLOWED_BACKENDS: BuilderTransport[] = ["codex_cli_openai", "opencode_github_copilot", "opencode_ollama"];

function resolveForceBackend(env: NodeJS.ProcessEnv, option?: BuilderTransport): BuilderTransport | undefined {
  if (option && ALLOWED_BACKENDS.includes(option)) return option;
  const configured = env.OPERATOR_PROXY_BUILDER_BACKEND;
  if (configured && ALLOWED_BACKENDS.includes(configured as BuilderTransport)) return configured as BuilderTransport;
  return undefined;
}

function validateBaseOverride(worktree: string, requestedBase: string, env: NodeJS.ProcessEnv) {
  if (!isExact40CharSha(requestedBase)) throw new Error("builder base override identity invalid");
  const cleanHead = execFileSync(env.GIT_PATH ?? "git", ["-C", worktree, "rev-parse", "HEAD"], { encoding: "utf8", timeout: 30000 }).trim();
  if (cleanHead !== requestedBase) throw new Error("builder base override does not match clean worktree HEAD");
  const status = execFileSync(env.GIT_PATH ?? "git", ["-C", worktree, "status", "--porcelain", "--untracked-files=all"], { encoding: "utf8", timeout: 30000 }).trim();
  if (status) throw new Error("builder base override worktree is dirty");
}

interface IgnoredSnapshot {
  paths: Map<string, string>;
  ignoredDirs: Set<string>;
  parentDirs: Set<string>;
}

function validateIgnoredRelativePath(path: string) {
  if (!path || isAbsolute(path) || path.split(/[\\/]/).some(part => part === "..")) throw new Error("builder ignored path invalid");
}

function ignoredFingerprint(worktree: string, path: string): string {
  validateIgnoredRelativePath(path);
  const absolute = resolve(worktree, path), stat = lstatSync(absolute);
  const kind = stat.isSymbolicLink() ? "symlink" : stat.isFile() ? "file" : "other";
  if (kind === "other") throw new Error("builder ignored artifact type invalid");
  const bytes = kind === "symlink" ? Buffer.from(readlinkSync(absolute), "utf8") : readFileSync(absolute);
  return `${kind}:${stat.mode}:${stat.size}:${createHash("sha256").update(bytes).digest("hex")}`;
}

function ignoredSnapshot(worktree: string, env: NodeJS.ProcessEnv): IgnoredSnapshot {
  const output = execFileSync(env.GIT_PATH ?? "git", ["-C", worktree, "ls-files", "--others", "--ignored", "--exclude-standard", "-z"], { encoding: "utf8", timeout: 30000 });
  const paths = new Map<string, string>();
  for (const path of output.split("\0").filter(Boolean)) paths.set(path, ignoredFingerprint(worktree, path));
  const ignoredStatus = execFileSync(env.GIT_PATH ?? "git", ["-C", worktree, "status", "--ignored=matching", "--porcelain=v1", "-z", "--untracked-files=all"], { encoding: "utf8", timeout: 30000 });
  const ignoredDirs = new Set(ignoredStatus.split("\0").filter(entry => entry.startsWith("!! ") && entry.endsWith("/")).map(entry => entry.slice(3, -1)));
  const parentDirs = new Set<string>();
  for (const path of [...paths.keys(), ...ignoredDirs]) {
    validateIgnoredRelativePath(path);
    for (let parent = dirname(path); parent !== "."; parent = dirname(parent)) parentDirs.add(parent);
  }
  return { paths, ignoredDirs, parentDirs };
}

function removeNewIgnoredPaths(worktree: string, baseline: IgnoredSnapshot, env: NodeJS.ProcessEnv) {
  const current = ignoredSnapshot(worktree, env);
  const created = [...current.paths.keys()].filter(path => !baseline.paths.has(path)).sort((a, b) => b.length - a.length);
  const root = resolve(worktree);
  for (const path of created) {
    const absolute = resolve(root, path);
    if (absolute !== root && !absolute.startsWith(`${root}\\`) && !absolute.startsWith(`${root}/`)) throw new Error("builder ignored path escaped worktree");
    rmSync(absolute, { force: true, recursive: true });
    for (let parent = dirname(path); parent !== "." && !baseline.parentDirs.has(parent); parent = dirname(parent)) {
      const directory = resolve(root, parent);
      try {
        if (readdirSync(directory).length > 0) break;
        rmdirSync(directory);
      } catch (error) {
        if (existsSync(directory)) throw error;
      }
    }
  }
  const remaining = ignoredSnapshot(worktree, env);
  const createdDirs = [...remaining.ignoredDirs].filter(path => !baseline.ignoredDirs.has(path)).sort((a, b) => b.length - a.length);
  for (const path of createdDirs) {
    validateIgnoredRelativePath(path);
    const directory = resolve(root, path);
    if (readdirSync(directory).length > 0) throw new Error("builder ignored directory cleanup blocked");
    rmdirSync(directory);
  }
  const restored = ignoredSnapshot(worktree, env);
  if (restored.paths.size !== baseline.paths.size || restored.ignoredDirs.size !== baseline.ignoredDirs.size || [...baseline.paths].some(([path, fingerprint]) => restored.paths.get(path) !== fingerprint) || [...baseline.ignoredDirs].some(path => !restored.ignoredDirs.has(path))) throw new Error("builder ignored baseline restore mismatch");
}

function restoreWorktreeBaseline(worktree: string, baseSha: string, ignoredBaseline: IgnoredSnapshot, env: NodeJS.ProcessEnv) {
  execFileSync(env.GIT_PATH ?? "git", ["-C", worktree, "reset", "--hard", baseSha], { encoding: "utf8", timeout: 120000, windowsHide: true });
  execFileSync(env.GIT_PATH ?? "git", ["-C", worktree, "clean", "-fd", "--"], { encoding: "utf8", timeout: 120000, windowsHide: true });
  removeNewIgnoredPaths(worktree, ignoredBaseline, env);
  const head = execFileSync(env.GIT_PATH ?? "git", ["-C", worktree, "rev-parse", "HEAD"], { encoding: "utf8", timeout: 30000 }).trim();
  if (head !== baseSha) throw new Error("builder worktree baseline restore head mismatch");
  const status = execFileSync(env.GIT_PATH ?? "git", ["-C", worktree, "status", "--porcelain", "--untracked-files=all"], { encoding: "utf8", timeout: 30000 }).trim();
  if (status) throw new Error("builder worktree baseline restore left dirty state");
}

function collectChangedFiles(worktree: string, baseSha: string, env: NodeJS.ProcessEnv): string[] {
  const head = execFileSync(env.GIT_PATH ?? "git", ["-C", worktree, "rev-parse", "HEAD"], { encoding: "utf8", timeout: 30000 }).trim();
  const committedFiles = execFileSync(env.GIT_PATH ?? "git", ["-C", worktree, "diff", "--name-only", `${baseSha}..${head}`], { encoding: "utf8", timeout: 30000 }).split(/\r?\n/).filter(Boolean);
  const workingTreeFiles = execFileSync(env.GIT_PATH ?? "git", ["-C", worktree, "status", "--porcelain", "--untracked-files=all"], { encoding: "utf8", timeout: 30000 }).split(/\r?\n/).filter(Boolean).map(line => line.slice(3).trim()).filter(Boolean);
  return [...new Set([...committedFiles, ...workingTreeFiles])];
}

export async function routeControlPlaneBuild(spec: ProxySpec, issue: number, prompt: string, repairCycle: number, options: RouterOptions = {}, worktree?: string): Promise<BuilderResult> {
  const env = options.env ?? process.env;
  const session = `builder-${randomUUID()}`;
  const input = buildInputFromSpec(spec, issue, session, repairCycle, prompt, env, worktree, options.baseSha);
  const healthDir = join(operatorProxyRoot(env), "state", "builder-health");
  const provenance = new BuilderAttemptProvenance(env);
  if (options.baseSha) validateBaseOverride(worktree ?? input.worktree, options.baseSha, env);
  validateWorktree(input.worktree, input.base_sha, forbiddenWorktreeRoots(env), env);

  const forceBackend = resolveForceBackend(env, options.forceBackend);
  const attemptOrder: BuilderTransport[] = forceBackend ? [forceBackend] : ["codex_cli_openai", "opencode_github_copilot", "opencode_ollama"];
  let fallbackReason: string | undefined;

  for (let index = 0; index < attemptOrder.length; index++) {
    const backendId = attemptOrder[index];
    const backendSession = `${session}-${backendId}`;
    const backendInput = { ...input, session: backendSession };
    let cfg: BackendConfig;
    let buildFn: (i: BuilderInput) => Promise<BuilderResult>;
    if (backendId === "codex_cli_openai") {
      cfg = resolveCodexConfig(env);
      buildFn = (i) => runCodexBuilder(i, cfg, env);
    } else if (backendId === "opencode_github_copilot") {
      cfg = resolveCopilotConfig(spec.risk, env);
      buildFn = (i) => runOpenCodeBuilder(i, cfg, env);
    } else {
      cfg = resolveOllamaConfig(env);
      buildFn = (i) => runOpenCodeBuilder(i, cfg, env);
    }

    const startedReceipt = provenance.recordAttemptStart(input, {backend: backendId, model: cfg.model, attemptNumber: index + 1});

    const invokeBackend = async (attemptSession: string): Promise<BuilderResult> => {
      const result = await buildFn({ ...backendInput, session: attemptSession });
      await validateBuilderOutput({ ...backendInput, session: attemptSession }, result, env);
      if (result.executor_role !== "codex_control_plane" || result.base_sha !== input.base_sha || result.builder_backend !== backendId || result.builder_model !== cfg.model || !/^[a-z0-9][a-z0-9._:/-]{2,127}$/.test(result.provider_session) || !/^[0-9a-f]{40}$/.test(result.head_sha)) throw new Error("builder result contract invalid");
      if (result.fallback_reason !== undefined) throw new Error("builder backend must not set fallback_reason");
      if (fallbackReason && backendId === "codex_cli_openai") throw new Error("primary Codex result cannot be an automatic fallback");
      result.builder_session = session;
      if (fallbackReason) result.fallback_reason = fallbackReason;
      return result;
    };

    const attemptIgnoredBaseline = ignoredSnapshot(input.worktree, env);
    try {
      const result = await invokeBackend(backendSession);
      const files = collectChangedFiles(input.worktree, input.base_sha, env);
      provenance.recordAttemptCompleted(startedReceipt.receipt_id, input.front_id, result.head_sha, files, result.provider_session);
      return result;
    } catch (error) {
      restoreWorktreeBaseline(input.worktree, input.base_sha, attemptIgnoredBaseline, env);
      validateWorktree(input.worktree, input.base_sha, forbiddenWorktreeRoots(env), env);
      const { eligible, failure_class, transient } = isEligibleFallback(error);
      provenance.recordAttemptFailed(startedReceipt.receipt_id, input.front_id, failure_class);
      recordHealth(healthDir, { backend: backendId, model: cfg.model, failure_class, attempt: index + 1, front_id: spec.front_id!, base_sha: input.base_sha, created_utc: new Date().toISOString() });

      if (!eligible) throw new Error(redactString(String(error instanceof Error ? error.message : error)));
      if (index === attemptOrder.length - 1) {
        throw new Error(`BUILDER_ROUTER_BLOCKED: ${failure_class}; attempts=${attemptOrder.join(",")}`);
      }

      if (transient && cfg.maxRetries > 0) {
        const backoffMs = Math.min(1000 * Math.pow(2, index), 8000);
        await new Promise(resolve => setTimeout(resolve, backoffMs));
        const retryReceipt = provenance.recordAttemptStart(input, {backend: backendId, model: cfg.model, attemptNumber: index + 1});
        const retryIgnoredBaseline = ignoredSnapshot(input.worktree, env);
        try {
          const result = await invokeBackend(`${backendSession}-retry`);
          const files = collectChangedFiles(input.worktree, input.base_sha, env);
          provenance.recordAttemptCompleted(retryReceipt.receipt_id, input.front_id, result.head_sha, files, result.provider_session);
          return result;
        } catch (retryError) {
          restoreWorktreeBaseline(input.worktree, input.base_sha, retryIgnoredBaseline, env);
          validateWorktree(input.worktree, input.base_sha, forbiddenWorktreeRoots(env), env);
          const { eligible: retryEligible, failure_class: retryClass } = isEligibleFallback(retryError);
          provenance.recordAttemptFailed(retryReceipt.receipt_id, input.front_id, retryClass);
          recordHealth(healthDir, { backend: backendId, model: cfg.model, failure_class: `retry:${retryClass}`, attempt: index + 1, front_id: spec.front_id!, base_sha: input.base_sha, created_utc: new Date().toISOString() });
          if (!retryEligible) throw new Error(redactString(String(retryError instanceof Error ? retryError.message : retryError)));
        }
      }

      fallbackReason = failure_class;
    }
  }
  throw new Error("BUILDER_ROUTER_BLOCKED: all backends exhausted");
}

export function listBuilderBackendHealth(healthDir?: string, env: NodeJS.ProcessEnv = process.env) {
  try {
    const dir = healthDir ?? join(operatorProxyRoot(env), "state", "builder-health");
    return readdirSync(dir).filter(f => f.endsWith(".json"));
  } catch {
    return [];
  }
}

export { ELIGIBLE_FALLBACK_FAILURES, INELIGIBLE_FALLBACK_FAILURES };
