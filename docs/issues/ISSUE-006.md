# ISSUE-006

## Title
Final DOCX Figure Loss During Export

## Priority
P0

## Status
Closed

## Fixed In
v2.5.x — 2026-08-19

## Version Found
v2.5.x

## Expected Behavior
All 10 figures and embedded media from the source manuscript are preserved in `Final_Manuscript.docx`.

## Actual Behavior
- Source figures: 10
- Final DOCX figures: 0
- Figure captions preserved: 10/10
- The exported document contains 10 new `1 x 1` placeholder tables where the images should be.

## Production Evidence
- Source: `output/Template.docx`
- Failing artifact: `output/issue005_final_production_validation_20260819_2045/Final_Manuscript.docx`
- Accepted artifact: `output/issue006_production_validation_20260819_accepted/Final_Manuscript.docx`
- Source inline shapes: 10
- Final inline shapes before fix: 0
- Final inline shapes after fix: 10
- Source embedded media files: 11
- Source media referenced by the document: 10
- Final embedded media files before fix: 0
- Final embedded media files after fix: 10

## Root Cause
1. `PandocAdapter.convert_docx_to_markdown()` converted the DOCX without
   `--extract-media`. The Markdown contained ten `media/image*.png` links, but
   no image files existed in the workflow output directory.
2. Adding extraction alone exposed a Windows-path edge case. Pandoc emitted
   backslash paths containing the repository segment `\.agents`; Markdown
   interpreted `\.` as an escape and attempted to read `workspace.agents`
   instead. Existing media was therefore still replaced with descriptions.
3. `pandoc-crossref` rendered each missing image description as a `1 x 1`
   table, which produced the ten observed placeholder tables.

## Minimal Fix Applied
- Reused the existing `PandocAdapter` conversion path.
- Added `--extract-media=<workflow-output-directory>` for file-based
  DOCX-to-Markdown conversion.
- Normalized the extraction root to forward slashes so dotted Windows path
  segments remain valid Markdown image targets.
- No Workflow, Engine, Phase, exporter, compiler, or user-visible interface was
  added or rewritten.

## Regression Test
Added `tests/regression/test_issue_006.py` with three tests:
1. The adapter requests media extraction beside the Markdown output and uses a
   forward-slash path containing a dotted directory segment.
2. A real figure-bearing DOCX survives conversion and export when the source
   directory differs from the workflow output directory.
3. Extracted media remains resolvable after Workflow JSON state persistence and
   continuation through a new `ManuscriptWorkflow` instance.

## Regression Results
- ISSUE-006 focused regression: 3/3 PASS.
- Related conversion/export/workflow and ISSUE-004/005/008 tests: 74/74 PASS.
- Full existing suite: 477/477 PASS.
- Golden Dataset integrity: PASS.

## Production Acceptance
- Canonical route: `ManuscriptWorkflow`, with a new process at every gate.
- Workflow completion: Phase 7 `completed`.
- Source directory differs from workflow output directory: PASS.
- Source figures: 10; final figures: 10.
- Displayed source media hashes preserved: 10/10 SHA-256 matches.
- Final embedded media: 10/10 displayed figures.
- Original data tables: 2/2 preserved; shapes remain `6 rows / 42 cells`
  and `11 rows / 66 cells`.
- Missing-image `1 x 1` placeholder tables: 10 before fix, 0 after fix.
- Figure captions: 10/10; labels remain Figure 1 through Figure 10.
- Abstract new citations: 0.
- Keywords new citations: 0.
- Legacy mapping: 59/59.
- Legacy occurrences migrated: 123/123.
- Residual legacy citations: 0.
- Old CiteKeys preserved: 59/59.

The existing Production Validation Runner reported zero functional FAILs for
Pandoc, Citation, Summary, Injection, Density, Table, Figure, Floating,
Mapping, and CSL. Its generic output-size comparator still reports three
non-comparable risks because it compares this 123-paper real run against a
10-paper/55-KB Golden acceptance artifact; those are not ISSUE-006 regressions
and the Golden Dataset integrity check itself passed.

## Acceptance Result
PASS — ISSUE-006 Closed.

## Notes
This fix is independent of ISSUE-007. Bibliography visible numbering remains
outside ISSUE-006 scope and did not block closure.
