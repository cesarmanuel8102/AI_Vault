import {ollamaModelForBuilder} from "./builder_config.js";
import {REVIEWER_MODELS, REVIEWER_QUALIFICATION} from "./reviewer_config.js";

export type ProviderRole = "builder" | "reviewer" | "supervisor" | "arbiter" | "owner";

export interface ProviderSession {
  provider: string;
  model: string;
  session_id: string;
}

export interface FallbackAuditRecord {
  schema_version: 1;
  failure_class: string;
  from_backend: string;
  to_backend: string;
  reason: string;
  timestamp_utc: string;
}

export interface ProviderRoleRegistry {
  ownerIdentity(): string;
  supervisorIdentity(): string;
  builderIdentity(): string;
  qualifiedReviewerModels(): string[];
  qualifiedFallbackModels(): string[];
  isOwnerIdentity(provider: string): boolean;
  isSupervisorIdentity(provider: string): boolean;
  isBuilderIdentity(provider: string): boolean;
  isQualifiedReviewer(model: string): boolean;
  isQualifiedFallback(model: string): boolean;
}

const safeId = /^[a-z0-9][a-z0-9._:/-]{2,127}$/;

export function defaultProviderRoleRegistry(env = process.env): ProviderRoleRegistry {
  const ownerModel = env.OPERATOR_PROXY_OWNER_MODEL ?? "owner-vault/owner";
  const supervisorModel = env.OPERATOR_PROXY_SUPERVISOR_MODEL ?? "codex_cli_openai/codex-supervisor";
  const builderModel = ollamaModelForBuilder(env);
  const qualifiedReviewers = Object.entries(REVIEWER_QUALIFICATION)
    .filter(([, q]) => q.qualified)
    .map(([model]) => model);
  const fallbackPool: string[] = [
    REVIEWER_MODELS.deepseekPro,
    REVIEWER_MODELS.deepseekFlash,
    REVIEWER_MODELS.nemotron,
  ].filter(model => REVIEWER_QUALIFICATION[model as keyof typeof REVIEWER_QUALIFICATION].qualified);

  return {
    ownerIdentity: () => ownerModel,
    supervisorIdentity: () => supervisorModel,
    builderIdentity: () => builderModel,
    qualifiedReviewerModels: () => [...qualifiedReviewers],
    qualifiedFallbackModels: () => [...fallbackPool],
    isOwnerIdentity: (provider: string) => provider === ownerModel || provider === ownerModel.split("/")[0],
    isSupervisorIdentity: (provider: string) => provider === supervisorModel || provider === supervisorModel.split("/")[0],
    isBuilderIdentity: (provider: string) => provider === builderModel || provider === builderModel.split("/")[0],
    isQualifiedReviewer: (model: string) => qualifiedReviewers.includes(model),
    isQualifiedFallback: (model: string) => fallbackPool.includes(model),
  };
}

export function validateProviderSession(
  role: ProviderRole,
  model: string,
  provider_session: unknown,
  auditLog: FallbackAuditRecord[],
  registry: ProviderRoleRegistry = defaultProviderRoleRegistry(),
): void {
  if (!safeId.test(model)) throw new Error("model identity invalid");
  const session = provider_session as ProviderSession | undefined;
  if (!session || typeof session !== "object") throw new Error("provider session invalid");
  if (!safeId.test(session.provider) || !safeId.test(session.model) || !/^[a-z0-9][a-z0-9._:/-]{2,255}$/.test(session.session_id)) {
    throw new Error("provider session identity malformed");
  }

  const supervisorProvider = auditLog.find(x => registry.isSupervisorIdentity(x.from_backend) || registry.isSupervisorIdentity(x.to_backend));
  if (role === "builder" || role === "reviewer") {
    if (supervisorProvider || registry.isOwnerIdentity(session.provider) || registry.isSupervisorIdentity(session.provider)) {
      throw new Error("builder/reviewer session must not equal owner or supervisor session");
    }
    if (role === "reviewer" && !registry.isQualifiedReviewer(session.model)) {
      throw new Error("reviewer model not in qualified pool");
    }
  }
  if (role === "owner" && registry.isBuilderIdentity(session.provider)) {
    throw new Error("owner session must not alias builder provider");
  }
  if (role === "supervisor" && registry.isBuilderIdentity(session.provider)) {
    throw new Error("supervisor session must not alias builder provider");
  }
  if (role === "arbiter" && !registry.isQualifiedFallback(session.model)) {
    throw new Error("arbiter model not in qualified fallback pool");
  }
}

export function auditFallback(failureClass: string, fromBackend: string, toBackend: string, reason: string): FallbackAuditRecord {
  return {
    schema_version: 1,
    failure_class: failureClass,
    from_backend: fromBackend,
    to_backend: toBackend,
    reason,
    timestamp_utc: new Date().toISOString(),
  };
}
