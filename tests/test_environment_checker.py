"""test_environment_checker.py — v2.4.2"""
import sys, os, pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(PROJECT_ROOT, "installers"))

from environment_checker import EnvironmentChecker
import environment_checker


class TestEnvironmentChecker:
    def test_python_always_available(self):
        ec = EnvironmentChecker()
        result = ec._check_python()
        assert result["available"] is True

    def test_check_all_returns_dict(self):
        ec = EnvironmentChecker()
        results = ec.check_all()
        assert "python" in results
        assert "pandoc" in results

    def test_report_is_string(self):
        ec = EnvironmentChecker()
        report = ec.report()
        assert "CiteMatch Environment Check" in report

    def test_zotero_no_bib(self):
        ec = EnvironmentChecker()
        result = ec._check_zotero_bib(None)
        assert result["available"] is False

    def test_report_with_bib(self, tmp_path):
        bib = tmp_path / "test.bib"
        bib.write_text("@article{test, author={A}, title={T}, journal={J}, year={2024}}")
        ec = EnvironmentChecker()
        result = ec._check_zotero_bib(str(bib))
        assert result["available"] is True
        assert result["entries"] == 1

    def test_explicit_pandoc_and_sibling_crossref_are_preferred(
        self, tmp_path, monkeypatch
    ):
        pandoc = tmp_path / "pandoc.exe"
        crossref = tmp_path / "pandoc-crossref.exe"
        pandoc.write_bytes(b"placeholder")
        crossref.write_bytes(b"placeholder")

        class Completed:
            returncode = 0
            stderr = ""

            def __init__(self, stdout):
                self.stdout = stdout

        def fake_run(command, **_kwargs):
            if command[0] == str(pandoc):
                return Completed("pandoc 3.6.4\n")
            if command[0] == str(crossref):
                return Completed("pandoc-crossref 0.3\n")
            raise AssertionError(command)

        monkeypatch.setattr(environment_checker.subprocess, "run", fake_run)
        result = EnvironmentChecker()._check_pandoc(str(pandoc))
        assert result["available"] is True
        assert result["path"] == str(pandoc)
        assert result["pandoc_crossref"] == {
            "available": True,
            "path": str(crossref),
            "detail": "pandoc-crossref 0.3",
        }

    def test_invalid_explicit_pandoc_fails_closed(self, tmp_path):
        result = EnvironmentChecker()._check_pandoc(str(tmp_path / "missing.exe"))
        assert result["available"] is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
