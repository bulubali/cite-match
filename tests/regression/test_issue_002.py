"""ISSUE-002: non-pipe tables must never be treated as body prose."""
from pathlib import Path
from types import SimpleNamespace
import sys

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[2]
ENGINE_DIR = PROJECT_ROOT / "engine"
if str(ENGINE_DIR) not in sys.path:
    sys.path.insert(0, str(ENGINE_DIR))
VALIDATION_DIR = PROJECT_ROOT / "tests" / "production_validation"
if str(VALIDATION_DIR) not in sys.path:
    sys.path.insert(0, str(VALIDATION_DIR))

from candidate_adapter import adapt_semantic_candidates
from citation_registry import CitationRegistry
from injector import CitationInjector
from md_ast import MarkdownAST
from validators.table_validator import TableValidator


PIPE_TABLE = """| Category | Evidence | Reference |
|---|---|---|
| A | Target sentence. | [@Existing] |
"""

SIMPLE_TABLE = """  ------------------------------------------------------------------------
  **Category**       **Evidence**                         **Reference**
  ------------------ ------------------------------------ ----------------
  A                  Target sentence.                     [@Existing]
  ------------------------------------------------------------------------
"""

GRID_TABLE = """+----------+----------------------+----------------+
| Category | Evidence             | Reference      |
+==========+======================+================+
| A        | Target sentence.     | [@Existing]    |
+----------+----------------------+----------------+
"""


def _candidate(target: str, citekey: str = "VeryLongCitationKeyForTableSafety2026"):
    return SimpleNamespace(
        is_rejected=False,
        target_sentence=target,
        section="Results",
        similarity_score=1.0,
        paper=SimpleNamespace(citekey=citekey),
    )


@pytest.mark.parametrize(
    ("source", "expected_format"),
    [(PIPE_TABLE, "pipe"), (SIMPLE_TABLE, "simple"), (GRID_TABLE, "grid")],
)
def test_all_supported_table_formats_are_recognized(source, expected_format):
    ast = MarkdownAST(source)
    ast.parse()

    line_number = next(
        index for index, line in enumerate(source.splitlines(), 1)
        if "Target sentence." in line
    )
    assert ast._is_in_table(line_number)
    assert ast.table_format_for_line(line_number) == expected_format


@pytest.mark.parametrize("source", [SIMPLE_TABLE, GRID_TABLE])
def test_non_pipe_targets_are_marked_as_table_candidates(source):
    plan = adapt_semantic_candidates([_candidate("Target sentence.")], source)
    assert len(plan) == 1
    assert plan[0][0].is_in_table is True


@pytest.mark.parametrize("source", [SIMPLE_TABLE, GRID_TABLE])
def test_non_pipe_table_injection_is_fail_closed_and_content_is_unchanged(source):
    original_rows = source.splitlines()
    plan = adapt_semantic_candidates([_candidate("Target sentence.")], source)
    injector = CitationInjector(CitationRegistry())
    injector.set_document(source)

    result = injector.inject_candidates(plan, auto_confirm=True)

    assert result.splitlines() == original_rows
    assert "VeryLongCitationKeyForTableSafety2026" not in result
    assert "?" not in result
    assert any(log["action"] == "skip_unsafe_table" for log in injector.injection_log)
    assert not any(log["action"] == "inject" for log in injector.injection_log)


def test_pipe_table_keeps_existing_safe_injection_behavior():
    plan = adapt_semantic_candidates([_candidate("Target sentence.")], PIPE_TABLE)
    injector = CitationInjector(CitationRegistry())
    injector.set_document(PIPE_TABLE)

    result = injector.inject_candidates(plan, auto_confirm=True)

    assert "Target sentence [@VeryLongCitationKeyForTableSafety2026]." in result
    assert [line.count("|") for line in result.splitlines()] == [
        line.count("|") for line in PIPE_TABLE.splitlines()
    ]


def test_existing_table_validator_reports_non_pipe_tables(tmp_path):
    manuscript = tmp_path / "simple-table.md"
    manuscript.write_text(SIMPLE_TABLE, encoding="utf-8")

    findings = TableValidator(str(manuscript)).validate()

    assert any(
        finding.check == "Non-pipe Table Detection" and finding.severity == "PASS"
        for finding in findings
    )


@pytest.mark.parametrize(
    ("target", "citekey"),
    [
        ("It is suitable for skin patches, textile devices, and concealed wearable systems.",
         "qiWeavableStretchablePiezoresistive2020"),
        ("Piezoresistive, ionic or capacitive modes, and fabric integrated systems.",
         "zhangHighlyAccurateFlexible2022"),
        ("Epidermal wearable systems, neonatal monitoring, and intraoperative attached devices.",
         "zhangFlexibleSphereElastomer2024"),
        ("Thin film integration, printed electronics, miniature wireless modules, flexible batteries, heterogeneous packaging, and synergistic integration of sensors and actuators.",
         "changIntegrationChemicalPhysical2025"),
    ],
)
def test_real_production_table_targets_are_skipped_without_cell_text_mutation(target, citekey):
    private_source = (
        PROJECT_ROOT / "output" / "issue005_real_user_acceptance_r3" /
        "migrated.md"
    )
    if not private_source.is_file():
        pytest.skip("Private ISSUE-002 production evidence is not distributed.")
    source = private_source.read_text(encoding="utf-8")
    plan = adapt_semantic_candidates([_candidate(target, citekey)], source)
    assert plan[0][0].is_in_table is True

    injector = CitationInjector(CitationRegistry())
    injector.set_document(source)
    result = injector.inject_candidates(plan, auto_confirm=True)

    assert result == source
    assert citekey not in result
    assert any(log["action"] == "skip_unsafe_table" for log in injector.injection_log)
