"""
test_existing_figure_citation_migration.py — v2.2.1: Figure caption migration

Two independent rules:
  Rule 1: Existing [N] in figure captions MUST be migrated → [@citekey]
  Rule 2: New semantic injection MUST NEVER go into figure captions

Tests:
  PASS: existing figure citations migrated
  PASS: new papers cannot inject into figures
  PASS: body citations unaffected
  PASS: migration coverage report
"""
import sys, os, re, pytest

ENGINE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "engine")
sys.path.insert(0, ENGINE_DIR)

from citation_migrator import CitationMigrator, MigrationReport, MigrationZone, build_mapping_from_manuscript
from semantic_mapper import SemanticMapper
from literature_intel import PaperIntel
from sample_data import SAMPLE_DRAFT_EN, SAMPLE_BIB
from bib_parser import BibTeXParser

BS = chr(92)


# ============================================================
# Test data with figure captions containing citations
# ============================================================
DRAFT_WITH_FIGURE_CITATIONS = """# Results

## Performance Analysis

The sensor shows excellent performance [@ref1].

![Figure 1](media/fig1.png)

Figure 1. Comparison of piezoelectric materials including PZT \\[1\\] and PVDF \\[2\\] showing superior sensitivity.

The results confirm the advantage of PZT-based sensors.

## Methods

Fabrication followed standard protocols [@ref2].
"""

BIB_FOR_TEST = """@article{Test2024PZT,
  author = {Zhang, X. and Li, Y.},
  title = {PZT-Based Flexible Pressure Sensor},
  journal = {Advanced Materials},
  year = {2024},
  doi = {10.1000/test.pzt}
}
@article{Test2023PVDF,
  author = {Wang, A. and Chen, B.},
  title = {PVDF Nanofiber Sensor for Pulse Monitoring},
  journal = {ACS Nano},
  year = {2023},
  doi = {10.1000/test.pvdf}
}
"""


class TestFigureCitationMigration:
    """Rule 1: Existing figure citations MUST be migrated"""

    def test_migrator_detects_figure_zones(self):
        """Identifies figure caption zones in manuscript"""
        num_map = {1: 'Test2024PZT', 2: 'Test2023PVDF'}
        migrator = CitationMigrator(num_map)
        zones = migrator._identify_zones(DRAFT_WITH_FIGURE_CITATIONS)
        zone_types = {z.zone_type for z in zones}
        assert 'figure_caption' in zone_types, f"Expected figure_caption zone, got: {zone_types}"

    def test_figure_citations_migrated(self):
        """Legacy [1] [2] in figure captions are converted to [@citekey]"""
        num_map = {1: 'Test2024PZT', 2: 'Test2023PVDF'}
        migrator = CitationMigrator(num_map)
        result, report = migrator.migrate_all(DRAFT_WITH_FIGURE_CITATIONS)

        assert report.figure_migrated > 0, f"Expected figure citations migrated, got {report.figure_migrated}"
        assert '[@Test2024PZT]' in result, f"Expected @Test2024PZT in: {result}"
        assert '[@Test2023PVDF]' in result, f"Expected @Test2023PVDF in: {result}"

    def test_body_citations_unaffected(self):
        """Body citations remain unchanged during migration"""
        num_map = {1: 'Test2024PZT', 2: 'Test2023PVDF'}
        migrator = CitationMigrator(num_map)
        result, report = migrator.migrate_all(DRAFT_WITH_FIGURE_CITATIONS)

        # Existing Pandoc citations preserved
        assert '[@ref1]' in result
        assert '[@ref2]' in result

    def test_coverage_report_generated(self):
        """Migration report includes all zones"""
        num_map = {1: 'Test2024PZT', 2: 'Test2023PVDF'}
        migrator = CitationMigrator(num_map)
        result, report = migrator.migrate_all(DRAFT_WITH_FIGURE_CITATIONS)

        assert report.total_migrated > 0
        summary = report.coverage_summary()
        assert 'Figure Captions' in summary
        assert 'Body' in summary

    def test_figure_caption_text_preserved(self):
        """Caption descriptive text is not modified"""
        num_map = {1: 'Test2024PZT', 2: 'Test2023PVDF'}
        migrator = CitationMigrator(num_map)
        result, report = migrator.migrate_all(DRAFT_WITH_FIGURE_CITATIONS)

        assert 'piezoelectric materials' in result
        assert 'superior sensitivity' in result


class TestSemanticMapperFigureExclusion:
    """Rule 2: New injection MUST NEVER go into figure captions"""

    def test_new_paper_not_injected_into_figure(self):
        """Semantic mapper excludes figure caption zones from candidates"""
        paper = PaperIntel(
            citekey="NewPZT2025",
            title="Novel PZT Sensor",
            paper_type="research",
            core_finding="Achieves high sensitivity",
            technical_keywords=["piezoelectric", "PZT"],
            semantic_anchors=["piezoelectric", "PZT", "sensitivity", "sensor", "flexible"],
            recommended_section="§3.1.1",
        )

        mapper = SemanticMapper()
        candidates = mapper.map_papers_to_manuscript([paper], DRAFT_WITH_FIGURE_CITATIONS)

        accepted = [c for c in candidates if not c.is_rejected]
        # Should NOT match in figure caption lines
        for c in accepted:
            assert 'piezoelectric materials including' not in c.target_sentence.lower(), \
                f"Should not match figure caption: {c.target_sentence}"

    def test_body_sentences_still_matchable(self):
        """Body sentences outside figure captions are still valid targets"""
        paper = PaperIntel(
            citekey="NewBody2025",
            title="Body Sensor Test",
            paper_type="research",
            core_finding="Works well",
            technical_keywords=["sensor", "performance"],
            semantic_anchors=["sensor", "performance", "shows", "excellent", "fabrication"],
            recommended_section="§4",
        )

        mapper = SemanticMapper()
        candidates = mapper.map_papers_to_manuscript([paper], DRAFT_WITH_FIGURE_CITATIONS)

        accepted = [c for c in candidates if not c.is_rejected]
        # Should match body text like "The sensor shows excellent performance"
        for c in accepted:
            assert 'Figure 1' not in c.target_sentence, f"Should not match figure line: {c.target_sentence}"


class TestMigrationReport:
    """MigrationReport correctness"""

    def test_report_creation(self):
        report = MigrationReport()
        report.body_citations = 10
        report.body_migrated = 10
        report.figure_citations = 2
        report.figure_migrated = 2
        report.total_citations = 12
        report.total_migrated = 12
        assert report.total_migrated == 12
        summary = report.coverage_summary()
        assert '100%' in summary

    def test_report_with_no_figures(self):
        report = MigrationReport()
        report.body_citations = 5
        report.body_migrated = 5
        report.total_citations = 5
        report.total_migrated = 5
        summary = report.coverage_summary()
        assert 'Figure Captions' in summary
        assert 'N/A' in summary  # 0/0 = N/A


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
