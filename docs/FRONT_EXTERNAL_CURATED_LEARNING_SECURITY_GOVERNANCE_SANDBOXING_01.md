# FRONT-EXTERNAL-CURATED-LEARNING-SECURITY-GOVERNANCE-SANDBOXING-01

## Objective

Create a canonical curated source plan for Brain to learn **Security / Governance / Sandboxing** safely, without ingesting any content into semantic memory or FAISS, without downloading full papers or repos, and without modifying protected runtime files.

This front is **DRY-RUN ONLY / CURATION FIRST**.

## Why Security / Governance / Sandboxing Is Fourth

After understanding agentic systems (1), evaluation (2), and memory architecture (3), Brain must learn how to **secure itself, govern its actions, and sandbox untrusted execution**. Without security and governance, Brain cannot:

- Protect secrets and sensitive configuration
- Enforce least privilege on its own actions
- Prevent prompt injection and adversarial manipulation
- Maintain audit trails for accountability
- Sandbox generated code or external tools
- Govern financial or high-risk actions
- Recover safely from failures or incidents

## Prior Brain Learning State

- Agentic Systems curated plan complete (21 sources)
- Evaluation & Benchmarking curated plan complete (24 sources)
- Memory / RAG / Knowledge Architecture curated plan complete (28 sources)
- 1,710 lines of semantic memory (unchanged in this front)
- 1,611 FAISS IDs (unchanged in this front)
- Chat retrieval injection patch present but marker pass remains 1/3
- `execution_gate.py` exists but was not modified in this front
- No prior curated external source plan for security/governance

## Safe Source Policy

**No security/governance source is accepted because it is popular.** Every source must be:

- **Safe**: Publicly reachable, no malware, no illegal content
- **Attributable**: Clear authors, org, or maintainers
- **Technically relevant**: Concrete controls, architecture, or implementation
- **Cross-checked**: Verified against at least one other source type when possible
- **Mapped to Brain capability**: Directly linked to a Brain governance target
- **Legally usable at metadata level**: No full-text copying required
- **Not ingested in this front**: All sources remain `not_ingested`
- **Defensive only**: No offensive/exploitative content emphasis

## Taxonomy (22 Categories)

1. **Least Privilege** — Minimum permissions necessary
2. **Role-Based Access Control** — Permission model based on roles
3. **Policy-as-Code** — Governance rules as versioned, testable code
4. **Execution Gates** — Checkpoints before action execution
5. **Sandboxed Code Execution** — Isolated environments for untrusted code
6. **Filesystem Boundaries** — Restricting file system access
7. **Network Egress Control** — Controlling outbound connections
8. **Secrets Management** — Secure handling of credentials and keys
9. **Audit Logging** — Recording actions for accountability
10. **Immutable Evidence Logs** — Tamper-proof records
11. **Supply-Chain Security** — Securing dependencies and builds
12. **Dependency Trust** — Verifying third-party libraries
13. **Prompt Injection Defense** — Protecting against adversarial inputs
14. **Tool-Use Governance** — Rules on tool invocation
15. **Human Approval Gates** — Explicit authorization for high-risk actions
16. **Rollback / Recovery** — Reverting changes and restoring state
17. **Incident Response** — Structured process for security incidents
18. **Safe Autonomy Levels** — Graduated permissions with verified competence
19. **Privacy Governance** — Handling personal/sensitive data
20. **Local-First Governance** — No external cloud dependency
21. **Chain-of-Thought Non-Disclosure** — Preventing reasoning leakage
22. **Financial-Action Governance** — Controls for trading and financial decisions

## Source Acceptance Criteria

- Clear attribution
- Publicly reachable URL
- Technical depth > marketing/hype
- License allows metadata reference
- Relevance to at least one taxonomy category
- Not contradicted by a more authoritative source
- No critical risk flagged by safety rubric

**Decision rule**: Accept if score >= 58 and no critical risks; hold if 42-57; reject if < 42 or any critical risk.

## Source Rejection Criteria (Automatic)

- Private or access-restricted content
- No identifiable attribution
- Illegal or copyright-violating distribution
- Offensive security content without defensive framing
- Exploit/malware code emphasis
- Requires copying full copyrighted text
- Privacy-invasive architecture with no safeguards
- Unverifiable security claims
- Abandoned and contradicted by newer official source

## Safety Scoring Rubric

18 dimensions scored 0-5 (max 90):

