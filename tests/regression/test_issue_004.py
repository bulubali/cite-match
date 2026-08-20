"""ISSUE-004 regression: production Workflow migrates all legacy citations."""
from pathlib import Path
import re
import sys

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_DIR = PROJECT_ROOT / "workflows"
OUTPUT_DIR = PROJECT_ROOT / "output"
sys.path.insert(0, str(WORKFLOW_DIR))

from manuscript_workflow import ManuscriptWorkflow, PRODUCTION_ENTRY_ID


LEGACY_CITATION_RE = re.compile(r"\^\\\[([^\]]+?)\\\]\^")
LEGACY_REFERENCE_RE = re.compile(r"^\\\[(\d+)\\\]\s+", re.MULTILINE)


@pytest.fixture
def production_fixture() -> tuple[Path, Path]:
    manuscript = OUTPUT_DIR / "draft_mode_c_backup.md"
    bib = OUTPUT_DIR / "references.bib"
    if not manuscript.exists() or not bib.exists():
        pytest.skip("ISSUE-004 production fixture is not present")
    return manuscript, bib


def test_production_workflow_migrates_real_fixture_safely(
    production_fixture, tmp_path
):
    manuscript, bib = production_fixture
    original = manuscript.read_text(encoding="utf-8")

    assert len(set(LEGACY_REFERENCE_RE.findall(original))) == 59
    assert len(LEGACY_CITATION_RE.findall(original)) == 121

    workflow = ManuscriptWorkflow(
        str(manuscript), str(bib), str(tmp_path / "issue-004-output")
    )
    result = workflow.run(mode="C", dry_run=True)

    assert result["status"] == "completed", result
    assert result["entry"] == PRODUCTION_ENTRY_ID
    assert result["data"]["mapping"] == {
        "total": 59,
        "mapped": 59,
        "unmapped": 0,
        "ambiguous": 0,
        "unsafe": 0,
        "mapping_pct": 100.0,
    }
    assert result["data"]["legacy_occurrences"] == 121
    assert result["data"]["migrated_occurrences"] == 121
    assert result["data"]["legacy_numeric_occurrences"] == 2
    assert result["data"]["migrated_numeric_occurrences"] == 2
    assert result["data"]["total_migrated_occurrences"] == 123
    assert result["data"]["residual_superscript"] == 0
    assert result["data"]["residual_numeric"] == 0
    assert result["data"]["references_removed"] is True
    assert result["data"]["used_references"] == 59
    assert result["data"]["pending_references"] == 123

    migrated = workflow.last_markdown
    assert len(LEGACY_CITATION_RE.findall(migrated)) == 0
    assert re.search(
        r"^\*\*References\*\*\s*$", migrated, re.MULTILINE
    ) is None
    assert LEGACY_REFERENCE_RE.search(migrated) is None
    assert len(result["data"]["used_keys"]) == 59
    assert all(f"@{key}" in migrated for key in result["data"]["used_keys"])


def test_issue_004_regression_does_not_write_repository_output(
    production_fixture, tmp_path
):
    manuscript, bib = production_fixture
    temporary_output = tmp_path / "isolated-output"
    workflow = ManuscriptWorkflow(
        str(manuscript), str(bib), str(temporary_output)
    )

    result = workflow.run(mode="C", dry_run=True)

    assert result["status"] == "completed", result
    assert result["outputs"]["markdown"] is None
    assert not temporary_output.exists()
