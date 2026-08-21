import type {Risk,ReviewerOutput} from "./types.js";

export interface ReviewerInput {
  repository:string;
  repositoryRoot:string;
  pr:number;
  baseSha:string;
  headSha:string;
  risk:Risk;
  changedFiles:string[];
  builderSession:string;
  builderModel?:string;
  panelEvidence?:unknown;
}

export interface ReviewerAttempt {
  output:ReviewerOutput;
  backend:"opencode_ollama";
  model:string;
  session:string;
  providerSession:string;
  startedUtc:string;
  completedUtc:string;
}

export interface ReviewerRun extends ReviewerAttempt {
  schema_version:1;
  review_mode?:"single-deepseek-pro";
  receipt_key:string;
  evidence_sha256:string;
  identity:{repository:string;pr:number;baseSha:string;headSha:string;risk:Risk;changedFiles:string[];builderSession:string;builderModel:string|null};
  primary_output:ReviewerOutput;
  attempts:{model:string;session:string;status:"PASS"|"FAILED";failure_class?:string}[];
  verifier?:{model:string;session:string;providerSession:string;verdict:string;output:ReviewerOutput};
  arbiter?:{model:string;session:string;providerSession:string;verdict:string;output:ReviewerOutput};
}

export interface ReviewerBackend {
  readonly model:string;
  review(input:ReviewerInput,session:string):ReviewerAttempt;
}

export class ReviewerBackendError extends Error {
  constructor(message:string,readonly failureClass:string,readonly transient=false){super(message);this.name="ReviewerBackendError";}
}
