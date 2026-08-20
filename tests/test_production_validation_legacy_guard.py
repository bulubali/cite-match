"""Production-validation guard for residual ISSUE-004 citations."""
from pathlib import Path
import sys


VALIDATION_DIR = Path(__file__).parent / "production_validation"
sys.path.insert(0, str(VALIDATION_DIR))

from validators.injection_validator import InjectionValidator


def test_residual_legacy_citation_is_p0_failure(tmp_path):
    manuscript = tmp_path / "injected.md"
    manuscript.write_text(
        "# Results\n\nA claim still has ^\\[12\\]^ here.\n",
        encoding="utf-8",
    )

    findings = InjectionValidator(str(manuscript)).validate()
    legacy = next(
        finding for finding in findings
        if finding.check == "Legacy Citation Migration"
    )

    assert legacy.severity == "FAIL"
    assert "P0" in legacy.detail
    assert "^\\[12\\]^" in legacy.detail


def test_pandoc_citation_passes_legacy_guard(tmp_path):
    manuscript = tmp_path / "migrated.md"
    manuscript.write_text(
        "# Results\n\nA migrated claim [@Author2024].\n",
        encoding="utf-8",
    )

    findings = InjectionValidator(str(manuscript)).validate()
    legacy = next(
        finding for finding in findings
        if finding.check == "Legacy Citation Migration"
    )

    assert legacy.severity == "PASS"
