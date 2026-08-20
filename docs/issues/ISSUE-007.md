# ISSUE-007

## Title
Bibliography Visible Numbering Missing

## Priority
P1

## Status
Closed

## Fixed In
v2.5.x — 2026-08-19

## Version Found
v2.5.x

## Expected Behavior
All 90 entries in the final bibliography have continuous visible numbering from 1 through 90.

## Actual Behavior
- Bibliography entries present: 90/90
- Unique bibliography entries: 90
- In-text numeric citations: present and rendered normally
- Visible bibliography numbering: 0/90
- Word numbering properties (`numPr`): 0/90

## Production Evidence
- Final artifact: `output/issue005_final_production_validation_20260819_2045/Final_Manuscript.docx`
- The active CSL sorts the bibliography by `citation-number`, but its bibliography layout does not render `citation-number`.

## Root Cause
The ACS Nano CSL is numeric: its citation layout renders
`citation-number`, and its bibliography sort key is `citation-number`.
However, the bibliography layout contained only the formatted reference
fields and never rendered `citation-number`. Citeproc therefore generated all
90 unique entries in the correct order but had no visible number to emit.

`CSLModifier.ensure_collapse()` and the default/All Authors operations did not
remove numbering; the source layout never contained it. Word `numPr` is not
the intended mechanism here. The visible prefix must be produced by CSL and
citeproc so it remains bound to the same citation-number used by body links.
This is a generic numeric-CSL omission, not an ACS-Nano-fixture or 90-entry
special case.

## Minimal Fix Applied
- Added an idempotent `CSLModifier.ensure_bibliography_numbering()` operation.
- Numeric styles are detected from citation rendering or bibliography sorting
  by `citation-number`.
- When, and only when, a numeric bibliography layout lacks a visible
  `citation-number`, the modifier prepends a CSL text node rendering `1. `,
  `2. `, and so on.
- Existing visible numbering and author-date styles are left unchanged.
- `JournalStyleManager.modify_csl()` invokes the operation in the existing
  formal CSL compilation path before author-display handling.

No Workflow, Phase, exporter subsystem, framework, fallback, fixture-specific
branch, or manual DOCX modification was added.

## Regression Test
Added `tests/regression/test_issue_007.py` covering:
1. Numeric bibliography numbering insertion and idempotence.
2. Preservation across full/default author-display modification.
3. No numbering injection into an author-date CSL.
4. Real Pandoc/citeproc DOCX compilation with continuous visible numbering,
   citation order, and no Word `numPr` dependency.
5. Invocation through `JournalStyleManager`, the formal compilation path.

## Regression Results
- ISSUE-007 focused and directly related tests: 26/26 PASS.
- Full Suite: 481/481 PASS.
- Golden Dataset integrity: PASS (7/7 files).

## Production Acceptance

### Exact 90-entry ISSUE-007 reproduction
- Source manuscript:
  `output/issue005_final_production_validation_20260819_2045/injected_manuscript.md`
- Accepted artifact:
  `output/issue007_90_entry_validation_20260819_accepted/Final_Manuscript.docx`
- Formal path: `CSLModifier` -> `JournalStyleManager` ->
  `PandocCommandBuilder` -> citeproc -> `DocxExporter`.
- Entries: 90/90; unique: 90; missing: 0; duplicates: 0.
- Old references: 59/59; new references: 31/31.
- Visible numbering: 0/90 before fix -> 90/90 after fix.
- Sequence: 1 through 90, continuous; gaps: 0; duplicate numbers: 0.
- Body-to-bibliography numeric links checked: 189; order mismatches: 0.
- Word `numPr`: 0/90, confirming numbering is correctly CSL-rendered.
- Citeproc missing-citation warnings: 0.

### Full real-manuscript workflow regression
- Accepted artifact:
  `output/issue007_production_validation_20260819_accepted/Final_Manuscript.docx`
- Canonical `ManuscriptWorkflow` completed Phase 7 across persisted gates.
- Every citeproc-resolved bibliography entry is visibly numbered: 134/134,
  continuous 1 through 134, no gaps, no duplicate entries or numbers.
- Body-to-bibliography numeric links checked: 229; order mismatches: 0.
- Figures: 10/10; embedded displayed media hashes: 10/10.
- Captions: Figure 1 through Figure 10 (10/10).
- Original data tables: 2/2 with shapes preserved at 6 rows/42 cells and
  11 rows/66 cells; missing-image placeholders: 0.
- Abstract new citations: 0; Keywords new citations: 0.
- Legacy mapping: 59/59; legacy occurrences migrated: 123/123; residual: 0.
- The Production Validation Runner reported zero functional FAILs across
  Pandoc, Citation, Summary, Injection, Density, Table, Figure, Floating,
  Mapping, and CSL. Its three output-size comparison FAILs remain the known
  non-comparable real-manuscript-versus-small-Golden comparator result.

The full workflow also reproduced four pre-existing truncated citations inside
Pandoc grid tables (`changIntegrationChe`, `q`, `zhangFle`, and
`zhangHighlyAccurateF`). They are attributable to the already-open P0
ISSUE-002 grid-table handling defect, are unchanged by this CSL-only fix, and
were not modified under ISSUE-007. The exact 90-entry ISSUE-007 production
case has no missing references or citeproc warnings.

## Acceptance Result
PASS — ISSUE-007 Closed.

## Notes
This fix is independent of ISSUE-005 and ISSUE-006. ISSUE-005 was not started.
