import {readFileSync} from "node:fs";
import {join} from "node:path";

export interface CatalogItem {
  id: string;
  title: string;
  status: string;
  executor: string;
  risk: string;
  deployment_mode: string;
  allowed_paths: string[];
  forbidden_paths: string[];
  acceptance: string[];
  test_commands: string[];
  dependencies?: string[];
  objective?: string;
  domain?: string;
  deliverables?: string[];
  verification_classes?: string[];
  human_gate_triggers?: string[];
  stop_conditions?: string[];
  repair_budget?: number;
  closeout?: unknown;
  jit_binding_policy?: string;
}

export interface Catalog {
  schema_version: number;
  campaign_id: string;
  roadmap_id: string;
  current_phase: string;
  hard_limits: Record<string, boolean>;
  items: CatalogItem[];
}

export interface CatalogAuditResult {
  valid: boolean;
  errors: string[];
  warnings: string[];
}

const REQUIRED_FIELDS: (keyof CatalogItem)[] = [
  "id", "title", "status", "executor", "risk", "deployment_mode",
  "allowed_paths", "forbidden_paths", "acceptance", "test_commands",
];

const OPTIONAL_SEMANTIC_FIELDS: (keyof CatalogItem)[] = [
  "objective", "dependencies", "domain", "deliverables",
  "verification_classes", "human_gate_triggers", "stop_conditions",
  "repair_budget", "closeout", "jit_binding_policy",
];

const REQUIRED_R3_TO_R19 = [
  "R3.3", "R3.4", "R3.5", "R4", "R5", "R6", "R7", "R8", "R9", "R10",
  "R11", "R12", "R13", "R14", "R15", "R16", "R17", "R18", "R19",
];

const HARD_LIMITS = ["AUTO_MERGE", "LIVE_TRADING", "REAL_MONEY", "CANONICAL_LOCAL_SYNC", "HUMAN_FINAL_AUTHORITY"];

export function loadCatalog(catalogPath: string): Catalog {
  const raw = readFileSync(catalogPath, "utf8");
  const parsed = JSON.parse(raw) as Catalog;
  if (parsed.schema_version !== 1) throw new Error("catalog schema_version invalid");
  if (!parsed.roadmap_id || !parsed.campaign_id) throw new Error("catalog identity missing");
  return parsed;
}

export function auditCatalog(catalog: Catalog): CatalogAuditResult {
  const errors: string[] = [];
  const warnings: string[] = [];

  // hard limits
  for (const limit of HARD_LIMITS) {
    const value = catalog.hard_limits?.[limit];
    if (typeof value !== "boolean") errors.push(`hard_limit ${limit} missing or not boolean`);
  }
  if (catalog.hard_limits?.AUTO_MERGE !== false) errors.push("AUTO_MERGE must be false");
  if (catalog.hard_limits?.LIVE_TRADING !== false) errors.push("LIVE_TRADING must be false");
  if (catalog.hard_limits?.REAL_MONEY !== false) errors.push("REAL_MONEY must be false");
  if (catalog.hard_limits?.CANONICAL_LOCAL_SYNC !== false) errors.push("CANONICAL_LOCAL_SYNC must be false");
  if (catalog.hard_limits?.HUMAN_FINAL_AUTHORITY !== true) errors.push("HUMAN_FINAL_AUTHORITY must be true");

  // required range
  const ids = catalog.items.map(i => i.id);
  for (const required of REQUIRED_R3_TO_R19) {
    if (!ids.includes(required)) errors.push(`missing required item ${required}`);
  }

  // uniqueness
  const seen = new Set<string>();
  for (const id of ids) {
    if (seen.has(id)) errors.push(`duplicate item id ${id}`);
    seen.add(id);
  }

  // DAG dependencies
  const itemSet = new Set(ids);
  const visited = new Set<string>();
  const visiting = new Set<string>();
  function visit(id: string, path: string[]): void {
    if (visiting.has(id)) {
      errors.push(`dependency cycle: ${[...path, id].join(" -> ")}`);
      return;
    }
    if (visited.has(id)) return;
    if (!itemSet.has(id)) {
      errors.push(`dependency references unknown item ${id}`);
      return;
    }
    visiting.add(id);
    const item = catalog.items.find(i => i.id === id)!;
    for (const dep of item.dependencies ?? []) visit(dep, [...path, id]);
    visiting.delete(id);
    visited.add(id);
  }
  for (const id of ids) visit(id, []);

  // phase gaps and ordering
  const numericIds = ids.map(id => {
    const m = id.match(/^R(\d+)(?:\.(\d+))?$/);
    if (!m) return null;
    return {id, major: Number.parseInt(m[1], 10), minor: Number.parseInt(m[2] ?? "0", 10)};
  }).filter((x): x is {id: string; major: number; minor: number} => x !== null);
  numericIds.sort((a, b) => a.major - b.major || a.minor - b.minor);
  for (let i = 1; i < numericIds.length; i++) {
    const prev = numericIds[i - 1];
    const cur = numericIds[i];
    if (cur.major === prev.major) {
      if (cur.minor !== prev.minor + 1) errors.push(`phase gap between ${prev.id} and ${cur.id}`);
    } else if (cur.major !== prev.major + 1) {
      errors.push(`phase gap between ${prev.id} and ${cur.id}`);
    }
  }

  // active items
  const active = catalog.items.filter(i => i.status === "AUTHORIZED_ACTIVE");
  if (active.length > 1) errors.push(`multiple AUTHORIZED_ACTIVE items: ${active.map(i => i.id).join(", ")}`);
  const plannedLocked = catalog.items.filter(i => i.status === "PLANNED_LOCKED");
  const planned = catalog.items.filter(i => i.status === "PLANNED");
  if (planned.length > 0 && plannedLocked.length > 0) {
    warnings.push(`mixed PLANNED and PLANNED_LOCKED statuses`);
  }

  // per-item contract completeness
  for (const item of catalog.items) {
    for (const field of REQUIRED_FIELDS) {
      const value = item[field];
      if (value === undefined || (Array.isArray(value) && value.length === 0)) {
        errors.push(`${item.id}: required field ${field} missing or empty`);
      }
    }
    for (const field of OPTIONAL_SEMANTIC_FIELDS) {
      if (item[field] === undefined) errors.push(`${item.id}: semantic field ${field} missing`);
    }
    if (!["LOW", "MEDIUM", "HIGH", "CRITICAL"].includes(item.risk)) {
      errors.push(`${item.id}: risk invalid`);
    }
    if (!["NO_DEPLOY", "INSTALL_ONLY", "INSTALL_AND_RUNTIME_PILOT", "DOCUMENTATION_CLOSEOUT"].includes(item.deployment_mode)) {
      errors.push(`${item.id}: deployment_mode invalid`);
    }
    if (item.repair_budget !== undefined && (!Number.isInteger(item.repair_budget) || item.repair_budget < 0)) {
      errors.push(`${item.id}: repair_budget invalid`);
    }
  }

  return {valid: errors.length === 0, errors, warnings};
}

export function auditCatalogFile(catalogPath: string): CatalogAuditResult {
  const catalog = loadCatalog(catalogPath);
  return auditCatalog(catalog);
}
