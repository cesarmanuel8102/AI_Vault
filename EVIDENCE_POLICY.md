# Evidence Policy

This repository distinguishes source code from runtime evidence and generated artifacts.

## Tracked by Git

Track:
- source code
- tests
- documentation
- stable configuration templates
- small reproducible fixtures

Do not track:
- runtime logs
- generated evidence directories
- market data archives
- strategy phase outputs
- local memory indexes
- secrets
- binary caches
- temporary backups

## Runtime artifacts

Runtime artifacts must remain local or be stored in an external artifact store.
They must not be committed to Git unless explicitly approved as a small reproducible fixture.

## Secrets

Secrets must never be committed.

If a secret is found in Git history:
1. remove it from tracking,
2. rotate the credential,
3. assess whether history rewriting is required.

## Approved hygiene command

Use git rm --cached to stop tracking generated files without deleting local copies.

Never use bulk deletion or git clean without a reviewed plan.
