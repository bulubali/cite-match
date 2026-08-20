"""test_pandoc_adapter.py — v2.4.2"""
import sys, os, pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(PROJECT_ROOT, "converters"))

from pandoc_adapter import PandocAdapter, PandocError
import pandoc_adapter


class TestPandocAdapter:
    def test_is_available(self):
        adapter = PandocAdapter()
        # Pandoc may or may not be installed
        assert isinstance(adapter.is_available, bool)

    def test_get_version_when_available(self):
        adapter = PandocAdapter()
        if adapter.is_available:
            ver = adapter.get_version()
            assert ver is not None
            assert "pandoc" in ver.lower()

    def test_convert_nonexistent_file_raises(self):
        adapter = PandocAdapter()
        if adapter.is_available:
            with pytest.raises(PandocError):
                adapter.convert_docx_to_markdown("/nonexistent/file.docx")

    def test_convert_md_to_docx_nonexistent(self):
        adapter = PandocAdapter()
        if adapter.is_available:
            with pytest.raises(PandocError):
                adapter.convert_markdown_to_docx("/nonexistent/file.md", "/tmp/out.docx")

    def test_version_returns_none_when_unavailable(self):
        adapter = PandocAdapter()
        if not adapter.is_available:
            assert adapter.get_version() is None

    def test_explicit_path_is_used_for_docx_conversion(self, tmp_path, monkeypatch):
        executable = tmp_path / "pandoc.exe"
        executable.write_bytes(b"placeholder")
        source = tmp_path / "source.docx"
        source.write_bytes(b"placeholder")
        observed = {}

        class Completed:
            returncode = 0
            stderr = ""
            stdout = "# Converted\n"

        def fake_run(command, **_kwargs):
            observed["command"] = command
            return Completed()

        monkeypatch.setattr(pandoc_adapter.subprocess, "run", fake_run)
        result = PandocAdapter(str(executable)).convert_docx_to_markdown(
            str(source)
        )
        assert result == "# Converted\n"
        assert observed["command"][0] == str(executable.resolve())

    def test_invalid_explicit_path_does_not_fall_back_to_path(self, tmp_path):
        adapter = PandocAdapter(str(tmp_path / "missing.exe"))
        assert adapter.is_available is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
