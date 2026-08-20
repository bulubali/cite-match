"""test_zotero_workflow.py — v2.4.2"""
import sys, os, pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(PROJECT_ROOT, "workflows"))

from zotero_workflow import ZoteroWorkflow


class TestZoteroWorkflow:
    def test_nonexistent_file(self):
        wf = ZoteroWorkflow("/nonexistent/test.bib")
        assert wf.is_valid is False

    def test_valid_bib(self, tmp_path):
        bib = tmp_path / "test.bib"
        bib.write_text("@article{key1, author={A}, title={T}, journal={J}, year={2024}}")
        wf = ZoteroWorkflow(str(bib))
        assert wf.is_valid is True
        assert wf.entry_count == 1

    def test_multiple_entries(self, tmp_path):
        bib = tmp_path / "multi.bib"
        bib.write_text("@article{a,...}\n@article{b,...}\n@article{c,...}")
        wf = ZoteroWorkflow(str(bib))
        assert wf.is_valid is True
        assert wf.entry_count == 3

    def test_empty_bib(self, tmp_path):
        bib = tmp_path / "empty.bib"
        bib.write_text("")
        wf = ZoteroWorkflow(str(bib))
        assert wf.is_valid is False

    def test_report_contains_count(self, tmp_path):
        bib = tmp_path / "test.bib"
        bib.write_text("@article{key1, author={A}, title={T}, journal={J}, year={2024}}")
        wf = ZoteroWorkflow(str(bib))
        report = wf.report()
        assert "1" in report

    def test_no_bib_provided(self):
        wf = ZoteroWorkflow()
        assert "No .bib file" in wf.report()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
