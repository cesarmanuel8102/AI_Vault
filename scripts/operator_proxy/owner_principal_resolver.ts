import {readFileSync} from "node:fs";
import type {CampaignAuthorization,OwnerAuthoritySources,RepositoryAuthorization} from "./types.js";

const exactKeys=(value:Record<string,unknown>,keys:readonly string[])=>Object.keys(value).length===keys.length&&keys.every(key=>Object.hasOwn(value,key));
const principal=(value:unknown):value is string=>typeof value==="string"&&value.trim()===value&&value.length>0;
const repositoryRecord=(value:unknown,repository:string):RepositoryAuthorization=>{
  if(!value||typeof value!=="object"||Array.isArray(value)||!exactKeys(value as Record<string,unknown>,["schema_version","repository","owner_principal"]))throw new Error("owner authority invalid");
  const record=value as Record<string,unknown>;
  if(record.schema_version!==1)throw new Error("owner authority invalid");
  if(record.repository!==repository)throw new Error("owner authority repository mismatch");
  if(!principal(record.owner_principal))throw new Error("owner authority principal invalid");
  return {repository,owner_principal:record.owner_principal};
};

export function loadRepositoryAuthorization(path:string,repository:string):RepositoryAuthorization {
  let source:string;
  try{source=readFileSync(path,"utf8");}catch{throw new Error("owner authority missing");}
  let parsed:unknown;
  try{parsed=JSON.parse(source);}catch{throw new Error("owner authority json invalid");}
  return repositoryRecord(parsed,repository);
}

const validCampaign=(candidate:unknown,authorizationId:string,repository:string):candidate is CampaignAuthorization=>{
  if(!candidate||typeof candidate!=="object"||Array.isArray(candidate))return false;
  const value=candidate as Record<string,unknown>;
  return value.authorization_id===authorizationId&&value.repository===repository&&principal(value.owner_principal);
};
const validRepository=(candidate:unknown,repository:string):candidate is RepositoryAuthorization=>{
  if(!candidate||typeof candidate!=="object"||Array.isArray(candidate))return false;
  const value=candidate as Record<string,unknown>;
  return value.repository===repository&&principal(value.owner_principal);
};

export function resolveOwnerPrincipal(spec:Pick<CampaignAuthorization,"authorization_id"|"repository">,sources:OwnerAuthoritySources):string {
  if(!Array.isArray(sources?.campaign_candidates)||!Array.isArray(sources?.repository_candidates))throw new Error("owner authority invalid");
  const campaigns=sources.campaign_candidates;
  const repositories=sources.repository_candidates;
  if(campaigns.length>1||repositories.length>1)throw new Error("owner authority ambiguous");
  if(campaigns.length===1&&!validCampaign(campaigns[0],spec.authorization_id,spec.repository))throw new Error("owner authority invalid");
  if(repositories.length===1&&!validRepository(repositories[0],spec.repository))throw new Error("owner authority invalid");
  const campaign=campaigns[0];
  const repository=repositories[0];
  if(campaign){
    if(repository&&campaign.owner_principal!==repository.owner_principal)throw new Error("owner authority disagreement");
    return campaign.owner_principal;
  }
  if(repository)return repository.owner_principal;
  throw new Error("owner authority missing");
}
