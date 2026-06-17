# Root Cause Audit: Mandatory Inline Numbered Check Parser

## Bug Summary
The mandatory multi-tool parser fails to extract multiple checks from compact inline numbered lists.

## Example Failing Input


## Expected
- 4 requested checks
- 3 scheduled tools (route_probe x2, repo_status_read)
- 1 final answer obligation

## Actual
- 1 requested check
- 1 scheduled tool (only first route_probe)
- 3 checks silently dropped

## Root Cause Location
- **File:** 
- **Function:** 
- **Lines:** 62-87

## Why It Happens
1. **Line-based parsing:**  creates single element for single-line input
2. **First-match-only:**  finds first pattern match only per line
3. **Early break:**  exits loop after first match per line
4. **No inline splitting:** No logic to split by numbered markers (, , ) while preserving URLs

## Formats Not Supported
- Inline dot-numbered: 
- Inline paren-numbered: 
- Semicolon-separated: 
- Inline dash bullets: 

## Fix Required
Add inline check splitting before line-based pattern matching:
1. Split by numbered markers (URL-safe)
2. Split by semicolons with numbered markers
3. Split by dash bullets
4. Then apply existing pattern matching per segment
