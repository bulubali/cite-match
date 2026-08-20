# CiteMatch v2.5 — Feature Checklist

| # | Feature | Status | Version | Date | Files Changed | Tests |
|---|---------|--------|---------|------|---------------|-------|
| 1 | Phase 7 Mapping Report (md+csv+BOM) | DONE | v2.5.0 | 2026-07-24 | `engine/mapping_report.py` | `test_mapping_report.py` (7) |
| 2 | Journal Style Compile Pipeline | DONE | v2.5.0 | 2026-07-24 | `converters/journal_compiler.py` | `test_pandoc_builder.py` (TBD) |
| 3 | CSL Modifier (ElementTree) | DONE | v2.5.0 | 2026-07-24 | `converters/csl_modifier.py` | `test_csl_modifier.py` (7) |
| 4 | Cross-Reference Protection | DONE | v2.5.0 | 2026-07-24 | `engine/crossref_guard.py` | `test_crossref_guard.py` (8) |
| 5 | Post-Injection Citation Merge | DONE | v2.5.0 | 2026-07-24 | `engine/crossref_guard.py` (merge_adjacent_citations) | (in test_crossref_guard) |
| 6 | Bilingual Utils (normalize_brackets) | DONE | v2.5.0 | 2026-07-24 | `engine/bilingual_utils.py` | `test_bilingual_utils.py` (8) |
| 7 | BBT File Field Blocking | DONE | v2.5.0 | 2026-07-26 | `engine/literature_intel.py` | acceptance test |
| 8 | DOCX Conversion Warning | DONE | v2.5.0 | 2026-07-26 | `converters/pandoc_adapter.py` | acceptance test |
| 9 | Golden Dataset | DONE | v2.5.0 | 2026-07-26 | `tests/golden_dataset/` (7 files) | `verify_golden_dataset.py` |
| 10 | Figure Caption Exclusion (fix) | DONE | v2.5.0 | 2026-07-26 | `engine/semantic_mapper.py` | regression + acceptance |
| 11 | Real Manuscript Acceptance | DONE | v2.5.0 | 2026-07-26 | acceptance test | 27/27 PASS |
