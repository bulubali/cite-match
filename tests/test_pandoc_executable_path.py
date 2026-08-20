import os
import sys

import pytest


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(PROJECT_ROOT, "exporters"))
sys.path.insert(0, os.path.join(PROJECT_ROOT, "converters"))

from docx_exporter import DocxExporter
from journal_compiler import PandocCommandBuilder


def _builder(pandoc_path=None):
    return (
        PandocCommandBuilder(pandoc_path=pandoc_path)
        .set_input("draft.md")
        .set_output("Final_Manuscript.docx")
        .set_bibliography("references.bib")
        .set_csl("journal.csl")
    )


def test_default_none_keeps_existing_pandoc_command():
    command = _builder().build()

    assert command[0] == "pandoc"


def test_explicit_executable_path_is_used(tmp_path):
    executable = tmp_path / "pandoc.exe"
    executable.write_bytes(b"")

    command = _builder(str(executable)).build()

    assert command[0] == os.path.abspath(str(executable))


def test_invalid_executable_path_fails_closed(tmp_path):
    missing = tmp_path / "missing-pandoc.exe"

    with pytest.raises(ValueError, match="Pandoc executable not found"):
        PandocCommandBuilder(pandoc_path=str(missing))


def test_docx_exporter_passes_explicit_path(tmp_path, monkeypatch):
    executable = tmp_path / "pandoc.exe"
    executable.write_bytes(b"")
    manuscript = tmp_path / "injected.md"
    manuscript.write_text("Claim [@Paper2025].\n", encoding="utf-8")
    observed = {}

    def execute(builder):
        observed["command"] = builder.build()
        return True, "compiled"

    monkeypatch.setattr(PandocCommandBuilder, "execute", execute)
    exporter = DocxExporter(str(tmp_path / "output"))

    result = exporter.export_manuscript(
        str(manuscript),
        output_path=str(tmp_path / "Final_Manuscript.docx"),
        pandoc_path=str(executable),
    )

    assert result == str(tmp_path / "Final_Manuscript.docx")
    assert observed["command"][0] == os.path.abspath(str(executable))
    assert exporter.last_command == observed["command"]


def test_explicit_path_does_not_change_parameter_order(tmp_path):
    executable = tmp_path / "pandoc.exe"
    executable.write_bytes(b"")

    command = _builder(str(executable)).build()

    assert command[:4] == [
        os.path.abspath(str(executable)),
        "draft.md",
        "-o",
        "Final_Manuscript.docx",
    ]
    assert command.index("--filter") < command.index("--citeproc")
    assert command.index("--citeproc") < command.index("--bibliography")
    assert command.index("--bibliography") < command.index("--csl")
    assert command.index("--csl") < command.index("-M")
