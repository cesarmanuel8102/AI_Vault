# Runtime Stall Root Fix

## Goal

Eliminate the two proven indefinite waits in the PAPER runtime without changing trading policy, broker orders, positions, or the LIVE boundary.

## Constraints

- Work only in the isolated worktree until tests and review pass.
- Never connect to local port 4001 or force a broker order.
- Preserve canonical state and user artifacts.
- Every blocking operation introduced or retained by this change must have a finite bound.

## Task 1: Bound Codex subprocess cleanup

Files: `ibkr_paper_30d/autonomous_research.py`, `tests/ibkr_paper_30d/test_autonomous_codex_provider.py`.

1. Add a regression test proving timeout cleanup never calls an unbounded `communicate()` and returns within a finite deadline even when descendants retain inherited handles.
2. Run it and observe RED against the current implementation.
3. Capture Codex output through regular temporary files rather than inherited PIPE readers; terminate/wait only with finite deadlines; preserve `CompletedProcess`, timeout output, text/binary, input and `check` behavior.
4. Run targeted provider tests GREEN.

## Task 2: Prevent broker logging lock deadlock

Files: `ibkr_paper_30d/runtime_logging.py`, `ibkr_paper_30d/day1_launch.py`, `tests/ibkr_paper_30d/test_runtime_logging.py`, kernel manifest artifacts as required.

1. Add a regression test with a deliberately blocking root handler proving dependency callbacks do not propagate into it after runtime configuration.
2. Run it and observe RED before implementation.
3. Configure the noisy broker dependency logger at process startup with a non-propagating `NullHandler`; authoritative broker errors remain represented by explicit application events and state, not library console logging.
4. Run targeted launch/logging tests, kernel closure/provenance tests, then the relevant full suite.

## Deployment and runtime verification

1. Obtain a fresh whole-branch review and fix Important/Critical findings with RED→GREEN tests.
2. Commit the verified branch.
3. Integrate without discarding canonical untracked state; refresh approved-HEAD material through the existing deployment path.
4. Stop only the proven wedged PAPER runtime, relaunch the scheduled PAPER service, and verify fresh PID/lock/watchdog/provider cycles, port 4002 only, no ambiguity/duplicates, and accepted terminal cycles.

## Review focus

- No unbounded subprocess wait remains on success, timeout, cleanup, or output collection paths.
- Text/binary output and input semantics remain compatible with existing callers.
- Logging isolation cannot disable explicit application alerts or broker-state reconciliation.
- No change broadens order authority or touches LIVE.
