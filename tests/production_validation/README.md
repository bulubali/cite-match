# CiteMatch v2.5.x — Production Validation Framework

Long-term production validation system for the CiteMatch Engine.
Independent from the Golden Dataset (which handles regression testing).

## Architecture

```
tests/production_validation/
├── README.md                    ← This file
├── validation_runner.py         ← Main orchestrator
├── validation_report.py         ← Report generator (MD + JSON)
├── validation_config.yaml       ← Thresholds and paths
├── production_checklist.md      ← Manual checklist
├── statistics.py                ← Metrics computation
├── compare_outputs.py           ← Golden Dataset comparison
├── validators/
│   ├── citation_validator.py    ← Phase 00,1: Bib integrity, pending keys
│   ├── mapping_validator.py     ← Phase 7: Mapping report, CSV, similarity
│   ├── pandoc_validator.py      ← Phase 0,6: Pandoc toolchain
│   ├── csl_validator.py         ← Phase 6: CSL modification
│   ├── injection_validator.py   ← Phase 3,5: Injection rules, crossref
│   ├── density_validator.py     ← Phase 3: Sentence/paragraph density
│   ├── table_validator.py       ← Phase 3: Table IF gate, table damage
│   ├── figure_validator.py      ← Phase 3: Figure caption protection
│   ├── floating_validator.py    ← Phase 4: Floating references
│   └── summary_validator.py     ← Phase 2: References Summary
└── reports/                     ← Generated reports
```

## Quick Start

```bash
# Run full validation
python tests/production_validation/validation_runner.py

# Run specific validator
python tests/production_validation/validators/citation_validator.py

# Compare with golden dataset
python tests/production_validation/compare_outputs.py
```

## Output

| File | Description |
|------|-------------|
| `reports/Production_Validation_Report.md` | Human-readable report |
| `reports/validation_statistics.json` | Machine-readable metrics |
| `reports/comparison_report.md` | Golden dataset comparison |

## Severity Levels

- **PASS (✅)** — All checks passed
- **WARNING (⚠️)** — Non-blocking issue with root cause analysis
- **FAIL (❌)** — Blocking issue; must be fixed before proceeding

## Integration

This framework validates the engine output at `cite-match_v2/output/`.
The Golden Dataset lives at `tests/golden_dataset/`.
Both must pass before any engine code change is accepted.
