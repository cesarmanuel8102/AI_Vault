import {createHash} from "node:crypto";

const PRIVATE_KEY=/-----BEGIN(?: [A-Z0-9]+)? PRIVATE KEY-----[\s\S]*?-----END(?: [A-Z0-9]+)? PRIVATE KEY-----/gi;
const URL_CREDENTIALS=/\b([a-z][a-z0-9+.-]*:\/\/)([^\s/:@]+):([^\s/@]+)@/gi;
const AUTHORIZATION=/\b(authorization\s*[:=]\s*)[^\r\n,;]+/gi;
const BEARER=/\bbearer\s+[A-Za-z0-9._~+\/-]+=*/gi;
const TOKENS=/\b(?:ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|sk-[A-Za-z0-9_-]{16,})\b/g;
const ASSIGNMENTS=/\b([A-Za-z][A-Za-z0-9_-]*(?:api[_-]?key|password|passwd|client[_-]?secret|access[_-]?token|refresh[_-]?token|connection[_-]?string)|api[_-]?key|password|passwd|client[_-]?secret|access[_-]?token|refresh[_-]?token|connection[_-]?string)\s*[:=]\s*(?:"[^"]*"|'[^']*'|[^\s,;]+)/gi;
const CONNECTION_PASSWORD=/\b(password|pwd)=[^;\s]+/gi;
const SENSITIVE_KEY=/^(?:authorization|api[_-]?key|password|passwd|client[_-]?secret|access[_-]?token|refresh[_-]?token|connection[_-]?string|private[_-]?key)$/i;

export function redactString(value:string):string {
  return value
    .replace(PRIVATE_KEY,"[REDACTED:PRIVATE_KEY]")
    .replace(URL_CREDENTIALS,"$1[REDACTED:TOKEN]@")
    .replace(AUTHORIZATION,"$1[REDACTED:TOKEN]")
    .replace(BEARER,"Bearer [REDACTED:TOKEN]")
    .replace(TOKENS,"[REDACTED:TOKEN]")
    .replace(ASSIGNMENTS,(_match,key)=>`${key}=[REDACTED:${/pass/i.test(key)?"PASSWORD":"TOKEN"}]`)
    .replace(CONNECTION_PASSWORD,(_match,key)=>`${key}=[REDACTED:PASSWORD]`);
}

export function redactSensitiveData<T>(value:T):T {
  if(typeof value==="string")return redactString(value) as T;
  if(Array.isArray(value))return value.map(redactSensitiveData) as T;
  if(value&&typeof value==="object"){
    const output:Record<string,unknown>={};
    for(const [key,item] of Object.entries(value as Record<string,unknown>))output[key]=SENSITIVE_KEY.test(key)?(/pass/i.test(key)?"[REDACTED:PASSWORD]":"[REDACTED:TOKEN]"):redactSensitiveData(item);
    return output as T;
  }
  return value;
}

export function containsSensitiveData(value:unknown):boolean {return JSON.stringify(redactSensitiveData(value))!==JSON.stringify(value);}
export function safeJson(value:unknown):string {return JSON.stringify(redactSensitiveData(value));}
export function redactedCorrelation(value:unknown){const normalized=safeJson(value);return {sha256:createHash("sha256").update(normalized).digest("hex"),redacted:true};}
export function redactedError(error:unknown):string {const value=error as {message?:unknown;stdout?:unknown;stderr?:unknown};return redactString([value?.message,value?.stdout,value?.stderr].filter(x=>x!==undefined).map(String).join("\n")||String(error));}
