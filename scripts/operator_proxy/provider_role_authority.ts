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

const safeId = /^[a-z0-9][a-z0-9._:/-]{2,127}$/;

export function validateProviderSession(role: ProviderRole, model: string, provider_session: unknown, auditLog: FallbackAuditRecord[]): void {
  if (!safeId.test(model)) throw new Error("model identity invalid");
  const session = provider_session as ProviderSession | undefined;
  if (!session || typeof session !== "object") throw new Error("provider session invalid");
  if (!safeId.test(session.provider) || !safeId.test(session.model) || !/^[a-z0-9][a-z0-9._:/-]{2,255}$/.test(session.session_id)) throw new Error("provider session identity malformed");
  if (role === "builder" || role === "reviewer") {
    const supervisorProvider = auditLog.find(x => x.from_backend === "supervisor" || x.to_backend === session.provider);
    if (supervisorProvider || session.provider === "owner-vault" || session.provider.startsWith("owner/")) throw new Error("builder/reviewer session must not equal owner or supervisor session");
  }
  if (role === "owner" && session.provider.includes("builder")) throw new Error("owner session must not alias builder provider");
  if (role === "supervisor" && session.provider.includes("builder")) throw new Error("supervisor session must not alias builder provider");
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
