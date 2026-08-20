"""ISSUE-006: preserve DOCX figures through conversion and export."""
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
WORKFLOWS_DIR = PROJECT_ROOT / "workflows"
for module_dir in (CONVERTERS_DIR, EXPORTERS_DIR, WORKFLOWS_DIR):
    sys.path.insert(0, str(module_dir))

from docx_exporter import DocxExporter
from manuscript_workflow import ManuscriptWorkflow
from pandoc_adapter import PandocAdapter


WP_NS = "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"
W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
IMAGE_RE = re.compile(r"!\[[^\]]*\]\(([^)]+)\)")


def _docx_metrics(path: Path) -> dict[str, int]:
    with zipfile.ZipFile(path) as archive:
        media = [name for name in archive.namelist() if name.startswith("word/media/")]
        document = ElementTree.fromstring(archive.read("word/document.xml"))
    inline = len(document.findall(f".//{{{WP_NS}}}inline"))
    tables = document.findall(f".//{{{W_NS}}}tbl")
    one_by_one = 0
    for table in tables:
        rows = table.findall(f"./{{{W_NS}}}tr")
        cells = table.findall(f"./{{{W_NS}}}tr/{{{W_NS}}}tc")
        if len(rows) == 1 and len(cells) == 1:
            one_by_one += 1
    return {
        "media": len(media),
        "inline": inline,
        "tables": len(tables),
        "one_by_one": one_by_one,
    }


def _image_paths(markdown_path: Path) -> list[Path]:
    text = markdown_path.read_text(encoding="utf-8")
    return [Path(match) for match in IMAGE_RE.findall(text)]


def _require_pandoc_toolchain() -> tuple[str, str]:
    tool_dir = os.environ.get("CITEMATCH_PANDOC_TOOL_DIR")
    if tool_dir:
        os.environ["PATH"] = tool_dir + os.pathsep + os.environ.get("PATH", "")
    pandoc = shutil.which("pandoc")
    crossref = shutil.which("pandoc-crossref")
    if not pandoc or not crossref:
        pytest.skip("Pandoc and pandoc-crossref are required for DOCX integration")
    return pandoc, crossref


def test_docx_conversion_requests_media_extraction_next_to_output(
    tmp_path, monkeypatch
):
    source = tmp_path / "source" / "manuscript.docx"
    source.parent.mkdir()
    source.write_bytes(b"docx fixture")
    output = tmp_path / ".workflow-output" / "draft.md"
    output.parent.mkdir()
    observed = {}

    adapter = PandocAdapter()
    adapter._pandoc_path = "pandoc"

    def fake_run(args, timeout=60):
        observed["args"] = args
        output.write_text("converted", encoding="utf-8")
        return type("Result", (), {"returncode": 0, "stderr": ""})()

    monkeypatch.setattr(adapter, "_run", fake_run)
    assert adapter.convert_docx_to_markdown(str(source), str(output)) == str(output)

    expected = f"--extract-media={output.parent.resolve().as_posix()}"
    assert expected in observed["args"]
    assert observed["args"].index(expected) < observed["args"].index("-o")


def test_real_docx_figures_survive_conversion_and_export_across_directories(
    tmp_path,
):
    pandoc, _ = _require_pandoc_toolchain()
    fixture = PROJECT_ROOT / "tests" / "golden_dataset" / "manuscript_original.docx"
    if not fixture.is_file():
        pytest.skip("Private Golden DOCX fixture is not distributed.")
    source_dir = tmp_path / "source-manuscript"
    output_dir = tmp_path / ".workflow-output"
    source_dir.mkdir()
    output_dir.mkdir()
    source = source_dir / "manuscript.docx"
    shutil.copy2(fixture, source)

    source_metrics = _docx_metrics(source)
    assert source_metrics["inline"] > 0
    markdown = output_dir / "draft.md"
    PandocAdapter().convert_docx_to_markdown(str(source), str(markdown))

    image_paths = _image_paths(markdown)
    assert len(image_paths) == source_metrics["inline"]
    assert all(path.is_absolute() and path.is_file() for path in image_paths)

    final = output_dir / "Final_Manuscript.docx"
    result = DocxExporter(str(output_dir)).export_manuscript(
        str(markdown), output_path=str(final), pandoc_path=pandoc
    )
    assert result == str(final)

    final_metrics = _docx_metrics(final)
    assert final_metrics["inline"] == source_metrics["inline"]
    assert final_metrics["media"] == source_metrics["inline"]
    assert final_metrics["tables"] == source_metrics["tables"]
    assert final_metrics["one_by_one"] == source_metrics["one_by_one"]


def test_workflow_restart_keeps_extracted_media_resolvable(tmp_path):
    _require_pandoc_toolchain()
    source_fixture = (
        PROJECT_ROOT / "tests" / "golden_dataset" / "manuscript_original.docx"
    )
    if not source_fixture.is_file():
        pytest.skip("Private Golden DOCX fixture is not distributed.")
    source_dir = tmp_path / "source-manuscript"
    output_dir = tmp_path / ".workflow-output"
    source_dir.mkdir()
    output_dir.mkdir()
    source = source_dir / "manuscript.docx"
    bib = source_dir / "references.bib"
    shutil.copy2(source_fixture, source)
    bib.write_text(
        """@article{FigureStudy2025,
  author = {Figure, A.},
  title = {Flexible wearable blood pressure monitoring systems},
  abstract = {Flexible wearable blood pressure monitoring systems.},
  year = {2025},
  journal = {Journal A},
  file = {D:/papers/figure-study.pdf}
}
""",
        encoding="utf-8",
    )

    markdown = output_dir / "draft.md"
    PandocAdapter().convert_docx_to_markdown(str(source), str(markdown))
    initial_images = _image_paths(markdown)
    assert initial_images
    assert all(path.is_file() for path in initial_images)

    workflow_markdown = output_dir / "stateful-draft.md"
    workflow_markdown.write_text(
        "# Introduction\n\n"
        f"![Figure]({initial_images[0]})\n\n"
        "Flexible wearable blood pressure monitoring systems.\n",
        encoding="utf-8",
    )

    started = ManuscriptWorkflow(
        str(workflow_markdown), str(bib), str(output_dir)
    ).run(mode="A", dry_run=False)
    assert started["gate"] == "IF_CONFIRM"

    resumed = ManuscriptWorkflow(
        str(workflow_markdown), str(bib), str(output_dir)
    ).confirm(
        "IF_CONFIRM", body_if="disable", table_if="disable", dry_run=False
    )
    assert resumed["gate"] == "SUMMARY_CONFIRM"
    assert _image_paths(workflow_markdown) == [initial_images[0]]
    assert initial_images[0].is_file()
