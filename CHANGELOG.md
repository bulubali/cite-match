# CiteMatch Changelog

## v2.5.0-rc.1 (2026-08-20) — Release Candidate

- Production RC frozen after Real User Production Acceptance.
- Release distribution excludes private manuscripts, BibTeX/Zotero exports, Golden fixtures, workflow state, and production artifacts.
- Added public release documentation, dependency guidance, third-party CSL notice, and a distributable Installed Skill copy.
- Deferred: ISSUE-009 IF Resolution Provenance and Provider Integration.

## v2.4.2 (2026-07-24) — Workflow Layer

- Workflow orchestration: `workflows/manuscript_workflow.py`, `workflows/zotero_workflow.py`
- Document conversion: `converters/pandoc_adapter.py`
- Export: `exporters/docx_exporter.py`
- Environment checker: `installers/environment_checker.py`
- Project structure refactor: workflows/, converters/, exporters/, installers/

## v2.4.0 — Stable Baseline

- Policy-driven architecture with YAML profiles
- Multilingual section classifier (en + zh)
- Journal IF database externalized to YAML
- Safe failure mode (missing profile → default)
- 361 tests

## v2.3.3 — Safe Fallback

- IF gate defaults to disabled when policy unavailable

## v2.3.2 — Interactive IF Gate

- User confirmation prompt and runtime threshold override

## v2.3.0 — Policy Engine

- `engine/policy_manager.py`, `engine/density_controller.py`
- Three configurable profiles

## v2.2.0 — Literature Intelligence

- `engine/literature_intel.py`, `engine/semantic_mapper.py`, `engine/floating_refs.py`

## v2.1.0 — Bilingual Sync

- `engine/bilingual_validator.py`, `engine/bilingual_sync.py`

## v2.0.0 — Python Engine

- State machine, AST parser, Citation Registry, multi-strategy matcher, AST-aware injector
