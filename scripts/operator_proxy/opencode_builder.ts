import {execFileSync} from "node:child_process";
import {existsSync} from "node:fs";
import {isAbsolute} from "node:path";
import type {BackendConfig} from "./builder_config.js";
import type {BuilderInput, BuilderResult} from "./builder_backend.js";
import {BuilderBackendError} from "./builder_backend.js";
import {redactedError, redactString} from "./redaction.js";

// A governed build can legitimately run the declared contract suite after editing.
const DEFAULT_BUILD_TIMEOUT_MS = 180_000;
const MAX_BUILD_TIMEOUT_MS = 300_000;
const MIN_BUILD_TIMEOUT_MS = 1_000;

export function buildTimeoutMs(env: NodeJS.ProcessEnv): number {
  const configured = env.OPERATOR_PROXY_OPENCODE_TIMEOUT_MS;
  if (configured === undefined) return DEFAULT_BUILD_TIMEOUT_MS;
  if (!/^\d+$/.test(configured)) throw new Error("OpenCode timeout invalid");
  const value = Number(configured);
  if (!Number.isSafeInteger(value) || value < MIN_BUILD_TIMEOUT_MS || value > MAX_BUILD_TIMEOUT_MS) throw new Error("OpenCode timeout out of range");
  return value;
}

function resolveOpenCodeExecutable(env: NodeJS.ProcessEnv): string {
  if (env.OPEN_CODE_PATH) {
    if (!isAbsolute(env.OPEN_CODE_PATH) || !existsSync(env.OPEN_CODE_PATH)) throw new Error("OpenCode path invalid");
    return env.OPEN_CODE_PATH;
  }
  const localAppData = env.LOCALAPPDATA ?? "";
  const appData = env.APPDATA ?? "";
  const home = env.USERPROFILE ?? env.HOME ?? "";
  const candidates = [
    localAppData ? `${localAppData}\\opencode-ai\\bin\\opencode.exe` : "",
    appData ? `${appData}\\npm\\node_modules\\opencode-ai\\node_modules\\opencode-windows-x64\\bin\\opencode.exe` : "",
    appData ? `${appData}\\npm\\node_modules\\opencode-ai\\node_modules\\opencode-windows-x64-baseline\\bin\\opencode.exe` : "",
    home ? `${home}\\AppData\\Roaming\\npm\\node_modules\\opencode-ai\\node_modules\\opencode-windows-x64\\bin\\opencode.exe` : "",
    home ? `${home}\\AppData\\Roaming\\npm\\node_modules\\opencode-ai\\node_modules\\opencode-windows-x64-baseline\\bin\\opencode.exe` : "",
  ];
  for (const c of candidates) if (c && existsSync(c)) return c;
  throw new Error("OpenCode executable not found: set OPEN_CODE_PATH");
}

export function parseOpenCodeOutput(output: string): { headSha?: string; providerSession?: string; nativeProviderSession?: string } {
  const headMatches = [...output.matchAll(/^HEAD_SHA=([^\r\n]*)$/gm)];
  if (headMatches.length > 1) throw new Error("OpenCode builder HEAD_SHA receipt ambiguous");
  const headMatch = headMatches[0]?.[1];
  if (headMatch !== undefined && !/^[0-9a-f]{40}$/.test(headMatch)) throw new Error("OpenCode builder HEAD_SHA receipt invalid");
  const sessionMatches = [...output.matchAll(/^PROVIDER_SESSION=([^\r\n]*)$/gm)];
  if (sessionMatches.length > 1) throw new Error("OpenCode builder PROVIDER_SESSION receipt ambiguous");
  const providerSession=sessionMatches[0]?.[1];
  if(providerSession!==undefined&&!/^[a-z0-9][a-z0-9._:/-]{2,127}$/.test(providerSession))throw new Error("OpenCode builder PROVIDER_SESSION receipt invalid");
  const nativeMatches = [...output.matchAll(/^NATIVE_PROVIDER_SESSION=([^\r\n]*)$/gm)];
  if (nativeMatches.length > 1) throw new Error("OpenCode builder NATIVE_PROVIDER_SESSION receipt ambiguous");
  const nativeProviderSession=nativeMatches[0]?.[1];
  if(nativeProviderSession!==undefined&&!/^[a-z0-9][a-z0-9._:/-]{2,127}$/.test(nativeProviderSession))throw new Error("OpenCode builder NATIVE_PROVIDER_SESSION receipt invalid");
  return { headSha: headMatch, providerSession, nativeProviderSession };
}

export async function runOpenCodeBuilder(input: BuilderInput, config: BackendConfig, env: NodeJS.ProcessEnv = process.env, fallbackReason?: string): Promise<BuilderResult> {
  const started = new Date().toISOString();
  let executable = config.executable ?? resolveOpenCodeExecutable(env);
  const agent = env.OPEN_CODE_AGENT;
  let args = ["run", "--model", config.model, "--dir", input.worktree, ...(agent ? ["--agent", agent] : []), input.prompt];
  if (executable.endsWith(".js")) {
    args = [executable, ...args];
    executable = process.execPath;
  }
  let stdout = "";
  try {
    stdout = redactString(execFileSync(executable, args, {
      encoding: "utf8",
      env: { ...env, OPERATOR_PROXY_SESSION: input.session, OPERATOR_PROXY_PROVIDER_CORRELATION_ID: input.provider_correlation_id },
      timeout: buildTimeoutMs(env),
      windowsHide: true,
      maxBuffer: 32 * 1024 * 1024,
    }));
  } catch (error: any) {
    if (error?.code === "ETIMEDOUT" || error?.signal === "SIGTERM") {
      throw new BuilderBackendError("OpenCode builder transport timeout", "TRANSPORT_TIMEOUT", true);
    }
    throw new Error(redactedError(error));
  }
  const parsed = parseOpenCodeOutput(stdout);
  const override = env.OPENCODE_OVERRIDE_HEAD;
  if (override !== undefined && !/^[0-9a-f]{40}$/.test(override)) throw new Error("OpenCode override HEAD invalid");
  if (parsed.headSha && override && parsed.headSha !== override) throw new Error("OpenCode builder HEAD override conflicts with receipt");
  // Model stdout is not an authority. The supervising process derives the
  // commit identity from Git, while an optional model receipt can only agree.
  const actualHead = execFileSync(env.GIT_PATH ?? "git", ["-C", input.worktree, "rev-parse", "HEAD"], { encoding: "utf8", timeout: 30000 }).trim();
  const head = override ?? actualHead;
  if (!/^[0-9a-f]{40}$/.test(actualHead)) throw new Error("OpenCode builder HEAD invalid");
  if (parsed.headSha && parsed.headSha !== actualHead) throw new Error("OpenCode builder HEAD mismatch");
  if (!input.provider_correlation_id) throw new Error("OpenCode builder provider correlation missing");
  if (parsed.providerSession && parsed.providerSession !== input.provider_correlation_id) throw new Error("OpenCode builder provider correlation mismatch");
  return {
    executor_role: "codex_control_plane",
    builder_backend: config.transport,
    builder_model: config.model,
    builder_session: input.session,
    provider_session: input.provider_correlation_id,
    native_provider_session: parsed.nativeProviderSession,
    base_sha: input.base_sha,
    head_sha: head,
    branch: input.work_branch,
    commit: head,
    pr: 0,
    fallback_reason: fallbackReason,
    started_utc: started,
    completed_utc: new Date().toISOString(),
  };
}
