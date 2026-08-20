"""ISSUE-007: numeric CSL bibliographies render visible numbering."""
from pathlib import Path
import os
import re
import shutil
import sys
import zipfile
from xml.etree import ElementTree

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONVERTERS_DIR = PROJECT_ROOT / "converters"
EXPORTERS_DIR = PROJECT_ROOT / "exporters"
for module_dir in (CONVERTERS_DIR, EXPORTERS_DIR):
    sys.path.insert(0, str(module_dir))

from csl_modifier import CSLModifier
from docx_exporter import DocxExporter
from journal_compiler import JournalStyleManager


CSL_NS = "http://purl.org/net/xbiblio/csl"
W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"

NUMERIC_CSL = """<?xml version="1.0" encoding="utf-8"?>
<style xmlns="http://purl.org/net/xbiblio/csl" class="in-text" version="1.0">
  <info>
    <title>Generic Numeric Test</title>
    <id>https://example.invalid/styles/generic-numeric-test</id>
    <category citation-format="numeric"/>
    <updated>2026-08-19T00:00:00+00:00</updated>
  </info>
  <citation collapse="citation-number">
    <layout prefix="[" suffix="]" delimiter=", ">
      <text variable="citation-number"/>
    </layout>
  </citation>
  <bibliography>
    <sort><key variable="citation-number"/></sort>
    <layout><text variable="title"/></layout>
  </bibliography>
</style>"""

AUTHOR_DATE_CSL = NUMERIC_CSL.replace(
    '<category citation-format="numeric"/>',
    '<category citation-format="author-date"/>',
).replace(
    '<text variable="citation-number"/>',
    '<text variable="author"/>',
).replace(
    '<sort><key variable="citation-number"/></sort>',
    '<sort><key variable="author"/></sort>',
)


def _write(path: Path, content: str) -> Path:
    path.write_text(content, encoding="utf-8")
    return path


def _bibliography_number_nodes(path: Path):
    root = ElementTree.parse(path).getroot()
    bibliography = root.find(f"{{{CSL_NS}}}bibliography")
    assert bibliography is not None
    return [
        elem for elem in bibliography.iter(f"{{{CSL_NS}}}text")
        if elem.get("variable") == "citation-number"
    ]


def _require_pandoc_toolchain() -> str:
    tool_dir = os.environ.get("CITEMATCH_PANDOC_TOOL_DIR")
    if tool_dir:
        os.environ["PATH"] = tool_dir + os.pathsep + os.environ.get("PATH", "")
    pandoc = shutil.which("pandoc")
    if not pandoc or not shutil.which("pandoc-crossref"):
        pytest.skip("Pandoc and pandoc-crossref are required for DOCX integration")
    return pandoc


def test_numeric_numbering_is_added_once_and_author_modes_preserve_it(tmp_path):
    source = _write(tmp_path / "numeric.csl", NUMERIC_CSL)
    modifier = CSLModifier(str(source))

    assert modifier.ensure_bibliography_numbering()
    assert not modifier.ensure_bibliography_numbering()
    modifier.set_full_author_display()
    modifier.set_default_author_display()
    output = Path(modifier.save(str(tmp_path / "modified.csl")))

    nodes = _bibliography_number_nodes(output)
    assert len(nodes) == 1
    assert nodes[0].get("suffix") == ". "


def test_author_date_style_is_not_numbered(tmp_path):
    source = _write(tmp_path / "author-date.csl", AUTHOR_DATE_CSL)
    modifier = CSLModifier(str(source))

    assert not modifier.ensure_bibliography_numbering()
    output = Path(modifier.save(str(tmp_path / "modified.csl")))
    assert _bibliography_number_nodes(output) == []


def test_exported_docx_has_visible_continuous_csl_numbers_without_word_numpr(
    tmp_path,
):
    pandoc = _require_pandoc_toolchain()
    markdown = _write(
        tmp_path / "manuscript.md",
        "First [@Beta2025]. Second [@Alpha2025]. Third [@Gamma2025].\n",
    )
    bibliography = _write(
        tmp_path / "references.bib",
        """@article{Alpha2025, author={Alpha, A.}, title={Alpha title}, year={2025}}
@article{Beta2025, author={Beta, B.}, title={Beta title}, year={2025}}
@article{Gamma2025, author={Gamma, G.}, title={Gamma title}, year={2025}}
""",
    )
    csl = _write(tmp_path / "numeric.csl", NUMERIC_CSL)
    output = tmp_path / "Final_Manuscript.docx"

    result = DocxExporter(str(tmp_path)).export_manuscript(
        str(markdown),
        bibliography=str(bibliography),
        csl=str(csl),
        output_path=str(output),
        pandoc_path=pandoc,
    )
    assert result == str(output)

    with zipfile.ZipFile(output) as archive:
        document = ElementTree.fromstring(archive.read("word/document.xml"))
    paragraphs = document.findall(f".//{{{W_NS}}}p")
    bibliography_paragraphs = []
    for paragraph in paragraphs:
        style = paragraph.find(
            f"./{{{W_NS}}}pPr/{{{W_NS}}}pStyle"
        )
        if style is not None and style.get(f"{{{W_NS}}}val") == "Bibliography":
            text = "".join(paragraph.itertext())
            bibliography_paragraphs.append((paragraph, text))

    assert [
        re.match(r"^(\d+)\. ", text).group(1)
        for _, text in bibliography_paragraphs
    ] == ["1", "2", "3"]
    assert [text.split(". ", 1)[1] for _, text in bibliography_paragraphs] == [
        "Beta title", "Alpha title", "Gamma title"
    ]
    assert all(
        paragraph.find(f".//{{{W_NS}}}numPr") is None
        for paragraph, _ in bibliography_paragraphs
    )


def test_journal_style_manager_applies_numbering_in_formal_path(tmp_path):
    source = _write(tmp_path / "numeric.csl", NUMERIC_CSL)
    output = Path(JournalStyleManager().modify_csl(str(source)))
    assert len(_bibliography_number_nodes(output)) == 1
