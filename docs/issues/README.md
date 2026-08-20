# CiteMatch Issue Index

> Maintenance Mode — Bug fixes only.

---

## Issue List

| Issue | Title | Priority | Phase | Status | Found | Fixed |
|-------|-------|----------|-------|--------|-------|-------|
| [ISSUE-001](ISSUE-001.md) | Journal Alias Matching Failure | P0 | Phase 1 | Closed | v2.5.0 | 2026-08-20 |
| [ISSUE-002](ISSUE-002.md) | Non-pipe Table Detection / Cell Integrity | P0 | Phase 3/5 | Closed | v2.5.x | 2026-08-20 |
| [ISSUE-003](ISSUE-003.md) | Density Overflow: No Second-Candidate Retry | P1 | Phase 3 | Closed | v2.5.0 | 2026-08-20 |
| [ISSUE-004](ISSUE-004.md) | Legacy Citation Migration Missing | P0 | Mode C | Regression Testing | v2.5.0 | 2026-07-27 |
| [ISSUE-005](ISSUE-005.md) | Production Entry Incomplete for Phase 2–7 | P0 | Phase 2–7 | Closed | v2.5.x | 2026-08-20 |
| [ISSUE-006](ISSUE-006.md) | Final DOCX Figure Loss During Export | P0 | Phase 6 | Closed | v2.5.x | 2026-08-19 |
| [ISSUE-007](ISSUE-007.md) | Bibliography Visible Numbering Missing | P1 | Phase 6 | Closed | v2.5.x | 2026-08-19 |
| [ISSUE-008](ISSUE-008.md) | Abstract Exclusion Violation | P0 | Phase 3/5 | Closed | v2.5.x | 2026-08-19 |
| [ISSUE-009](ISSUE-009.md) | IF Resolution Provenance and Provider Integration | P2 | Phase 1 | Deferred | v2.5.x | — |

---

## Legend

| Priority | Description |
|----------|-------------|
| P0 | Production Bug — reference error, lost citation, duplicate, IF Gate, table/figure injection, Pandoc/CSL/Mapping Report failure |
| P1 | Correctness Bug — consecutive citation format, `^` residue, citation merge error, crossref modified |
| P2 | Experience — prompt wording, hint order, output format |

| Status | Description |
|--------|-------------|
| Open | Reported, awaiting Root Cause Analysis |
| In Progress | Root Cause confirmed, fix in progress |
| Regression Testing | Fix applied, regression tests running |
| Production Validation | Automated regression passed; awaiting real-paper acceptance |
| Closed | All tests passed, real-paper acceptance verified |

---

## Workflow

```
发现 Bug → 创建 ISSUE-XXX → Root Cause Analysis → 最小修复 → 新增 Regression Test → 全量测试 → 真实论文 Acceptance → Closed
```
