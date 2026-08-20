"""test_docx_exporter.py — v2.4.2"""
import sys, os, pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(PROJECT_ROOT, "exporters"))

from docx_exporter import DocxExporter


class TestDocxExporter:
    def test_creates_output_dir(self, tmp_path):
        out = str(tmp_path / "output")
        exporter = DocxExporter(out)
        assert os.path.isdir(exporter.output_dir)

    def test_collect_reports(self, tmp_path):
        out = str(tmp_path / "output")
        exporter = DocxExporter(out)

        r1 = tmp_path / "report1.md"
        r1.write_text("# Report 1")
        r2 = tmp_path / "report2.md"
        r2.write_text("# Report 2")

        copied = exporter.collect_reports({
            "summary": str(r1),
            "audit": str(r2),
        })
        assert len(copied) == 2

    def test_generate_export_summary(self, tmp_path):
        out = str(tmp_path / "output")
        exporter = DocxExporter(out)
        summary = exporter.generate_export_summary(None, {"test": str(tmp_path / "test.md")})
        assert "CiteMatch Export Summary" in summary
        assert "test.md" in summary

    def test_export_nonexistent_manuscript(self, tmp_path):
        out = str(tmp_path / "output")
        exporter = DocxExporter(out)
        result = exporter.export_manuscript("/nonexistent/ms.md")
        # Should fail gracefully, not crash
        assert result is None or isinstance(result, str)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
