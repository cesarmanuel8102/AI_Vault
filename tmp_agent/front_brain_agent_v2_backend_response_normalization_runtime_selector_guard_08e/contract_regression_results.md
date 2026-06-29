# 08D Contract Regression Results

## Tests
- 
- 
- 

## Result
23 passed, 7 failed, 0 skipped.

## Functional / schema regressions
All functional contract tests for , , , trace endpoints, and dashboard chat contract passed.

## Expected scope-guard failures
The following 08D tests fail because 08E is explicitly allowed to modify  and . These are not defects:

1.  - 08E intentionally adds  wiring.
2.  -  sees allowed changes.
3.  -  sees allowed changes.
4.  -  sees allowed changes.
5.  (08d) - allowed source files differ from 08D baseline.
6.  (08d dashboard) - allowed source files differ from 08D baseline.
7.  (08d trace) - allowed source files differ from 08D baseline.

## Decision
ACCEPTED_WITH_SCOPE_GUARD_EXPECTED_FAILURES.
