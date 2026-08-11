import {execFileSync} from "node:child_process";
import {existsSync} from "node:fs";
import {isAbsolute} from "node:path";
import type {BackendConfig} from "./builder_config.js";
import type {BuilderInput, BuilderResult} from "./builder_backend.js";
import {redactedError, redactString} from "./redaction.js";

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

export function parseOpenCodeOutput(output: string): { headSha?: string; providerSession?: string } {
  const headMatches = [...output.matchAll(/^HEAD_SHA=([^\r\n]*)$/gm)];
  if (headMatches.length > 1) throw new Error("OpenCode builder HEAD_SHA receipt ambiguous");
  const headMatch = headMatches[0]?.[1];
  if (headMatch !== undefined && !/^[0-9a-f]{40}$/.test(headMatch)) throw new Error("OpenCode builder HEAD_SHA receipt invalid");
  const sessionMatches = [...output.matchAll(/^PROVIDER_SESSION=([^\r\n]*)$/gm)];
  if (sessionMatches.length > 1) throw new Error("OpenCode builder PROVIDER_SESSION receipt ambiguous");
  const providerSession=sessionMatches[0]?.[1];
  if(providerSession!==undefined&&!/^[a-z0-9][a-z0-9._:/-]{2,127}$/.test(providerSession))throw new Error("OpenCode builder PROVIDER_SESSION receipt invalid");
  return { headSha: headMatch, providerSession };
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
      env: { ...env, OPERATOR_PROXY_SESSION: input.session },
      timeout: 900000,
      windowsHide: true,
      maxBuffer: 32 * 1024 * 1024,
    }));
  } catch (error) {
    throw new Error(redactedError(error));
  }
  const parsed = parseOpenCodeOutput(stdout);
  const override = env.OPENCODE_OVERRIDE_HEAD;
  if (override !== undefined && !/^[0-9a-f]{40}$/.test(override)) throw new Error("OpenCode override HEAD invalid");
  if (parsed.headSha && override && parsed.headSha !== override) throw new Error("OpenCode builder HEAD override conflicts with receipt");
  const head = parsed.headSha ?? override;
  if (!head || !/^[0-9a-f]{40}$/.test(head)) throw new Error("OpenCode builder did not produce HEAD_SHA");
  const actualHead = execFileSync(env.GIT_PATH ?? "git", ["-C", input.worktree, "rev-parse", "HEAD"], { encoding: "utf8", timeout: 30000 }).trim();
  if (actualHead !== head) throw new Error("OpenCode builder HEAD mismatch");
  return {
    executor_role: "codex_control_plane",
    builder_backend: config.transport,
    builder_model: config.model,
    builder_session: input.session,
    provider_session: parsed.providerSession ?? `${config.transport}-${input.session}`,
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
