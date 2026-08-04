import type {ProxySpec} from "./types.js";
import type {BuilderInput, BuilderResult, BuilderTransport, ControlPlaneBuilderBackend} from "./builder_backend.js";
import { isEligibleFallback, validateWorktree, scopeViolations, INELIGIBLE_FALLBACK_FAILURES, ELIGIBLE_FALLBACK_FAILURES } from "./builder_backend.js";
import { resolveCodexConfig, resolveCopilotConfig, resolveOllamaConfig, type BackendConfig } from "./builder_config.js";
import { runCodexBuilder } from "./codex_builder.js";
import { runOpenCodeBuilder } from "./opencode_builder.js";
import { randomUUID } from "node:crypto";
import { execFileSync } from "node:child_process";
import { redactedError } from "./redaction.js";
import { existsSync, mkdirSync, readdirSync, realpathSync, writeFileSync } from "node:fs";
import { join, normalize, relative } from "node:path";

const FORBIDDEN_WORKTREE_ROOTS = [
  "C:\\Windows\\System32",
  "C:\\AI_VAULT",
];

export interface RouterOptions {
  env?: NodeJS.ProcessEnv;
  forceBackend?: "codex_cli_openai" | "opencode_github_copilot" | "opencode_ollama";
}

function buildInputFromSpec(spec: ProxySpec, issue: number, session: string, repairCycle: number, prompt: string, worktree?: string): BuilderInput {
  if (!spec.front_id || !spec.work_branch || !spec.expected_base_sha) throw new Error("builder spec incomplete");
  return {
    repository: spec.repository,
    worktree: worktree ?? join(process.env.OPERATOR_PROXY_ROOT ?? "C:\\AI_VAULT_CODEX_BRIDGE", "worktrees", spec.front_id),
    front_id: spec.front_id,
    issue,
    base_sha: spec.expected_base_sha,
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

function validateWorktreeIdentity(worktree: string, forbiddenRoots: string[]) {
  const top = execFileSync(process.env.GIT_PATH ?? "git", ["-C", worktree, "rev-parse", "--show-toplevel"], { encoding: "utf8", timeout: 30000 }).trim();
  const resolvedTop = realpathSync(top), resolvedWorktree = realpathSync(worktree);
  if (normalize(relative(resolvedTop, resolvedWorktree)) !== ".") throw new Error("builder worktree identity mismatch");
  for (const root of forbiddenRoots) {
    if (top.toLowerCase().startsWith(root.toLowerCase())) throw new Error("builder worktree root denied");
  }
}

async function validateBuilderOutput(input: BuilderInput, result: BuilderResult, env: NodeJS.ProcessEnv): Promise<void> {
  validateWorktreeIdentity(input.worktree, FORBIDDEN_WORKTREE_ROOTS);
  const head = execFileSync(env.GIT_PATH ?? "git", ["-C", input.worktree, "rev-parse", "HEAD"], { encoding: "utf8", timeout: 30000 }).trim();
  if (head !== result.head_sha) throw new Error("builder result head mismatch");
  const committedFiles = execFileSync(env.GIT_PATH ?? "git", ["-C", input.worktree, "diff", "--name-only", `${input.base_sha}..${head}`], { encoding: "utf8", timeout: 30000 }).split(/\r?\n/).filter(Boolean);
  const workingTreeFiles = execFileSync(env.GIT_PATH ?? "git", ["-C", input.worktree, "status", "--porcelain", "--untracked-files=all"], { encoding: "utf8", timeout: 30000 }).split(/\r?\n/).filter(Boolean).map(line => line.slice(3).trim()).filter(Boolean);
  const files = [...new Set([...committedFiles, ...workingTreeFiles])];
  if (files.length === 0) throw new Error("builder produced no changes");
  const violations = scopeViolations(files, specFromInput(input));
  if (violations.length > 0) throw new Error(`builder changed forbidden paths: ${violations.join(", ")}`);
}

function recordHealth(healthDir: string, record: { backend: string; model: string; failure_class: string; attempt: number; front_id: string; base_sha: string; created_utc: string }) {
  mkdirSync(healthDir, { recursive: true });
  const path = join(healthDir, `${record.backend}-${record.attempt}-${Date.now()}.json`);
  writeFileSync(path, `${JSON.stringify(record)}\n`);
}

const ALLOWED_BACKENDS: BuilderTransport[] = ["codex_cli_openai", "opencode_github_copilot", "opencode_ollama"];

function resolveForceBackend(env: NodeJS.ProcessEnv, option?: BuilderTransport): BuilderTransport | undefined {
  if (option && ALLOWED_BACKENDS.includes(option)) return option;
  const configured = env.OPERATOR_PROXY_BUILDER_BACKEND;
  if (configured && ALLOWED_BACKENDS.includes(configured as BuilderTransport)) return configured as BuilderTransport;
  return undefined;
}

export async function routeControlPlaneBuild(spec: ProxySpec, issue: number, prompt: string, repairCycle: number, options: RouterOptions = {}, worktree?: string): Promise<BuilderResult> {
  const env = options.env ?? process.env;
  const session = `builder-${randomUUID()}`;
  const input = buildInputFromSpec(spec, issue, session, repairCycle, prompt, worktree);
  const healthDir = join(process.env.OPERATOR_PROXY_ROOT ?? "C:\\AI_VAULT_CODEX_BRIDGE", "state", "builder-health");
  validateWorktree(input.worktree, input.base_sha, FORBIDDEN_WORKTREE_ROOTS);

  const codexCfg = resolveCodexConfig(env);
  const copilotCfg = resolveCopilotConfig(spec.risk, env);
  const ollamaCfg = resolveOllamaConfig(env);

  const backends: ControlPlaneBuilderBackend[] = [
    { id: "codex_cli_openai", model: codexCfg.model, build: (i) => runCodexBuilder(i, env) },
    { id: "opencode_github_copilot", model: copilotCfg.model, build: (i) => runOpenCodeBuilder(i, copilotCfg, env) },
    { id: "opencode_ollama", model: ollamaCfg.model, build: (i) => runOpenCodeBuilder(i, ollamaCfg, env) },
  ];

  const forceBackend = resolveForceBackend(env, options.forceBackend);
  const attemptOrder = forceBackend ? backends.filter(b => b.id === forceBackend) : backends;
  let fallbackReason: string | undefined;

  for (let index = 0; index < attemptOrder.length; index++) {
    const backend = attemptOrder[index];
    const backendSession = `${session}-${backend.id}`;
    const backendInput = { ...input, session: backendSession };
    const cfg: BackendConfig = backend.id === "codex_cli_openai" ? codexCfg : backend.id === "opencode_github_copilot" ? copilotCfg : ollamaCfg;

    try {
      const result = await backend.build(backendInput);
      await validateBuilderOutput(backendInput, result, env);
      result.builder_session = session;
      result.provider_session = `${backend.id}-${randomUUID()}`;
      if (fallbackReason) result.fallback_reason = fallbackReason;
      return result;
    } catch (error) {
      const { eligible, failure_class, transient } = isEligibleFallback(error);
      recordHealth(healthDir, { backend: backend.id, model: backend.model, failure_class, attempt: index + 1, front_id: spec.front_id!, base_sha: spec.expected_base_sha, created_utc: new Date().toISOString() });

      if (!eligible) throw error;
      if (index === attemptOrder.length - 1) {
        throw new Error(`BUILDER_ROUTER_BLOCKED: ${failure_class}; attempts=${attemptOrder.map(b => b.id).join(",")}`);
      }

      if (transient && cfg.maxRetries > 0) {
        try {
          const retryResult = await backend.build({ ...backendInput, session: `${backendSession}-retry` });
          await validateBuilderOutput({ ...backendInput, session: `${backendSession}-retry` }, retryResult, env);
          retryResult.builder_session = session;
          retryResult.provider_session = `${backend.id}-${randomUUID()}`;
          if (fallbackReason) retryResult.fallback_reason = fallbackReason;
          return retryResult;
        } catch (retryError) {
          const { failure_class: retryClass } = isEligibleFallback(retryError);
          recordHealth(healthDir, { backend: backend.id, model: backend.model, failure_class: `retry:${retryClass}`, attempt: index + 1, front_id: spec.front_id!, base_sha: spec.expected_base_sha, created_utc: new Date().toISOString() });
        }
      }

      fallbackReason = failure_class;
    }
  }
  throw new Error("BUILDER_ROUTER_BLOCKED: all backends exhausted");
}

export function listBuilderBackendHealth(healthDir = join(process.env.OPERATOR_PROXY_ROOT ?? "C:\\AI_VAULT_CODEX_BRIDGE", "state", "builder-health")) {
  try {
    return readdirSync(healthDir).filter(f => f.endsWith(".json"));
  } catch {
    return [];
  }
}

export { ELIGIBLE_FALLBACK_FAILURES, INELIGIBLE_FALLBACK_FAILURES };
