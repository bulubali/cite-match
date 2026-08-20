# CiteMatch v2.5.x — Production Validation Checklist

> **Rule:** Every code change MUST pass ALL items before merge.
> Last updated: 2026-07-27

---

## Pre-Validation

- [ ] All unit tests PASS (`pytest tests/ -x`)
- [ ] Golden Dataset verification PASS (`python tests/golden_dataset/verify_golden_dataset.py`)
- [ ] No uncommitted changes in engine/
- [ ] Validation config reviewed and current

---

## Phase 00 — BBT & Bib Integrity

- [ ] `.bib` file exists and is non-empty
- [ ] `.bib` file parseable (no syntax errors)
- [ ] BBT `file` field present for ≥50% of entries
- [ ] PDF paths in `file` field resolvable where present

## Phase 0 — Toolchain

- [ ] Pandoc ≥3.0 installed and accessible
- [ ] `pandoc-crossref` installed and accessible
- [ ] PyMuPDF (`fitz`) importable
- [ ] Python ≥3.10

## Phase 1 — Delta Detection & IF Gate

- [ ] Pending keys correctly computed: `All_Keys - Used_Keys`
- [ ] IF threshold applied and documented
- [ ] User confirmation recorded (if interactive)
- [ ] Ghost duplicates checked: no duplicate citekeys for same paper

## Phase 2 — References Summary

- [ ] `References_Summary.md` generated
- [ ] All required fields present: citekey, title, paper_type, core_finding, keywords, anchors, section
- [ ] Review papers correctly classified (title/abstract contains review markers)
- [ ] Semantic anchors ≥2 per paper
- [ ] PDF availability status reported

## Phase 3 — Semantic Mapping & Injection Rules

- [ ] Citation Candidate Table generated
- [ ] No new injection into Abstract zone
- [ ] No new injection into Figure Caption zone
- [ ] "This work"/"We propose" sentences protected
- [ ] Review papers routed to Introduction/Background only
- [ ] Sentence density ≤5 (max 3 papers per sentence for new injections)
- [ ] Paragraph density ≤12 (≤18 for review sections)
- [ ] Table citations obey Elite IF gate
- [ ] No table structure damage from injection

## Phase 4 — Floating References

- [ ] Floating references documented in report
- [ ] AI expansion markers present for floating refs
- [ ] Floating count ≤20% of pending

## Phase 5 — Safety Protocol

- [ ] Backup created before any write operation
- [ ] Dry-run mode available and tested
- [ ] CrossRef references (`fig:`, `tbl:`, `eq:`) protected
- [ ] Adjacent citations properly merged

## Phase 6 — Journal & CSL & Pandoc & DOCX

- [ ] Target journal name recorded
- [ ] CSL file downloaded or selected
- [ ] CSL `collapse="citation-number"` applied
- [ ] CSL `et-al` modification applied (if user requested)
- [ ] Pandoc compilation succeeded
- [ ] DOCX file generated and non-empty (≥100KB)
- [ ] `link-citations=true` enabled

## Phase 7 — Mapping Report

- [ ] `CiteMatch_Mapping_Report.md` generated
- [ ] `CiteMatch_Mapping_Report.csv` generated with UTF-8 BOM
- [ ] All injected citekeys present in mapping
- [ ] SequenceMatcher similarity scores recorded
- [ ] No missing citekeys in final manuscript

---

## Post-Validation

- [ ] `validation_statistics.json` generated
- [ ] `Production_Validation_Report.md` generated
- [ ] Overall score ≥90%
- [ ] No FAIL items
- [ ] All WARNING items reviewed and triaged
- [ ] Output comparison vs Golden Dataset: diff ≤5%

---

## Sign-off

| Role | Name | Date | Status |
|------|------|------|--------|
| Developer | | | |
| Reviewer | | | |
