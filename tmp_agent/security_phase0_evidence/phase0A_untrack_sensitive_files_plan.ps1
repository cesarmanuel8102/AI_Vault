# Phase 0A — Untrack sensitive files from git index (PLAN ONLY, do NOT execute without confirmation)
#
# Purpose:
#   Stop tracking .dev_auth/credentials.enc and .dev_auth/god_audit.jsonl in the git index.
#   Files remain on disk; only the index entry is removed.
#
# Preconditions:
#   1. phase0A_gitignore_dev_auth.patch has been applied (.gitignore covers .dev_auth/).
#   2. Operator has read EVIDENCE_POLICY.md.
#   3. Operator has confirmed credential rotation has been planned.
#
# Hard rules:
#   - Uses --cached so working-tree files are NOT deleted.
#   - Uses --ignore-unmatch so missing entries do not abort.
#   - Allowlist only. No wildcard, no -r, no recursive globs.
#   - This script does NOT commit. Operator must commit manually after review.
#
# Safety check: refuses to run if not on the expected branch.

$ErrorActionPreference = "Stop"

$expectedBranch = "codex/own-capital-sustainable-return"
$currentBranch  = (git branch --show-current).Trim()

if ($currentBranch -ne $expectedBranch) {
    Write-Error "ABORT: current branch '$currentBranch' != expected '$expectedBranch'"
    exit 1
}

Write-Host "[phase0A] Branch OK: $currentBranch"
Write-Host "[phase0A] Pre-state ls-files .dev_auth:"
git ls-files .dev_auth

$allowlist = @(
    ".dev_auth/credentials.enc",
    ".dev_auth/god_audit.jsonl"
)

foreach ($p in $allowlist) {
    Write-Host "[phase0A] git rm --cached --ignore-unmatch $p"
    git rm --cached --ignore-unmatch -- $p
}

Write-Host "[phase0A] Post-state ls-files .dev_auth:"
git ls-files .dev_auth

Write-Host "[phase0A] git status --short for .dev_auth:"
git status --short -- .dev_auth

Write-Host ""
Write-Host "[phase0A] Files on disk preserved (verify):"
foreach ($p in $allowlist) {
    if (Test-Path $p) {
        Write-Host "  EXISTS_ON_DISK: $p"
    } else {
        Write-Warning "  MISSING_ON_DISK: $p"
    }
}

Write-Host ""
Write-Host "[phase0A] DONE. No commit performed. No physical delete performed."
Write-Host "[phase0A] Operator must now:"
Write-Host "          1. Review staged deletions (git diff --cached -- .dev_auth)"
Write-Host "          2. Commit with explicit allowlist (do NOT use git add -A)"
Write-Host "          3. Plan credential rotation separately"
Write-Host "          4. Decide on git history rewrite (BFG / git filter-repo) outside this phase"
