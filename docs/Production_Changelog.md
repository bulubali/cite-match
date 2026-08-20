# Production Changelog

> CiteMatch v2.5.x — Production Validation & Bug Fix Tracking

## Release Candidate distribution boundary — 2026-08-20

- **Status:** CiteMatch v2.5.x Release Candidate; Real User Production Acceptance PASS; Full Suite baseline 538 passed, 3 skipped; private Golden validation PASS.
- **Distribution:** Production manuscripts, bibliography exports, workflow state, generated DOCX files, reports, and private Golden fixtures remain local-only and are excluded from the public release set.
- **Deferred:** ISSUE-009 remains Deferred. No external IF provider or IF data coverage expansion is included in this RC.
> Each entry records a completed Production Test with its target Issue, result, and status.

---

## v2.5.0

### Production Test 1

- **Date:** 2026-07-27
- **Issue:** [ISSUE-004](issues/ISSUE-004.md) — Legacy Citation Migration Missing
- **Result:** 121 old citations → 0 (100% migration rate)
- **Files:** `engine/legacy_migration.py`, `tests/regression/test_issue_004.py`
- **Regression:** 5/5 PASS
- **Production Validation:** PASS (0 old citations in DOCX, 125 bibliography entries)
- **Status:** Closed

---

### Production Test 2

- **Date:** 2026-07-27
- **Issue:** [ISSUE-001](issues/ISSUE-001.md) — Journal Alias Matching Failure
- **Result:** UNKNOWN: 51 → 2 (28% → <1%)
- **Status:** Closed

---

### Production Test 3

- **Issue:** [ISSUE-002](issues/ISSUE-002.md) — Grid Table Format Not Detected

---

### Production Test 4

- **Issue:** [ISSUE-003](issues/ISSUE-003.md) — Density Overflow: No Second-Candidate Retry

---

## v2.5.x

### Production Test 5

- **Date:** 2026-08-19
- **Issue:** [ISSUE-006](issues/ISSUE-006.md) — Final DOCX Figure Loss During Export
- **Root Cause:** DOCX media was not extracted; Windows backslash paths containing `\.agents` were then misparsed as Markdown escapes.
- **Result:** Figures 10 → 10; displayed media hash matches 10/10; missing-image placeholder tables 10 → 0; captions 10/10; original data tables 2/2.
- **Regression:** ISSUE-006 3/3 PASS; related 74/74 PASS; Full Suite 477/477 PASS; Golden Dataset PASS.
- **Production Validation:** Phase 7 completed through restart-safe gates; Legacy 59/59 and 123/123; Abstract/Keywords new citations 0/0.
- **Artifact:** `output/issue006_production_validation_20260819_accepted/Final_Manuscript.docx`
- **Status:** Closed

---

### Production Test 6

- **Date:** 2026-08-19
- **Issue:** [ISSUE-007](issues/ISSUE-007.md) — Bibliography Visible Numbering Missing
- **Root Cause:** The numeric ACS Nano CSL sorted bibliography entries by `citation-number` but did not render that variable in the bibliography layout; citeproc therefore produced correctly ordered, unnumbered entries.
- **Result:** Exact production reproduction: visible numbering 0/90 -> 90/90; continuous 1-90; old 59/59; new 31/31; missing 0; duplicates 0; body-link order mismatches 0/189; Word `numPr` remains 0/90 by design.
- **Regression:** Focused/related 26/26 PASS; Full Suite 481/481 PASS; Golden Dataset PASS.
- **Production Validation:** Canonical Phase 7 completed; resolved bibliography entries 134/134 visibly numbered; figures/media/captions 10/10; tables 2/2; placeholders 0; Abstract/Keywords new citations 0/0; Legacy 59/59 and 123/123.
- **Artifacts:** `output/issue007_90_entry_validation_20260819_accepted/Final_Manuscript.docx`; `output/issue007_production_validation_20260819_accepted/Final_Manuscript.docx`.
- **Scope Note:** Four truncated grid-table citations in the full run remain the pre-existing ISSUE-002 defect and were not changed under ISSUE-007.
- **Status:** Closed

### Production Test 7

