import type {ProxySpec,Risk} from "./types.js";

const criticalPathPatterns = [
  /(^|\/)(?:\.env|secrets?|credentials?)(?:\/|$)/i,
  /(^|\/)(?:auth|authentication|permissions?|access[-_]?control)(?:\/|$)/i,
  /(^|\/)\.github\/(?:CODEOWNERS|workflows\/.*branch.*protection)/i,
  /(^|\/)(?:trading|financial_autonomy|broker|ibkr|faiss)(?:\/|$)/i,
  /(^|\/)memory\/semantic(?:\/|$)/i,
  /(^|\/)canonical(?:\/|$)/i,
];

const criticalConceptPatterns = [
  /\bsecrets?\b/i,
  /\bcredentials?\b/i,
  /\bauthentication\b/i,
  /\bpermissions?\s+(?:change|update|modification)\b/i,
  /\b(?:change|update|modify)\s+(?:the\s+)?permissions?\b/i,
  /\bauthorization\s+(?:policy|rule|gate|model)\b/i,
  /\bbranch\s+protection\b/i,
  /\bconstitutional\s+authority\s+(?:change|update|modification)\b/i,
  /\b(?:change|update|modify)\s+(?:the\s+)?constitutional\s+authority\b/i,
  /\baccess[- ]control\s+(?:change|update|modification)\b/i,
  /\b(?:change|update|modify)\s+(?:the\s+)?access[- ]control\b/i,
  /\bforce[- ]?push\b/i,
  /\b(?:enable|execute|activate)\s+(?:live|real[- ]money)\s+trading\b/i,
  /\b(?:production\s+broker|IBKR|real[- ]money|real\s+capital)\b/i,
  /\b(?:change|increase|modify)\s+(?:financial|risk|capital)\s+limits?\b/i,
  /\bcanonical(?:\s+local)?\s+(?:sync|access|write|mutation)\b/i,
  /\bFAISS\s+(?:write|rebuild|mutation)\b/i,
];

export function classify(spec:ProxySpec):Risk {
  if(spec.allowed_paths.some(path=>criticalPathPatterns.some(pattern=>pattern.test(path))))return "CRITICAL";
  const acceptance=spec.acceptance.join(" ");
  return criticalConceptPatterns.some(pattern=>pattern.test(acceptance))?"CRITICAL":spec.risk;
}
