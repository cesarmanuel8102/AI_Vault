import type {ProxySpec} from "./types.js";
import {execFileSync} from "node:child_process";
import {realpathSync, statSync} from "node:fs";
import {posix, win32} from "node:path";

export type BuilderTransport = "codex_cli_openai" | "opencode_github_copilot" | "opencode_ollama";

export const ELIGIBLE_FALLBACK_FAILURES = new Set([
  "CODEX_CREDIT_LIMIT",
  "CODEX_QUOTA_EXHAUSTED",
  "RATE_LIMIT",
  "MODEL_UNAVAILABLE",
  "PROVIDER_UNAVAILABLE",
  "AUTH_SESSION_EXPIRED",
  "TRANSPORT_TIMEOUT",
  "TRANSPORT_FAILURE",
  "PROCESS_SPAWN_FAILURE",
  "EXECUTABLE_NOT_FOUND",
  "PROVIDER_PROTOCOL_FAILURE",
]);

export const INELIGIBLE_FALLBACK_FAILURES = new Set([
  "TEST_FAILURE",
  "SCOPE_VIOLATION",
  "FORBIDDEN_PATH",
  "WRONG_BASE",
  "WRONG_HEAD",
  "DIRTY_WORKTREE",
  "INVALID_SPEC",
  "POLICY_BLOCK",
  "REVIEW_FINDING",
  "SEMANTIC_BUILD_FAILURE",
  "GIT_CONFLICT",
  "OWNER_AUTHORITY_REQUIRED",
]);

export class BuilderBackendError extends Error {
  constructor(message: string, readonly failureClass: string, readonly transient = false) { super(message); }
}

export interface BuilderInput {
  repository: string;
  worktree: string;
  front_id: string;
  issue: number;
  base_sha: string;
  work_branch: string;
  allowed_paths: string[];
  forbidden_paths: string[];
  acceptance: string[];
  test_commands: string[];
  repair_cycle: number;
  previous_head?: string;
  risk: "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";
  deployment_mode: "NO_DEPLOY" | "INSTALL_ONLY" | "INSTALL_AND_RUNTIME_PILOT" | "DOCUMENTATION_CLOSEOUT";
  prompt: string;
  session: string;
}

export interface BuilderResult {
  executor_role: "codex_control_plane" | "agent_loop";
  builder_backend: BuilderTransport;
  builder_model: string;
  builder_session: string;
  provider_session: string;
  base_sha: string;
  head_sha: string;
  branch: string;
  commit: string;
  pr: number;
  fallback_reason?: string;
  started_utc: string;
  completed_utc: string;
}

export interface ControlPlaneBuilderBackend {
  readonly id: BuilderTransport;
  readonly model: string;
  build(input: BuilderInput, env?: NodeJS.ProcessEnv): Promise<BuilderResult>;
}

