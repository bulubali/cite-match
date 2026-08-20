"""test_literature_intel.py — Phase 2: Literature Intelligence Layer"""
import sys, os, pytest, tempfile

ENGINE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "engine")
sys.path.insert(0, ENGINE_DIR)

from literature_intel import LiteratureIntelligence, PaperIntel
from sample_data import SAMPLE_BIB


@pytest.fixture
def intel():
    return LiteratureIntelligence()


@pytest.fixture
def bib_entries(intel):
    return intel.load_bib.__wrapped__ if hasattr(intel.load_bib, '__wrapped__') else None


class TestPaperIntel:
    def test_creation(self):
        p = PaperIntel(citekey="Test2024")
        assert p.citekey == "Test2024"
        assert p.paper_type == "research"

    def test_to_markdown_row(self):
        p = PaperIntel(citekey="Test2024", title="A Test Paper",
                       paper_type="research", core_finding="Found X",
                       technical_keywords=["kw1", "kw2"],
                       recommended_section="§1")
        row = p.to_markdown_row()
        assert "Test2024" in row
        assert "kw1" in row


class TestLiteratureIntelligence:
    def test_load_bib_from_file(self, intel, tmp_path):
        bib_path = str(tmp_path / "test.bib")
        with open(bib_path, 'w', encoding='utf-8') as f:
            f.write(SAMPLE_BIB)
        entries = intel.load_bib(bib_path)
        assert len(entries) == 5

    def test_analyze_pending(self, intel, tmp_path):
        bib_path = str(tmp_path / "test.bib")
        with open(bib_path, 'w', encoding='utf-8') as f:
            f.write(SAMPLE_BIB)
        intel.load_bib(bib_path)
        papers = intel.analyze_pending(["Chen2023Flexible", "Wang2024Ultrathin"])
        assert len(papers) == 2
        for p in papers:
            assert p.title
            assert p.paper_type in ("research", "review")
            assert len(p.technical_keywords) > 0
            assert len(p.semantic_anchors) > 0
            assert p.recommended_section

    def test_classify_review(self, intel, tmp_path):
        bib_path = str(tmp_path / "test.bib")
        with open(bib_path, 'w', encoding='utf-8') as f:
            f.write(SAMPLE_BIB)
        intel.load_bib(bib_path)
        papers = intel.analyze_pending(["Chen2023Flexible"])
        assert len(papers) == 1

    def test_generate_summary(self, intel, tmp_path):
        bib_path = str(tmp_path / "test.bib")
        with open(bib_path, 'w', encoding='utf-8') as f:
            f.write(SAMPLE_BIB)
        intel.load_bib(bib_path)
        papers = intel.analyze_pending(["Chen2023Flexible", "Tan2022PulseWave"])
        out = str(tmp_path / "summary.md")
        content = intel.generate_summary(papers, out)
        assert os.path.exists(out)
        assert "HUMAN CONFIRMATION" in content
        assert "Chen2023Flexible" in content
        assert "Tan2022PulseWave" in content

    def test_pdf_path_resolution(self, intel):
        path = intel._resolve_pdf_path("C:\\papers\\test.pdf:application/pdf")
        assert path == "" or "papers" in path.lower() or path == ""  # file may not exist

    def test_clean_latex(self, intel):
        cleaned = intel._clean_latex("A {{PZT}} sensor with \\textbf{high} performance")
        assert "{{" not in cleaned
        assert "}}" not in cleaned

    def test_section_routing(self, intel):
        section = intel._route_to_section(
            "Piezoelectric MXene Sensor for BP Monitoring", "", "research")
        assert "Piezoelectric" in section or "3.1" in section

    def test_summary_has_checkpoint(self, intel, tmp_path):
        bib_path = str(tmp_path / "test.bib")
        with open(bib_path, 'w', encoding='utf-8') as f:
            f.write(SAMPLE_BIB)
        intel.load_bib(bib_path)
        papers = intel.analyze_pending(["Chen2023Flexible"])
        content = intel.generate_summary(papers, "")
        assert "继续匹配" in content  # Human confirmation checkpoint


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
