import type {ProxySpec} from "./types.js";
import {execFileSync} from "node:child_process";
import {realpathSync} from "node:fs";

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
  const message = String(error instanceof Error ? error.message : error);
  const classes: { pattern: RegExp; failure_class: string; transient: boolean }[] = [
    { pattern: /usage limit|credit|out of credits|billing|payment/i, failure_class: "CODEX_CREDIT_LIMIT", transient: false },
    { pattern: /quota|rate limit|too many requests/i, failure_class: "CODEX_QUOTA_EXHAUSTED", transient: true },
    { pattern: /spawnSync.*ENOENT|ENOENT.*codex|executable not found/i, failure_class: "EXECUTABLE_NOT_FOUND", transient: false },
    { pattern: /spawnSync.*EINVAL|spawn error|process launch|spawn/i, failure_class: "PROCESS_SPAWN_FAILURE", transient: true },
    { pattern: /timeout|timed out|ETIMEDOUT/i, failure_class: "TRANSPORT_TIMEOUT", transient: true },
    { pattern: /provider unavailable|model unavailable|service unavailable|503|502|504/i, failure_class: "PROVIDER_UNAVAILABLE", transient: true },
    { pattern: /auth.*expir|session.*expir|unauthorized|401/i, failure_class: "AUTH_SESSION_EXPIRED", transient: false },
    { pattern: /protocol|network|ECONNREFUSED|ECONNRESET|EPIPE/i, failure_class: "TRANSPORT_FAILURE", transient: true },
  ];
  for (const cls of classes) {
    if (cls.pattern.test(message)) return { eligible: true, failure_class: cls.failure_class, transient: cls.transient };
  }
  if (INELIGIBLE_FALLBACK_FAILURES.has(message)) return { eligible: false, failure_class: message, transient: false };
  if (/forbidden paths|builder produced no changes|scope violation|invalid spec|policy block|review finding|semantic build failure|git conflict|owner authority required|wrong base|wrong head|dirty worktree/i.test(message)) {
    return { eligible: false, failure_class: "SCOPE_VIOLATION", transient: false };
  }
  return { eligible: false, failure_class: "UNKNOWN_BUILD_FAILURE", transient: false };
}

function samePath(a: string, b: string): boolean {
  return a.localeCompare(b, undefined, { sensitivity: "accent" }) === 0;
}

export function validateWorktree(worktree: string, expectedBase: string, forbiddenRoots: string[]) {
  const top = execFileSync(process.env.GIT_PATH ?? "git", ["-C", worktree, "rev-parse", "--show-toplevel"], { encoding: "utf8", timeout: 30000 }).trim();
  const resolvedTop = realpathSync(top), resolvedWorktree = realpathSync(worktree);
  if (!samePath(resolvedTop, resolvedWorktree)) throw new Error("builder worktree identity mismatch");
  for (const root of forbiddenRoots) {
    if (top.toLowerCase().startsWith(root.toLowerCase())) throw new Error("builder worktree root denied");
  }
  const head = execFileSync(process.env.GIT_PATH ?? "git", ["-C", worktree, "rev-parse", "HEAD"], { encoding: "utf8", timeout: 30000 }).trim();
  if (!/^[0-9a-f]{40}$/.test(head)) throw new Error("builder worktree head invalid");
  if (head !== expectedBase) throw new Error("builder worktree base mismatch");
  const status = execFileSync(process.env.GIT_PATH ?? "git", ["-C", worktree, "status", "--porcelain", "--untracked-files=all"], { encoding: "utf8", timeout: 30000 }).trim();
  if (status) throw new Error("builder worktree dirty");
}

export function scopeViolations(files: string[], spec: ProxySpec): string[] {
  const allowed = (path: string) => spec.allowed_paths.some(p => p.endsWith("/") ? path.startsWith(p) : path === p) && !spec.forbidden_paths.some(p => path === p || path.startsWith(p.endsWith("/") ? p : `${p}/`));
  return files.filter(p => !allowed(p));
}