export function isEligibleFallback(error: unknown): { eligible: boolean; failure_class: string; transient: boolean } {
  if (error instanceof BuilderBackendError) return { eligible: ELIGIBLE_FALLBACK_FAILURES.has(error.failureClass), failure_class: error.failureClass, transient: error.transient };
  const message = String(error instanceof Error ? error.message : error);
  const classes: { pattern: RegExp; failure_class: string; transient: boolean }[] = [
    { pattern: /usage limit|credit limit|out of credits/i, failure_class: "CODEX_CREDIT_LIMIT", transient: false },
    { pattern: /quota exceeded|quota exhausted/i, failure_class: "CODEX_QUOTA_EXHAUSTED", transient: true },
    { pattern: /rate limit|too many requests|429/i, failure_class: "RATE_LIMIT", transient: true },
    { pattern: /spawnSync.*ENOENT|ENOENT.*codex|executable not found/i, failure_class: "EXECUTABLE_NOT_FOUND", transient: false },
    { pattern: /spawnSync.*EINVAL|spawn error|process launch|spawn/i, failure_class: "PROCESS_SPAWN_FAILURE", transient: true },
    { pattern: /timeout|timed out|ETIMEDOUT/i, failure_class: "TRANSPORT_TIMEOUT", transient: true },
    { pattern: /model unavailable|model not found/i, failure_class: "MODEL_UNAVAILABLE", transient: true },
    { pattern: /provider unavailable|service unavailable|503|502|504/i, failure_class: "PROVIDER_UNAVAILABLE", transient: true },
    { pattern: /auth.*expir|session.*expir|unauthorized|401/i, failure_class: "AUTH_SESSION_EXPIRED", transient: false },
    { pattern: /protocol/i, failure_class: "PROVIDER_PROTOCOL_FAILURE", transient: false },
    { pattern: /network|ECONNREFUSED|ECONNRESET|EPIPE/i, failure_class: "TRANSPORT_FAILURE", transient: true },
  ];
  for (const cls of classes) {
    if (cls.pattern.test(message)) return { eligible: true, failure_class: cls.failure_class, transient: cls.transient };
  }
  if (INELIGIBLE_FALLBACK_FAILURES.has(message)) return { eligible: false, failure_class: message, transient: false };
  const ineligible: [RegExp, string][] = [
    [/test (failed|failure)|npm ERR!/i, "TEST_FAILURE"], [/forbidden paths|path outside scope/i, "FORBIDDEN_PATH"],
    [/scope violation/i, "SCOPE_VIOLATION"], [/invalid spec/i, "INVALID_SPEC"], [/policy block/i, "POLICY_BLOCK"],
    [/review finding/i, "REVIEW_FINDING"], [/semantic build failure/i, "SEMANTIC_BUILD_FAILURE"], [/git conflict/i, "GIT_CONFLICT"],
    [/owner authority required/i, "OWNER_AUTHORITY_REQUIRED"], [/wrong base|base mismatch/i, "WRONG_BASE"],
    [/wrong head|head mismatch/i, "WRONG_HEAD"], [/dirty worktree/i, "DIRTY_WORKTREE"], [/builder produced no changes/i, "SCOPE_VIOLATION"],
  ];
  for (const [pattern, failureClass] of ineligible) if (pattern.test(message)) return { eligible: false, failure_class: failureClass, transient: false };
  return { eligible: false, failure_class: "UNKNOWN_BUILD_FAILURE", transient: false };
}

function sameFileSystemObject(a: string, b: string): boolean {
  try {
    const sa = statSync(a), sb = statSync(b);
    return sa.dev === sb.dev && sa.ino === sb.ino;
  } catch {
    return false;
  }
}

export function isEqualOrDescendantPath(root: string, candidate: string): boolean {
  const pathApi = /^[A-Za-z]:[\\/]/.test(root) || /^[A-Za-z]:[\\/]/.test(candidate) ? win32 : posix;
  const relative = pathApi.relative(pathApi.resolve(root), pathApi.resolve(candidate));
  return relative === "" || relative !== ".." && !relative.startsWith(`..${pathApi.sep}`) && !pathApi.isAbsolute(relative);
}

export function validateWorktree(worktree: string, expectedBase: string, forbiddenRoots: string[], env: NodeJS.ProcessEnv = process.env) {
  const top = execFileSync(env.GIT_PATH ?? "git", ["-C", worktree, "rev-parse", "--show-toplevel"], { encoding: "utf8", timeout: 30000 }).trim();
  const resolvedTop = realpathSync(top), resolvedWorktree = realpathSync(worktree);
  if (!sameFileSystemObject(resolvedTop, resolvedWorktree)) throw new Error("builder worktree identity mismatch");
  for (const root of forbiddenRoots) {
    if (isEqualOrDescendantPath(root, resolvedTop)) throw new Error("builder worktree root denied");
  }
  const head = execFileSync(env.GIT_PATH ?? "git", ["-C", worktree, "rev-parse", "HEAD"], { encoding: "utf8", timeout: 30000 }).trim();
  if (!/^[0-9a-f]{40}$/.test(head)) throw new Error("builder worktree head invalid");
  if (head !== expectedBase) throw new Error("builder worktree base mismatch");
  const status = execFileSync(env.GIT_PATH ?? "git", ["-C", worktree, "status", "--porcelain", "--untracked-files=all"], { encoding: "utf8", timeout: 30000 }).trim();
  if (status) throw new Error("builder worktree dirty");
}

export function scopeViolations(files: string[], spec: ProxySpec): string[] {
  const allowed = (path: string) => spec.allowed_paths.some(p => p.endsWith("/") ? path.startsWith(p) : path === p) && !spec.forbidden_paths.some(p => path === p || path.startsWith(p.endsWith("/") ? p : `${p}/`));
  return files.filter(p => !allowed(p));
}
