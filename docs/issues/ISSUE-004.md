# ISSUE-004

## Title
Legacy Citation Migration Missing — Old `^[num]^` Citations Not Converted to Pandoc `[@key]`

## Priority
P0

## Status
Regression Testing — Fix applied, awaiting final acceptance

## Fix Applied
- **Date:** 2026-07-27
- **Files Added:** `engine/legacy_migration.py` (200 lines)
- **Files Added:** `tests/regression/test_issue_004.py` (5 tests)
- **Pipeline:** Inserted between Mode C and Phase 1
- **Method:** Parse old References section → fuzzy author+year+title match → replace `^[num]^` with `[@key]`

## Fix Results
| Metric | Before | After |
|--------|--------|-------|
| Reference mapping | 0/59 (0%) | 59/59 (100%) |
| Old `^[num]^` in body | 121 | 0 |
| Migrated Pandoc `[@key]` | 0 | 121 |
| Bibliography entries | 98 | 125 |
| Regression tests | — | 5/5 PASS |
| Production Validation | FAIL | PASS |

## Version Found
v2.5.x (Production Validation 2026-07-27)

## Environment
- OS: Windows 11
- Input: `Template.docx` with 59 hard-coded numeric references + `references.bib` (182 entries)

## Steps to Reproduce
1. Take a `.docx` manuscript with numeric citations like `[1,2]` and a static References section with 59 entries
2. Run Mode C → References section is removed, but body citations remain as `^\[1,2\]^`
3. Run Phase 1 → 0 Pandoc keys detected, all 182 .bib entries treated as "new" (Pending_Keys)
4. Run Phase 2-3 → 57 new `[@key]` citations injected alongside old `^\[num\]^` citations
5. Run Phase 5 → injection succeeds, but old citations are untouched
6. Run Phase 6 (`pandoc --citeproc`) → new `[@key]` citations are resolved, old `^\[1,2\]^` appear as **literal text** in DOCX

## Expected Behavior
The pipeline should:
1. Parse the old References section to extract author/year/title metadata for each [1]-[59]
2. Map each old reference number to its corresponding .bib CiteKey via author/year fuzzy matching
3. Replace all `^\[1,2\]^` instances with Pandoc `[@key1; @key2]` format
4. This step should occur between Mode C and Phase 1 (or as an extension of Phase 1)

## Actual Behavior
- Mode C only removes the References section (8,209 chars, 59 entries) but leaves 121 body citations in `^\[num\]^` format
- No phase in the pipeline maps old numbers → .bib keys
- Phase 1 treats all 182 .bib entries as "pending" because 0 Pandoc keys are found
- After Phase 5 injection, the draft has both new `[@key]` citations AND old `^\[num\]^` citations
- The 59 papers already cited in the original draft are effectively **lost** — Pandoc won't recognize them

## Severity
- **Root Cause (Initial):** The SKILL.md pipeline design assumes manuscripts already use Pandoc `[@key]` format. There is no `LegacyCitationMapper` phase to handle the common case of Word documents with numeric citations. Mode C's scope is limited to removing the References section, not converting body citations.
- **Related Phase:** Between Mode C and Phase 1 (missing phase)
- **Files Involved:**
  - SKILL.md — Mode C and Phase 1 definitions
  - No engine module exists for legacy citation mapping

## Minimal Fix Plan
1. Add a `LegacyCitationMapper` step between Mode C and Phase 1:
   a. Parse old References section entries (author, year, title, journal)
   b. For each entry, find the best-matching .bib CiteKey using fuzzy author+year+title matching
   c. Build a mapping: `{1: @key1, 2: @key2, ..., 59: @key59}`
   d. Replace all `^\[1,2\]^` → `[@key1; @key2]` in the draft body
   e. Report any unmapped references to user
2. After mapping, Phase 1 delta detection correctly identifies Used_Keys and Pending_Keys
3. **No refactoring** — add one Python module, insert one pipeline step

## Regression Test
Plan: `tests/regression/test_issue_004_legacy_migration.py`
- Test: .docx with 5 numeric refs → all 5 mapped to correct .bib keys
- Test: multi-citation `[1,2]` → `[@key1; @key2]`
- Test: unmappable reference → reported to user, not silently dropped
- Test: no duplicate injection (existing papers not re-added as "new")

## Acceptance Result
PENDING

## Notes
- 58 unique reference numbers in body (1-59, missing #23)
- 59 entries in original References section
- Most-cited: [2] (10x), [6] (8x), [13] (8x), [14] (8x), [16] (8x), [28] (6x), [39] (8x)
- Without this fix, Pandoc compile produces broken output for any manuscript with legacy numeric citations
- **This is a showstopper for real-paper usage**
