import {execFileSync} from "node:child_process";
import {existsSync} from "node:fs";
import {isAbsolute} from "node:path";
import type {BuilderInput, BuilderTransportInput, BuilderResult} from "./builder_backend.js";
import type {BackendConfig} from "./builder_config.js";
import {redactedError, redactString} from "./redaction.js";

export function builderInvocation(codex: string, entrypoint = process.env.CODEX_ENTRYPOINT): { file: string; prefix: string[] } {
  if (!entrypoint) return { file: codex, prefix: [] };
  if (!isAbsolute(entrypoint) || !existsSync(entrypoint)) throw new Error("Codex entrypoint invalid");
  return { file: codex, prefix: [entrypoint, "-c", 'service_tier="fast"', "-c", 'model_reasoning_effort="high"'] };
}

export function parseCodexOutput(output: string): { headSha?: string; providerSession?: string; nativeProviderSession?: string } {
  const headMatch = output.match(/HEAD_SHA=([0-9a-f]{40})/);
  const sessionMatches = [...output.matchAll(/^PROVIDER_SESSION=([^\r\n]*)$/gm)];
  if (sessionMatches.length > 1) throw new Error("Codex builder PROVIDER_SESSION receipt ambiguous");
  const providerSession=sessionMatches[0]?.[1];
  if(providerSession!==undefined&&!/^[a-z0-9][a-z0-9._:/-]{2,127}$/.test(providerSession))throw new Error("Codex builder PROVIDER_SESSION receipt invalid");
  const nativeMatches = [...output.matchAll(/^NATIVE_PROVIDER_SESSION=([^\r\n]*)$/gm)];
  if (nativeMatches.length > 1) throw new Error("Codex builder NATIVE_PROVIDER_SESSION receipt ambiguous");
  const nativeProviderSession=nativeMatches[0]?.[1];
  if(nativeProviderSession!==undefined&&!/^[a-z0-9][a-z0-9._:/-]{2,127}$/.test(nativeProviderSession))throw new Error("Codex builder NATIVE_PROVIDER_SESSION receipt invalid");
  return { headSha: headMatch?.[1], providerSession, nativeProviderSession };
}

export async function runCodexBuilder(input: BuilderTransportInput|BuilderInput, config: BackendConfig, env: NodeJS.ProcessEnv = process.env): Promise<BuilderResult> {
  if (config.transport !== "codex_cli_openai" || !/^[a-z0-9][a-z0-9._/-]{2,127}$/.test(config.model)) throw new Error("Codex builder configuration invalid");
  const codex = env.CODEX_PATH ?? (env.CODEX_ENTRYPOINT ? process.execPath : "codex");
  const invocation = builderInvocation(codex, env.CODEX_ENTRYPOINT);
  const started = new Date().toISOString();
  let stdout = "";
  try {
    stdout = redactString(execFileSync(invocation.file, [...invocation.prefix, "--model", config.model, "exec", "--full-auto", "-C", input.worktree, input.prompt], {
      encoding: "utf8",
      env: { ...env, OPERATOR_PROXY_SESSION: input.session, OPERATOR_PROXY_PROVIDER_CORRELATION_ID: input.provider_correlation_id, ...(input.logical_attempt_id?{OPERATOR_PROXY_BUILD_ATTEMPT_ID:input.logical_attempt_id}:{}) },
      timeout: 900000,
      windowsHide: true,
      maxBuffer: 32 * 1024 * 1024,
    }));
  } catch (error) {
    throw new Error(redactedError(error));
  }
  const parsed = parseCodexOutput(stdout);
  const head = parsed.headSha ?? env.CODEX_OVERRIDE_HEAD;
  if (!head || !/^[0-9a-f]{40}$/.test(head)) throw new Error("Codex builder did not produce HEAD_SHA");
  if (!input.provider_correlation_id) throw new Error("Codex builder provider correlation missing");
  if (parsed.providerSession !== input.provider_correlation_id) throw new Error("Codex builder provider correlation mismatch");
  return {
    executor_role: "codex_control_plane",
    builder_backend: "codex_cli_openai",
    builder_model: config.model,
    builder_session: input.session,
    provider_session: parsed.providerSession,
    native_provider_session: parsed.nativeProviderSession,
    base_sha: input.base_sha,
    head_sha: head,
    branch: input.work_branch,
    commit: head,
    pr: 0,
    started_utc: started,
    completed_utc: new Date().toISOString(),
  };
}
