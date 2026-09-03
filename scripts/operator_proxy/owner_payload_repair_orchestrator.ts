/**
 * Durable coordinator for the exceptional Owner-authorized build. Domain
 * ports own validation and persistence; this class only orders those actions.
 */
export interface OwnerRepairState {
  state: "BLOCKED"|"OWNER_REPAIR_AUTHORIZED"|"BUILDING"|"CI_PENDING";
  last_error?: string;
  repair_cycles: number;
  head_sha?: string;
  base_sha: string;
  owner_payload_repair?: {grant_key:string;consumed_event_sha256:string;build_attempt_id:string};
}

type Grant = {grant_key:string; authorization_id:string; front_id:string; failed_head_sha:string};
type Consumed = {phase:"CONSUMED"; event_sha256:string; build_attempt_id:string};
type Dispatched = {phase:"BUILD_DISPATCHED"; event_sha256:string; predecessor_event_sha256:string; build_attempt_id:string};
type HeadBound = {phase:"HEAD_BOUND"; event_sha256:string; predecessor_event_sha256:string; build_attempt_id:string; new_head_sha:string};
type ReceiptView = {phase:"VERIFIED"}|Consumed|Dispatched|HeadBound;
type Candidate = {new_head_sha:string; provenance:{authorization_id:string;grant_key:string;build_attempt_id:string;consumed_event_sha256:string}};

export interface OwnerPayloadRepairOrchestrationPorts {
  verify(state:OwnerRepairState): Grant;
  receipt: {
    view(grantKey:string): ReceiptView|undefined;
    verified(grant:Grant): {phase:"VERIFIED"};
    consumed(grantKey:string): Consumed;
    dispatched(grantKey:string): Dispatched;
    headBound(grantKey:string,head:string): void;
  };
  lifecycle: {
    authorize(state:OwnerRepairState,receipt:Consumed): OwnerRepairState;
    begin(state:OwnerRepairState,receipt:Consumed): OwnerRepairState;
    adopt(state:OwnerRepairState,candidate:Candidate): OwnerRepairState;
  };
  authorizeTransport(receipt:Dispatched): {build_attempt_id:string};
  /** Finds an already-published exact candidate before any at-least-once redelivery. */
  findPublishedCandidate?(state:OwnerRepairState,receipt:Dispatched): Promise<Candidate|undefined>|Candidate|undefined;
  dispatch(capability:{build_attempt_id:string}): Promise<Candidate>|Candidate;
  verifyLineage(candidate:Candidate): boolean;
  /** Reconciles a durably published head without re-delivering the provider call. */
  reconcileHeadBound?(state:OwnerRepairState,receipt:HeadBound): Promise<OwnerRepairState>|OwnerRepairState;
}

export class OwnerPayloadRepairOrchestrator {
  constructor(readonly ports:OwnerPayloadRepairOrchestrationPorts) {}

  async resume(state:OwnerRepairState): Promise<OwnerRepairState> {
    if (state.repair_cycles !== 2) throw new Error("owner repair lifecycle denied");
    if (state.state === "CI_PENDING") return state;
    if (!state.head_sha) throw new Error("owner repair lifecycle denied");
    if (state.state === "BLOCKED" && state.last_error !== "CI_FAILED") throw new Error("owner repair lifecycle denied");

    const grant = this.ports.verify(state);
    if (grant.failed_head_sha !== state.head_sha) throw new Error("owner repair grant head mismatch");
    let view = this.ports.receipt.view(grant.grant_key);
    if (!view) view = this.ports.receipt.verified(grant);
    if (view.phase === "VERIFIED") view = this.ports.receipt.consumed(grant.grant_key);
    if (view.phase === "HEAD_BOUND") {
      if (!this.ports.reconcileHeadBound) throw new Error("owner repair head-bound recovery unavailable");
      const recovered=await this.ports.reconcileHeadBound(state,view);
      if(recovered.state!=="CI_PENDING"||recovered.repair_cycles!==2||recovered.head_sha!==view.new_head_sha)throw new Error("owner repair head-bound recovery invalid");
      return recovered;
    }
    if (view.phase !== "CONSUMED" && view.phase !== "BUILD_DISPATCHED") throw new Error("owner repair receipt phase invalid");
    const consumed = view.phase === "CONSUMED" ? view : {phase:"CONSUMED" as const,event_sha256:view.predecessor_event_sha256,build_attempt_id:view.build_attempt_id};

    if (state.state === "BLOCKED") state = this.ports.lifecycle.authorize(state,consumed);
    if (state.state === "OWNER_REPAIR_AUTHORIZED") state = this.ports.lifecycle.begin(state,consumed);
    const dispatched = view.phase === "BUILD_DISPATCHED" ? view : this.ports.receipt.dispatched(grant.grant_key);
    if (dispatched.predecessor_event_sha256 !== consumed.event_sha256 || dispatched.build_attempt_id !== consumed.build_attempt_id) throw new Error("owner repair receipt chain invalid");

    let candidate=await this.ports.findPublishedCandidate?.(state,dispatched);
    if(!candidate){
      const capability = this.ports.authorizeTransport(dispatched);
      if (capability.build_attempt_id !== consumed.build_attempt_id) throw new Error("owner repair transport capability invalid");
      candidate = await this.ports.dispatch(capability);
    }
    if (candidate.provenance.authorization_id !== grant.authorization_id || candidate.provenance.grant_key !== grant.grant_key || candidate.provenance.build_attempt_id !== consumed.build_attempt_id || candidate.provenance.consumed_event_sha256 !== consumed.event_sha256) throw new Error("owner repair provenance invalid");
    if (!this.ports.verifyLineage(candidate)) throw new Error("owner repair lineage denied");
    this.ports.receipt.headBound(grant.grant_key,candidate.new_head_sha);
    const adopted = this.ports.lifecycle.adopt(state,candidate);
    if (adopted.repair_cycles !== 2 || adopted.state !== "CI_PENDING") throw new Error("owner repair adoption invalid");
    return adopted;
  }
}
