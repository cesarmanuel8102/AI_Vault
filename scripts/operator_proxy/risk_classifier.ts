import type {ProxySpec,Risk} from "./types.js";

const criticalPathPatterns = [
  /(^|\/)\.env(?:[._/-]|$)/i,
  /(^|\/)[^/]*(?:secret|credential|api[-_]?key|password|private[-_]?key|access[-_]?token)[^/]*(?:\/|$)/i,
  /(^|\/)(?:auth|authentication|authorization|permissions?|access[-_]?control)(?:[._/-]|$)/i,
  /(^|\/)\.github\/(?:CODEOWNERS|workflows\/)/i,
  /(^|\/)scripts\/operator_proxy(?:\/|$)/i,
  /(^|\/)(?:install|deploy|repair)[^/]*\.(?:ps1|py|ts|js)$/i,
  /(^|\/)(?:[^/]*[._-])?(?:trading|financial[_-]?autonomy|broker|ibkr|faiss)(?:[._/-]|$)/i,
  /(^|\/)memory\/semantic(?:\/|$)/i,
  /(^|\/)canonical(?:\/|$)/i,
];

const criticalConceptPatterns = [
  /\bsecrets?\b/i,
  /\bcredentials?\b/i,
  /\bauthentication\b/i,
  /\bauth\b/i,
  /\b(?:OAuth|SSO|RBAC|ACL)\b/i,
  /\b(?:API[- ]?key|access[- ]?token|private[- ]?key|password)\b/i,
  /\bpermissions?\s+(?:changes?|updates?|modifications?)\b/i,
  /\b(?:changes?|changed|changing|updates?|updated|updating|modify|modifies|modified|modifying)\s+(?:the\s+)?permissions?\b/i,
  /\bauthorization\s+(?:polic(?:y|ies)|rules?|gates?|models?)\b/i,
  /\b(?:changes?|changed|changing|updates?|updated|updating|modify|modifies|modified|modifying)\s+(?:the\s+)?authorization\s+(?:polic(?:y|ies)|rules?|gates?|models?)\b/i,
  /\bbranch\s+protection\b/i,
  /\bGitHub\s+Actions?\s+(?:workflow|permission|token)\b/i,
  /\bconstitutional\s+authority\s+(?:change|update|modification)\b/i,
  /\b(?:changes?|changed|changing|updates?|updated|updating|modify|modifies|modified|modifying)\s+(?:the\s+)?constitutional\s+authority\b/i,
  /\baccess[- ]control\s+(?:change|update|modification)\b/i,
  /\b(?:changes?|changed|changing|updates?|updated|updating|modify|modifies|modified|modifying)\s+(?:the\s+)?access[- ]control\b/i,
  /\bforce[- ]?push\b/i,
  /\b(?:production\s+(?:deploy|deployment)|deploy(?:ment)?\s+to\s+production)\b/i,
  /\b(?:enable[sd]?|enabling|disable[sd]?|disabling|modify|modifies|modified|modifying)\s+(?:the\s+)?scheduled\s+task\b/i,
  /\b(?:UAC|administrator|administrative\s+privilege)\b/i,
  /\b(?:enable|execute|activate)\s+(?:live|real[- ]money)\s+trading\b/i,
  /\b(?:production\s+broker|IBKR|real[- ]money|real\s+capital)\b/i,
  /\b(?:changes?|changed|changing|increases?|increased|increasing|modify|modifies|modified|modifying)\s+(?:financial|risk|capital)\s+limits?\b/i,
  /\bcanonical(?:\s+local)?\s+(?:syncs?|syncing|access|writes?|writing|mutations?)\b/i,
  /\bFAISS\s+(?:writes?|writing|rebuilds?|rebuilding|mutations?)\b/i,
];

export function classify(spec:ProxySpec):Risk {
  if(spec.allowed_paths.some(path=>criticalPathPatterns.some(pattern=>pattern.test(path))))return "CRITICAL";
  const acceptance=spec.acceptance.join(" ");
  return criticalConceptPatterns.some(pattern=>pattern.test(acceptance))?"CRITICAL":spec.risk;
}
