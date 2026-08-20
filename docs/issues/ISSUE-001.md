# ISSUE-001

## Title
Journal Alias Matching Failure — IF Database fails to match journal name variants

## Priority
P0

## Status
Closed

## Version Found
v2.5.x (Production Validation 2026-07-27)

## Environment
- OS: Windows 11
- Python: 3.11
- Input: `Template.docx` + `血压监测传感器文献.bib` (182 entries)

## Steps to Reproduce
1. Load `references.bib` containing journal names in full/spelled-out forms
2. Run `BodyCitationIFGate._resolve_if()` against `if_database.yaml`
3. Observe that exact/substring matching fails for name variants

## Expected Behavior
Journal names with common variants should match correctly:
- `Advanced Materials` → `Adv. Mater.` (IF=27.4)
- `Advanced Science` → `Adv. Sci.` (IF=14.3)
- `Adv Funct Materials` → `Adv. Funct. Mater.` (IF=15.6)
- `Chemical Engineering Journal` → `Chem. Eng. J.` (IF=13.2)
- `Nat Med` → `Nat. Med.` (IF≈58)
- `Natl. Sci. Rev.` → IF≈16
- `Biosensors and Bioelectronics` → `Biosens. Bioelectron.` (IF=10.7)

## Actual Behavior
51 out of 182 entries (~28%) fall into UNKNOWN state due to journal name variant mismatch. At least ~15 of these are clear matches with incorrect name normalization. Examples include:
- `Advanced Materials` (2 papers) not matched to `Adv. Mater.`
- `Adv Funct Materials` (2 papers) not matched to `Adv. Funct. Mater.`
- `Nat Med` not matched to any entry
- `Chemical Engineering Journal` not matched to `Chem. Eng. J.`

## Severity
- **Root Cause (Initial):** `_resolve_if()` in `engine/body_if_gate.py:421-446` uses simple normalization (lowercase + remove dots/spaces) but lacks a **journal alias/expansion table**. Common full journal names (e.g., "Advanced Materials") are not recognized as aliases for abbreviated forms (e.g., "Adv. Mater.").
- **Related Phase:** Phase 1 (Global IF Gatekeeper)
- **Files Involved:**
  - `engine/body_if_gate.py` — `_resolve_if()` method, `JOURNAL_IF_MAP`
  - `profiles/journals/if_database.yaml` — lacks alias entries
  - `profiles/journals/if_database.yaml` — missing ~20 common journals

## Minimal Fix Plan
1. Add reviewed, explicit aliases in the canonical `if_database.yaml`; every alias must target an existing `journals` key.
2. Normalize only formatting differences (periods, commas, whitespace), then resolve explicit aliases before direct lookup.
3. Remove the unsafe generic substring fallback: it could map an unrelated title such as `Advanced Material Science` to `science`.
4. Keep journals without a canonical IF database entry as `UNKNOWN`; IF database coverage requires separately sourced, versioned data maintenance and was not populated from this manuscript.
5. **No refactoring** — minimal configuration and lookup changes only.

## Regression Test
`tests/regression/test_issue_001_journal_alias.py`

- Explicit abbreviation, full-name, whitespace, period, and comma variants resolve through canonical YAML aliases.
- Alias targets must be existing IF database keys.
- Unknown and near-name journals remain `UNKNOWN`; no broad normalization collision is allowed.
- Related Body/Table policy and `IF_UNKNOWN_REVIEW` tests remain green.

## Acceptance Result
PASS — 2026-08-20

- Focused/related tests: **97 passed**.
- Full Suite: **512 passed, 3 skipped**.
- Golden Dataset: **PASS**.
- Real paused-workflow matcher regression: **43 UNKNOWN candidates → 14 resolved aliases + 29 TRUE_UNKNOWN**.
- The 14 confirmed `ALIAS_MATCH_FAILURE` cases resolve to existing canonical IF entries; no citekey- or fixture-specific rule was added.
- The remaining 29 candidates have journal metadata but no existing IF database coverage. They remain `UNKNOWN` and preserve the `IF_UNKNOWN_REVIEW` Safety Interrupt.

## Notes
- Original ISSUE-001 includes both title matching and a future database-coverage expansion. This stabilization closes the confirmed alias-matching defect only; it does not invent or infer values for uncovered journals.
- The IF database remains the canonical YAML source. Its current schema had no sourced/versioned coverage-maintenance policy for safely adding the 29 remaining titles.
- ISSUE-005 Real User Acceptance remains paused at `IF_UNKNOWN_REVIEW`; no unknown candidate was approved, excluded, injected, or deleted.
