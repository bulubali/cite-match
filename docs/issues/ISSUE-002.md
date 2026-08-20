# ISSUE-002

## Title

Pandoc non-pipe table citation injection corrupts DOCX cell content

## Priority

P0

## Status

Closed

## Version Found

v2.5.x (real Production Acceptance, 2026-08-20)

## Root Cause

`PandocAdapter` converts the source DOCX to Pandoc fixed-width simple tables.
`MarkdownAST` recognized only pipe tables, so `CandidateAdapter`
marked simple-table targets as body content. Phase 5 then used raw character
offset injection. The added citation exceeded the fixed source column boundary;
Pandoc subsequently parsed the overflow as adjacent cells, splitting prose and
citekeys in the final DOCX.

The original Issue described grid tables. The same detection gap affected both
Pandoc grid and simple table formats.

## Minimal Fix

- `MarkdownAST` now recognizes pipe, Pandoc simple, and Pandoc grid tables and
  records the table format for each source region.
- `CandidateAdapter` consequently preserves `is_in_table=True` for all three.
- Pipe-table behavior remains compatible with the existing injection route.
- Simple/grid table candidates are fail-closed as `skip_unsafe_table`: no raw
  offset insertion, no body fallback, no cell reconstruction, and no content
  mutation. Phase 5 records the skipped citekeys and does not require them in
  its injected-key write validation.
- The existing `TableValidator` reports recognized non-pipe tables instead of
  silently reporting that no table exists.

## Regression Coverage

`tests/regression/test_issue_002.py` covers:

1. Pipe, simple, and grid table detection.
2. Simple/grid candidate adaptation as table candidates.
3. Long-key and multi-format non-pipe fail-closed behavior.
4. No row change, no adjacent-cell text movement, no citekey fragment, and no
   `?` residue when non-pipe injection is unavailable.
5. Existing pipe-table injection compatibility.
6. Existing table-validator recognition.
7. The four real production targets: Table 1 pulse-wave morphology; Table 2
   breathability, biocompatibility, and miniaturization.

## Validation

- Focused / directly related: **58 passed**.
- Full suite: **529 passed, 3 skipped**.
- Golden Dataset integrity: **PASS (7/7 files)**.
- Real Production Regression: canonical `ManuscriptWorkflow` Phase 1–7
  completed in `output/issue002_production_regression_20260820`.

### Real Production Result

- Table objects: 2/2; row/cell layout: Table 1 = 6 rows × 7 cells, Table 2 =
  11 rows × 6 cells.
- Four previously corrupted target cells retained their complete original
  non-citation text; the following cell also retained its original text.
- Non-pipe table candidates skipped safely: 14; injected into simple tables: 0.
- Citekey fragments: 0; `?]` citation residues: 0.
- Figures/media: 10/10; placeholder tables: 0.
- Legacy mapping: 59/59; occurrences: 123/123; residual legacy: 0.
- Abstract/Keywords new citations: 0/0.
- Bibliography visible numbers: 124/124, continuous from 1.
- Floating expansion: not applied (`keep`).

## Notes

The historical ISSUE-005 record is preserved. Its former real-acceptance DOCX
is not evidence of table cell integrity; this issue's independent production
artifact is the table-focused acceptance evidence. No CSL, citeproc, DOCX
post-processing, user manuscript, or other Issue behavior was changed.
