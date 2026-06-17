# Human Approval Package
**Domain:** security_governance_sandboxing
**Batch ID:** SEC_GOV_CANARY_001
**Record Count:** 5
**FAISS Eligible Count:** 0

## Source IDs
- nist_csf
- nist_ai_rmf
- opa_docs
- mitre_atlas
- gvisor_docs

## Mutation Authorization
- Memory mutation authorized now: False
- FAISS mutation authorized now: False
- Requires user approval before mutation: True

## Expected Counts
- Memory line count before: 1710
- Memory line count after (if approved): 1715
- FAISS ids count before: 1611
- FAISS ids count after (if approved): 1611

## Approval Phrase
```
APPROVE_SECURITY_GOVERNANCE_CANARY_INGESTION_BATCH_SEC_GOV_CANARY_001
```

## Denial Phrase
```
DENY_SECURITY_GOVERNANCE_CANARY_INGESTION_BATCH_SEC_GOV_CANARY_001
```

## Proposed Records Preview
| memory_id | source_id | source_title | domain | ingestion_status | faiss_eligible |
|-----------|-----------|--------------|--------|------------------|----------------|
| SEC_GOV_CANARY_001_nist_csf_001 | nist_csf | NIST Cybersecurity Framework ( | security_governance_sandboxing | proposed_only | False |
| SEC_GOV_CANARY_001_nist_ai_rmf_002 | nist_ai_rmf | NIST AI Risk Management Framew | security_governance_sandboxing | proposed_only | False |
| SEC_GOV_CANARY_001_opa_docs_003 | opa_docs | Open Policy Agent (OPA) -- Pol | security_governance_sandboxing | proposed_only | False |
| SEC_GOV_CANARY_001_mitre_atlas_004 | mitre_atlas | MITRE ATLAS -- Adversarial Thr | security_governance_sandboxing | proposed_only | False |
| SEC_GOV_CANARY_001_gvisor_docs_005 | gvisor_docs | gVisor -- Application Kernel f | security_governance_sandboxing | proposed_only | False |
