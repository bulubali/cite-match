# CiteMatch v2 — Trigger Rules

## Activation Keywords

### Chinese

- 文献匹配
- 引文匹配
- 补充引用
- 添加引用
- 自动引用
- 参考文献匹配
- 综述引用优化
- citation匹配
- 引用迁移
- 引文迁移
- 文献补充

### English

- citation matching
- citation insertion
- reference matching
- manuscript citation
- literature matching
- add citations
- citation migration
- review manuscript

## Activation Conditions

Activate when user provides:

- manuscript draft / review article draft / DOCX / Markdown
- BibTeX / Zotero library

AND requests:

- citation improvement / reference completion / literature matching / citation placement

## Default Mode

Mode A — Full Pipeline: Phase 00 → Phase 7

## Journal Rules

Only ask:
1. Target journal name
2. Full author list or et al.

Auto-resolve journal aliases. Default CSL: `nature.csl`.

## Confirmation Required

- Phase 00: BBT validation failure
- Phase 1: IF filtering threshold
- Phase 2: References Summary review
- Phase 3: Table citation injection
- Phase 5: Manuscript modification
- Phase 6: Final DOCX generation

## Output Rule

`[系统状态]: Current Phase: X` before each transition. One Phase per interaction.
