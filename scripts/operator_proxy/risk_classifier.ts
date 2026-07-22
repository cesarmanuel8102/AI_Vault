import type {ProxySpec,Risk} from "./types.js";
const critical=[/secret/i,/credential/i,/permission/i,/auth/i,/branch protection/i,/force.push/i,/trading/i,/IBKR/i,/real.money/i,/fund/i,/canonical/i,/FAISS/i];
export function classify(spec:ProxySpec):Risk {const text=[...spec.allowed_paths,...spec.acceptance].join(" ");return critical.some(x=>x.test(text))?"CRITICAL":spec.risk;}