| Dimension | Description |
|-----------|-------------|
| attribution_quality | Clear authors, org, or maintainers |
| primary_source_quality | Primary source (standard, official repo, docs) |
| technical_depth | Concrete security architecture, controls, implementation |
| implementation_relevance | Can be adapted without vendor-specific infrastructure |
| governance_method_clarity | Governance rules, policies, enforcement clearly defined |
| sandboxing_method_clarity | Isolation boundaries, resource limits, escape prevention |
| reproducibility | Reproducible steps/examples/tests |
| license_clarity | License stated and compatible |
| maintenance_status | Active, maintenance, or clearly archived |
| test_or_example_presence | Runnable examples/tests/demos |
| copyright_safety | Safe to reference at metadata level |
| relevance_to_brain | Maps to Brain governance capability target |
| risk_of_hype_or_marketing | Free of exaggerated claims |
| risk_of_obsolescence | Likely relevant 12+ months |
| risk_of_vendor_lock_in | Requires specific vendor/cloud? (5 = neutral, 0 = lock-in) |
| risk_of_security_misuse | Could be misused offensively? (5 = purely defensive, 0 = offensive) |
| risk_of_privacy_leakage | Risks leaking private/sensitive data? (5 = safe, 0 = high risk) |
| risk_of_unverifiable_claims | Claims supported by evidence |

**Thresholds**: Accept >= 58, Hold 42-57, Reject < 42.

## Contrast Scoring Rubric

Each source contrasted against at least two sources of different types:

- security framework vs official docs
- sandboxing docs vs policy-as-code docs
- supply-chain framework vs dependency scanning tool docs
- prompt-injection paper vs tool governance framework
- RBAC docs vs execution gate implementation pattern
- incident response framework vs rollback/recovery runbook pattern

Per-source fields: `confirms`, `contradicts`, `complements`, `unresolved_questions`, `confidence_level` (low/medium/high).

## Brain Governance Capability Map (18 Capabilities)

| Capability | Relevant Taxonomy | Example Sources |
|------------|-------------------|-----------------|
| Define safe autonomy levels | safe autonomy, human approval | NIST AI RMF, Anthropic Responsible Scaling |
| Define permission model | RBAC, least privilege | NIST CSF, OPA docs |
| Design execution gates | execution gates, tool governance | OWASP LLM Top 10, Google SAIF |
| Design tool allowlist/denylist | tool governance, least privilege | OWASP LLM Top 10, MITRE ATLAS |
| Design filesystem sandbox | filesystem boundaries, sandboxing | gVisor docs, Firecracker docs |
| Design network egress restrictions | network egress, sandboxing | gVisor docs, Docker security docs |
| Protect secrets and .env | secrets management, privacy | NIST CSF, OpenSSF Scorecard |
| Preserve audit logs | audit logging, immutable evidence | NIST AI RMF, Microsoft Responsible AI |
| Preserve immutable evidence | immutable evidence, audit logging | SLSA, Sigstore |
| Evaluate policy compliance | policy-as-code, execution gates | OPA docs, OWASP LLM Top 10 |
| Prevent CoT leakage | CoT non-disclosure, privacy | Prompt injection paper, Anthropic Constitutional AI |
| Prevent private data leakage | privacy governance, secrets | Microsoft Presidio, NIST AI RMF |
| Detect prompt injection | prompt injection defense, tool governance | Prompt injection paper, OWASP LLM Top 10 |
| Design human approval gates | human approval, safe autonomy | NIST AI RMF, Microsoft Responsible AI |
| Design rollback/recovery | rollback/recovery, incident response | SLSA, Docker security docs |
| Manage dependency trust | dependency trust, supply-chain | OpenSSF Scorecard, pip-audit |
| Prepare financial action governance | financial governance, human approval | NIST AI RMF, policy-as-code |
| Decide promote/reject/rollback under risk | rollback/recovery, safe autonomy | NIST CSF, incident response |

## Standard / Paper Candidates (10)

| Source | Authors/Org | Year | Status | Score |
|--------|-------------|------|--------|-------|
| NIST AI RMF | NIST | 2023 | accept | 65 |
| NIST CSF 2.0 | NIST | 2024 | accept | 66 |
| OWASP LLM Top 10 | OWASP | 2023 | accept | 62 |
| MITRE ATLAS | MITRE | 2023 | accept | 63 |
| Google SAIF | Google | 2023 | accept | 58 |
| Microsoft Responsible AI | Microsoft | 2022 | accept | 59 |
| Anthropic Responsible Scaling | Anthropic | 2023 | accept | 60 |
| Anthropic Constitutional AI | Anthropic | 2022 | accept | 58 |
| Prompt Injection Paper | CISPA / others | 2023 | accept | 59 |
| SLSA | OpenSSF / Google | 2021 | accept | 62 |

## GitHub / Framework / Docs Candidates (14)

| Source | Org | Status | Score | Notes |
|--------|-----|--------|-------|-------|
| Open Policy Agent (OPA) | CNCF | active | 64 | Policy engine for execution gates |
| gVisor | Google | active | 63 | Userspace kernel sandboxing |
| Firecracker | AWS | active | 62 | MicroVM isolation |
| Docker Security Docs | Docker | active | 60 | Container security best practices |
| Sigstore | Linux Foundation | active | 63 | Keyless signing + transparency |
| OpenSSF Scorecard | OpenSSF | active | 62 | Automated security scoring |
| pip-audit | PyPA / Trail of Bits | active | 61 | Python vulnerability scanning |
| Semgrep | r2c | active | 60 | Multi-language static analysis |
| Bandit | PyCQA | active | 60 | Python security linter |
| GitHub Actions Security | GitHub | active | 56 | CI/CD security hardening |
| Microsoft Presidio | Microsoft | active | 59 | PII detection and anonymization |
| promptfoo | promptfoo | active | 58 | LLM red-team testing |
| Unknown Security Blog | unknown | unknown | 20 | **Reject** — no attribution |

