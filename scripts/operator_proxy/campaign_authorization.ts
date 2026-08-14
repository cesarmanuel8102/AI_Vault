import type {CampaignState} from "./campaign_state.js";

export type CampaignAction = "WAKE" | "HUMAN_GATE_AUTHORIZE" | "HALT" | "PAUSE" | "RESUME" | "NEXT_PHASE";

export function validateCampaignAuthorization(state: CampaignState, authorization: any): void {
  if (!authorization || typeof authorization !== "object") throw new Error("authorization missing");
  if (authorization.campaign_id !== state.campaign_id) throw new Error("authorization campaign_id mismatch");
  if (authorization.authorization_id !== state.authorization_id) throw new Error("authorization authorization_id mismatch");
  const allowed: CampaignAction[] = ["WAKE", "HUMAN_GATE_AUTHORIZE", "HALT", "PAUSE", "RESUME", "NEXT_PHASE"];
  if (!allowed.includes(authorization.action)) throw new Error("authorization action invalid");
  const owner = authorization.owner_signature;
  if (typeof owner !== "string" || !/^[0-9a-f]{64}$/.test(owner)) throw new Error("owner signature invalid");
  if (authorization.requested_utc && typeof authorization.requested_utc !== "string") throw new Error("requested_utc invalid");
}

export function createOwnerAuthorization(campaign_id: string, authorization_id: string, action: CampaignAction, reason: string): object {
  return {
    schema_version: 1,
    campaign_id,
    authorization_id,
    action,
    reason,
    owner_signature: "0".repeat(64),
    requested_utc: new Date().toISOString(),
  };
}

export function enforceHardLimits(state: CampaignState): void {
  const limits = state.hard_limits;
  if (limits.AUTO_MERGE !== false) throw new Error("hard limit violated: AUTO_MERGE");
  if (limits.LIVE_TRADING !== false) throw new Error("hard limit violated: LIVE_TRADING");
  if (limits.REAL_MONEY !== false) throw new Error("hard limit violated: REAL_MONEY");
  if (limits.CANONICAL_LOCAL_SYNC !== false) throw new Error("hard limit violated: CANONICAL_LOCAL_SYNC");
  if (limits.HUMAN_FINAL_AUTHORITY !== true) throw new Error("hard limit violated: HUMAN_FINAL_AUTHORITY");
}
