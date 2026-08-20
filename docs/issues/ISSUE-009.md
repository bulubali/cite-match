# ISSUE-009

## Title
IF Resolution Provenance and Provider Integration

## Priority
P2 / Future Enhancement

## Status
Deferred

## Version Found
v2.5.x — 2026-08-20 IF Resolution Audit

## Scope

- ISSN/eISSN-first journal identity.
- DOI → Crossref identity enrichment.
- Verified local JIF cache carrying `value`, `metric_year`, `source`, and `retrieved_at`.
- Optional Clarivate Journal Citation Reports API provider, only with an approved license and user-provided API credentials.
- Never substitute CiteScore, SJR, or SNIP for Clarivate Journal Impact Factor (JIF).
- EasyScholar must not become a Production dependency unless it publishes a stable official API contract with supported authentication, identity-query semantics, metric-year provenance, and permitted programmatic use.

## Deferred Decision

No external IF provider will be integrated in v2.5.x.  The existing
`IF_UNKNOWN_REVIEW` Safety Interrupt remains the fail-closed behavior for
unverified journal IF values.

## Notes

- This is not an ISSUE-005 UX defect and does not reopen ISSUE-001 alias matching.
- No implementation, dependency installation, API key, cache, or external request is authorized by this record.