## Cross-Source Contrast Matrix (9 pairs)

| Pair | Type | Confidence | Key Finding |
|------|------|------------|-------------|
| NIST AI RMF ↔ NIST CSF | AI-specific vs general | high | AI RMF adds AI-specific risks; CSF provides broader infrastructure security |
| OWASP LLM Top 10 ↔ MITRE ATLAS | risk list vs threat framework | high | Both identify prompt injection as top risk; OWASP provides mitigations, ATLAS provides adversary tactics |
| Google SAIF ↔ Microsoft Responsible AI | vendor security vs governance | medium | SAIF is technical/operational; Responsible AI is governance/policy-oriented |
| gVisor ↔ Firecracker | userspace vs microVM | high | gVisor easier with containers; Firecracker stronger VM-level isolation |
| OPA ↔ NIST CSF | policy engine vs standard | high | OPA implements policy-as-code; CSF describes the governance need |
| Prompt injection paper ↔ promptfoo | research vs tool | high | Paper defines threat model; promptfoo provides automated red-team testing |
| SLSA ↔ Sigstore | levels vs signing | high | SLSA defines maturity levels; Sigstore provides keyless signing infrastructure |
| OpenSSF Scorecard ↔ pip-audit | scoring vs scanning | medium | Scorecard evaluates project health; pip-audit focuses on known CVEs |
| Anthropic Responsible Scaling ↔ Constitutional AI | governance vs technical | medium | Responsible Scaling defines governance framework; Constitutional AI provides self-critique mechanism |

## Privacy Risks

| Source | Risk | Notes |
|--------|------|-------|
| GitHub Actions Security | low | CI/CD best practices; no data exposure |
| Microsoft Presidio | low | PII detection for data protection |
| promptfoo | low | Red-team testing on user-controlled data |
| Unknown Security Blog | low | No actual product |

## Security Misuse Risks

| Source | Risk | Notes |
|--------|------|-------|
| Prompt injection paper | low | Defensive framing; no exploit code |
| promptfoo | low | Defensive red-teaming only |
| MITRE ATLAS | low | Defensive threat intelligence |
| Unknown Security Blog | low | No actionable content |

## Vendor Lock-In Risks

| Source | Risk | Notes |
|--------|------|-------|
| Google SAIF | medium | Some Google Cloud coupling |
| Microsoft Responsible AI | medium | Some Microsoft-specific tooling |
| GitHub Actions Security | medium | GitHub-specific but principles generalize |
| Anthropic Responsible Scaling | medium | Anthropic-specific policy framework |
| NIST standards | low | Government public domain |
| OWASP | low | Community-driven, vendor-neutral |
| Open-source tools | low | Self-hostable, no external dependency |

## Copyright Constraints

- **No full papers downloaded**
- **No full READMEs copied**
- **No repos cloned**
- **No PDFs stored in repo**
- **No exploit code or malware samples**
- All references are metadata-level (title, authors, URL, summary)
- Standards referenced by official publication URL
- GitHub repos referenced by public repo URL and visible metadata only

## Dry-Run-Only Confirmation

- `ingestion_status`: `dry_run_only` for all 25 sources
- No semantic memory writes
- No FAISS reindexing
- No protected runtime modifications
- No `.env` changes
- No secrets exposed
- No execution_gate.py modified

## Memory / FAISS Immutability Proof

| Check | Before | After | Result |
|-------|--------|-------|--------|
| semantic_memory.jsonl SHA | `655d323...` | `655d323...` | **PASS** |
| semantic_memory.jsonl lines | 1710 | 1710 | **PASS** |
| FAISS index SHA | `b7b755c...` | `b7b755c...` | **PASS** |
| FAISS ids SHA | `0043623...` | `0043623...` | **PASS** |
| FAISS ids count | 1611 | 1611 | **PASS** |

## Tests Result

41 tests passed, 0 failed.

## Limitations

1. **Marker pass remains 1/3** from prior chat fronts; this front does not address chat retrieval
2. **Metadata check is sample-based** (no full web verification run)
3. **No actual ingestion** performed; sources are candidates only
4. **Contrast matrix is manual**; future fronts may automate cross-checking
5. **No new executable policies created**; this is a curation-only front
6. **execution_gate.py was not modified**; future fronts may propose patches
7. **Unknown Security Blog rejected** due to lack of attribution

## Next Recommended Front

**FRONT-EXTERNAL-CURATED-LEARNING-AUTONOMOUS-CODING-PATCH-GENERATION-01**

Purpose: Curate safe, attributable sources for Autonomous Coding and Patch Generation — the fifth macro-domain in Brain's external learning plan.

**Do not execute without user approval.**
