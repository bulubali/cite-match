import os
import sys


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(PROJECT_ROOT, "exporters"))
sys.path.insert(0, os.path.join(PROJECT_ROOT, "converters"))

from docx_exporter import DocxExporter
from journal_compiler import JournalStyleManager, PandocCommandBuilder


def test_docx_export_forwards_journal_csl_authors_and_pandoc_flags(
    tmp_path, monkeypatch
):
    manuscript = tmp_path / "injected.md"
    manuscript.write_text("Claim [@Paper2025].\n", encoding="utf-8")
    bib = tmp_path / "references.bib"
    bib.write_text("@article{Paper2025, title={Paper}}", encoding="utf-8")
    csl = tmp_path / "nature.csl"
    csl.write_text("<style/>", encoding="utf-8")
    observed = {}

    monkeypatch.setattr(
        JournalStyleManager, "get_or_download_csl",
        lambda self, name: observed.setdefault("journal", name) and str(csl),
    )

    def modify(self, path, author_style="default"):
        observed["author_style"] = author_style
        observed["csl"] = path
        return path

    monkeypatch.setattr(JournalStyleManager, "modify_csl", modify)
    monkeypatch.setattr(
        PandocCommandBuilder, "execute", lambda self: (True, "compiled")
    )

    final_path = tmp_path / "custom-final.docx"
    exporter = DocxExporter(str(tmp_path / "output"))
    result = exporter.export_manuscript(
        str(manuscript),
        bibliography=str(bib),
        journal="nature",
        all_authors=True,
        output_path=str(final_path),
    )

    assert result == str(final_path)
    assert observed == {
        "journal": "nature", "author_style": "full", "csl": str(csl)
    }
    command = exporter.last_command
    assert command[0] == "pandoc"
    assert command.index("--filter") < command.index("--citeproc")
    assert command[command.index("--filter") + 1] == "pandoc-crossref"
    assert command[command.index("--bibliography") + 1] == str(bib)
    assert command[command.index("--csl") + 1] == str(csl)
    assert command[command.index("-M") + 1] == "link-citations=true"
    assert command[command.index("-o") + 1] == str(final_path)
