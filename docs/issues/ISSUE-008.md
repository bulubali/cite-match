# ISSUE-008

## Title
Abstract Exclusion Violation

## Priority
P0

## Status
Closed

## Version Found
v2.5.x

## Environment
- Production entry: `workflows/manuscript_workflow.py::ManuscriptWorkflow`
- Input fixture: `output/Template.docx` and `output/references.bib`
- Evidence run: `output/issue005_final_production_validation_20260819_2045`

## Expected Behavior
Pending/new references must never be injected into the Abstract or Keywords exclusion zone. Existing citations may be migrated in place, but the exclusion zone is read-only for new citation injection.

## Actual Behavior
- The original DOCX contains 0 citations in the Abstract and Keywords block.
- The Mode C migrated Markdown contains 0 citations in that block.
- Phase 5 injected 16 new CiteKeys into Abstract body sentences and 3 additional new CiteKeys into the Keywords line.
- All 19 candidates were persisted with `section = "(preamble)"` and `if_gate = "UNKNOWN"`.

### New CiteKeys in Abstract body
- `zhangFlexibleElectronicsCardiovascular2023`
- `tianFlexibleThermalArray2026`
- `jinFlexibleOptoacousticBlood2023`
- `zhangHighSignalNoise2024`
- `buiEBPEarwornDevice2021`
- `ahmadpourPiezoelectricMetamaterialBlood2023`
- `wangWearableMultichannelPulse2022`
- `liuHGCTNetHandcraftedFeatureguided2024`
- `changIntegrationChemicalPhysical2025`
- `kangSiliconNanocolumnbasedDisposable2025`
- `huangContinuousBloodPressure2025`
- `chowdhuryPaperbasedSupercapacitivePressure2023`
- `yangScreenprintableIontronicPressure2024`
- `wangWearablePiezoelectricbasedSystem2020`
- `elabbasiWearableBloodPressure2022`
- `wangDifferentialdeformationStructuredPressure2025`

### New CiteKeys in Keywords
- `zhangContinuousCufflessBlood2026`
- `wuTransferLearningbasedCalibrationfree2025`
- `liuCufflessBloodPressure2023`

## Root Cause Evidence
1. Pandoc emitted the labels as bold paragraphs (`**Abstract:**`, `**Keywords:**`, and `**1.Introduction�**`) rather than ATX Markdown headings.
2. `SemanticMapper._parse_manuscript()` changes section only for lines matching `^#{1,6}\s+`; it therefore classified the exclusion block as `(preamble)`.
3. `_is_rejected_zone()` contains the intended Abstract/Keywords rejection rule, but it never sees those section names for this production input.
4. `CitationCandidate` has no separate protected-zone field. `candidate_adapter.py` passes the incorrect section and recomputes only table/code-block flags.
5. `CitationInjector` protects tables and code blocks, but does not independently validate Abstract/Keywords positions. The misclassified candidates were therefore injected.

## Failure Locations
- Abstract body: `injected_manuscript.md` lines 3, 5, and 7
- Keywords: `injected_manuscript.md` line 13
- Candidate state: `workflow_state.json` (`candidate_state.candidates`)
- Injection evidence: `workflow_state.json` (`injection_state.log`)

## Acceptance Criteria
- New citation count in Abstract body = 0.
- New citation count in Keywords = 0.
- Existing citations, if present, remain eligible only for legacy migration.
- Production-format section labels are classified before semantic matching.
- Protected-zone metadata survives candidate adaptation and injection fails closed if the target is protected.

## Minimal Fix Applied
- Added one shared, policy-backed Markdown section-context helper supporting ATX headings, Pandoc full-line bold headings, plain section labels, English/Chinese Abstract labels, and English/Chinese Keywords labels.
- `SemanticMapper` excludes protected lines before matching and preserves the resolved body section after the protected block.
- `candidate_adapter.py` resolves the actual target line and fails closed if it is inside Abstract/Keywords, regardless of candidate-supplied section text.
- `CitationInjector` re-evaluates the actual manuscript line immediately before every zero-width new-citation insertion. Non-zero-width legacy replacements remain allowed.
- Added `keywords` / `key words` / `关键词` to the existing multilingual section-classifier policy.

## Regression Result
- ISSUE-008 focused regression: 18/18 PASS.
- Related SemanticMapper/Adapter/Injector and ISSUE-004/005 tests: 107/107 PASS.
- Full existing suite: 474/474 PASS.
- Golden Dataset integrity: PASS.
- Real manuscript before: Abstract body 16 new citations; Keywords 3; total protected-zone violations 19.
- Real manuscript after: Abstract body 0 new citations; Keywords 0; total protected-zone violations 0.
- Real manuscript body injection: 79/79 planned CiteKeys injected; no injection errors.
- Legacy regression: 59/59 mapped, 123/123 occurrences migrated, residual 0, and 59/59 old CiteKeys preserved.

## Fixed In
v2.5.x — 2026-08-19

## Notes
This is independent of ISSUE-004. The production fixture had no legacy citations in the Abstract/Keywords block, so all 19 observed CiteKeys are new Phase 3/5 injections.
