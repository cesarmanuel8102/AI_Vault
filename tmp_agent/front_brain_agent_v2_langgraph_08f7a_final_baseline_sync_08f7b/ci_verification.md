# CI Verification — 08F7B Baseline Sync

## Verified commit
- **SHA:** `747726229d7e6bb94570aceda2c7bb29f209708c`
- **Short:** `7477262`

## Source
- GitHub API check-runs endpoint

## Overall status
**success**

## Check runs
| Name | Status | Conclusion |
|------|--------|------------|
| Phase 1 baseline (Windows) | completed | success |
| Hygiene Guard | completed | success |
| Security Smoke Tests | completed | success |
| Dashboard / Trace Tests | completed | success |
| Roadmap / Policy Regression | completed | success |
| Memory / Retrieval Regression | completed | success |

## Required workflow mapping
- `phase1-ci` → Phase 1 baseline (Windows): **success**
- `nontrading-smoke-regression` → Hygiene Guard, Security Smoke Tests, Dashboard / Trace Tests, Roadmap / Policy Regression, Memory / Retrieval Regression: all **success**
