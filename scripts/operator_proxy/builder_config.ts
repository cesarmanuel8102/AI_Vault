import {execFileSync} from "node:child_process";
import {existsSync} from "node:fs";
import {isAbsolute} from "node:path";

export type BuilderTransport = "codex_cli_openai" | "opencode_github_copilot" | "opencode_ollama";

const safeModelSlug = /^[a-z0-9][a-z0-9._/-]{2,127}$/;

export interface BackendConfig {
  transport: BuilderTransport;
  executable: string;
  entrypoint?: string;
  model: string;
  maxRetries: number;
}

export function resolveCodexConfig(env = process.env): BackendConfig {
  const executable = env.CODEX_PATH ?? "codex";
  const entrypoint = env.CODEX_ENTRYPOINT;
  if (entrypoint && (!isAbsolute(entrypoint) || !existsSync(entrypoint))) throw new Error("Codex entrypoint invalid");
  return { transport: "codex_cli_openai", executable, entrypoint, model: "codex-local", maxRetries: 1 };
}

function opencodeExecutable(env = process.env): string {
  if (env.OPEN_CODE_PATH) {
    if (!isAbsolute(env.OPEN_CODE_PATH) || !existsSync(env.OPEN_CODE_PATH)) throw new Error("OpenCode path invalid");
    return env.OPEN_CODE_PATH;
  }
  const candidates = [
    "C:\\Users\\cesar\\AppData\\Roaming\\npm\\node_modules\\opencode-ai\\node_modules\\opencode-windows-x64\\bin\\opencode.exe",
    "C:\\Users\\cesar\\AppData\\Roaming\\npm\\node_modules\\opencode-ai\\node_modules\\opencode-windows-x64-baseline\\bin\\opencode.exe",
  ];
  for (const c of candidates) if (existsSync(c)) return c;
  throw new Error("OpenCode executable not found");
}

export function copilotModelForRisk(risk: "LOW" | "MEDIUM" | "HIGH" | "CRITICAL", env = process.env): string {
  const configured = env.OPERATOR_PROXY_COPILOT_MODEL;
  if (configured) {
    if (!safeModelSlug.test(configured.replace(/^github-copilot\//, ""))) throw new Error("Copilot model identity invalid");
    return configured;
  }
  if (risk === "HIGH" || risk === "CRITICAL") return "github-copilot/gpt-5.6-sol";
  if (risk === "MEDIUM") return "github-copilot/gpt-5.6-terra";
  return "github-copilot/gpt-5.6-luna";
}

export function ollamaModelForBuilder(env = process.env): string {
  const configured = env.OPERATOR_PROXY_OLLAMA_BUILDER_MODEL;
  if (configured) {
    if (!safeModelSlug.test(configured.replace(/^opencode\//, ""))) throw new Error("Ollama builder model identity invalid");
    return configured;
  }
  return "opencode/kimi-k2.7-code";
}

export function resolveCopilotConfig(risk: "LOW" | "MEDIUM" | "HIGH" | "CRITICAL", env = process.env): BackendConfig {
  const executable = opencodeExecutable(env);
  const model = copilotModelForRisk(risk, env);
  return { transport: "opencode_github_copilot", executable, model, maxRetries: 1 };
}

export function resolveOllamaConfig(env = process.env): BackendConfig {
  let executable = env.OPEN_CODE_OLLAMA_PATH;
  if (executable && (!isAbsolute(executable) || !existsSync(executable))) throw new Error("Ollama OpenCode path invalid");
  if (!executable) executable = opencodeExecutable(env);
  const model = ollamaModelForBuilder(env);
  return { transport: "opencode_ollama", executable, model, maxRetries: 1 };
}

export function discoveryOpenCodeModels(executable: string, env = process.env): string[] {
  try {
    const stdout = execFileSync(executable, ["models"], { encoding: "utf8", timeout: 120000, env });
    return stdout.split(/\r?\n/).map(l => l.trim()).filter(l => l && !l.startsWith("[") && !l.startsWith("Error") && !l.startsWith("opencode"));
  } catch {
    return [];
  }
}
