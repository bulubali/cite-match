"""test_mapping_report.py — v2.5: Phase 7 Mapping Report"""
import sys, os, pytest, tempfile

ENGINE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "engine")
sys.path.insert(0, ENGINE_DIR)

from mapping_report import MappingReportGenerator, MappingReport, MappingEntry


@pytest.fixture
def gen():
    return MappingReportGenerator()


class TestMappingReport:
    def test_generates_markdown(self, gen):
        original = "Text [@KeyA] and [@KeyB]. More text here for context padding."
        migrated = "Text [@KeyA] and [@KeyB] and new [@KeyC]."
        report = gen.generate(original, migrated)
        md = report.to_markdown()
        assert "KeyA" in md
        assert "KeyB" in md
        assert "KeyC" in md

    def test_new_citation_detected(self, gen):
        original = "Text [@KeyA]."
        migrated = "Text [@KeyA] and [@KeyB]."
        report = gen.generate(original, migrated)
        assert report.new_citations == 1

    def test_missing_key_detected(self, gen):
        original = "Text [@KeyA] and [@KeyB]."
        migrated = "Text [@KeyA]."
        report = gen.generate(original, migrated)
        assert len(report.missing_keys) == 1
        assert "KeyB" in report.missing_keys

    def test_csv_has_bom(self, gen):
        report = gen.generate("[@KeyA].", "[@KeyA].")
        csv_content = report.to_csv()
        assert csv_content[0] == chr(0xFEFF)

    def test_sequence_matcher_used(self, gen):
        original = "Flexible piezoelectric blood pressure sensor [@KeyA]."
        migrated = "Flexible piezoelectric blood pressure sensor [@KeyA]."
        report = gen.generate(original, migrated)
        assert report.entries[0].anchor_similarity > 0.9

    def test_save_markdown(self, gen, tmp_path):
        report = gen.generate("[@KeyA].", "[@KeyA].")
        path = str(tmp_path / "report.md")
        gen.save_markdown(report, path)
        assert os.path.exists(path)

    def test_save_csv(self, gen, tmp_path):
        report = gen.generate("[@KeyA].", "[@KeyA].")
        path = str(tmp_path / "report.csv")
        gen.save_csv(report, path)
        assert os.path.exists(path)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