- **Date:** 2026-08-20
- **Issue:** [ISSUE-001](issues/ISSUE-001.md) — Journal Alias Matching Failure
- **Root Cause:** IF lookup removed only periods and whitespace, lacked reviewed aliases, and used an unsafe substring fallback that could merge unrelated journal titles.
- **Result:** Paused real-workflow matcher regression: `IF_UNKNOWN_REVIEW` 43 → 29; confirmed alias failures 14 → 0. The remaining 29 titles have no existing canonical IF database entry and remain fail-closed `UNKNOWN`.
- **Regression:** Focused/related 97/97 PASS; Full Suite 512 passed, 3 skipped; Golden Dataset PASS.
- **Production Evidence:** The Phase-3 state from the real acceptance run was inspected read-only; no unknown candidate was approved, excluded, injected, or deleted.
- **Status:** Closed

---

### Production Test 8

- **Date:** 2026-08-20
- **Issue:** [ISSUE-005](issues/ISSUE-005.md) — Production Entry / Real User Acceptance
- **Root Cause:** The user-selected `AM` journal resolved correctly, but the official `advanced-materials.csl` asset was absent from the local CSL cache. A Phase-6 external export failure also left no formal same-state retry route.
- **Minimal Fix:** Cached the unmodified official CSL at `cache/csl/advanced-materials.csl`; persisted recoverable Phase-6 state and enabled the existing Mode B Phase-6 retry only for the matching persisted workflow context.
- **Regression:** Focused/directly related 36 passed; Full Suite 516 passed, 3 skipped; Golden Dataset PASS.
- **Real User Acceptance:** The user personally completed Preflight, UNKNOWN-IF review, and chose to retain (not apply) all 62 Floating suggestions. The same r3 state resumed Phase 6 and completed Phase 7 without replaying any completed interaction or injection.
- **Result:** Final DOCX generated with Advanced Materials CSL; bibliography 116/116 visibly and continuously numbered; figures/media/captions 10/10; tables 2/2; placeholders 0; Abstract/Keywords new citations 0/0; legacy 59/59 and 123/123 with residual 0; mapping MD/CSV generated with no missing keys.
- **Artifact:** `output/issue005_real_user_acceptance_r3/Final_Manuscript.docx`
- **Status:** Closed

---

### Production Test 9

- **Date:** 2026-08-20
- **Issue:** [ISSUE-002](issues/ISSUE-002.md) — Non-pipe Table Detection / Cell Integrity
- **Root Cause:** Pandoc DOCX conversion produced fixed-width simple tables, but table recognition only covered pipe syntax. Phase 5 then treated table candidates as prose and raw-offset insertion shifted fixed column boundaries before Pandoc export.
- **Minimal Fix:** Recognize pipe/simple/grid tables in the existing AST. Preserve pipe behavior; fail-close simple/grid candidates as recorded `skip_unsafe_table` entries, with no prose fallback or table reconstruction.
- **Regression:** Focused/related 58/58 PASS; Full Suite 529 passed, 3 skipped; Golden Dataset PASS.
- **Production Validation:** Canonical Phase 7 completed in `output/issue002_production_regression_20260820`; Tables 2/2 retained all rows/cells and all four formerly corrupted cells retained their non-citation content. Simple-table injection 0; safe skips 14; citekey fragments and `?` residues 0. Figures/media 10/10, Legacy 59/59 and 123/123, residual 0, Abstract/Keywords 0/0, bibliography numbers 124/124 continuous.
- **Status:** Closed

---

### Production Test 10

- **Date:** 2026-08-20
- **Issue:** [ISSUE-003](issues/ISSUE-003.md) — Density Overflow: No Second-Candidate Retry
- **Root Cause:** Phase 3 discarded the already-ranked alternatives from `_find_matches()` when it retained only each paper's best sentence.  Sentence overflow therefore became immediate Floating.
- **Minimal Fix:** Preserve existing ranked alternatives in candidate/state data; retain the existing top-three primary assignment; retry overflowed papers through their same-context alternatives before Floating.  Adapter and Injector remain non-semantic.
- **Regression:** Focused/related 36 passed; Full Suite 538 passed, 3 skipped; Golden Dataset PASS.
- **Production Regression:** Formal Phase 7 completed in `output/issue003_production_regression_20260820_r2`.  Initial sentence overflows: 40; rerouted: 36; all reliable alternatives exhausted: 4; final Floating: 8, all traceable.  No silent drop and no fallback from table to body.
- **Scope Note:** Paragraph soft-8 was not implemented because the formal path lacks a canonical paragraph boundary; Review protection and table-IF classification remain out of scope.
- **Status:** Closed

---

## Template

```markdown
### Production Test N

- **Date:** YYYY-MM-DD
- **Issue:** [ISSUE-XXX](issues/ISSUE-XXX.md) — Title
- **Result:** Metric: before → after
- **Status:** Open | Closed
```
