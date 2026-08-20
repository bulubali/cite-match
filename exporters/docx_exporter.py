#!/usr/bin/env python3
"""CiteMatch v2.4.2 — DOCX Exporter

Converts final processed manuscript back to Word format.
Collects all reports into output/ directory.
"""
import os
import sys
import shutil
from typing import Optional

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class DocxExporter:
    """Export processed manuscript and reports to output/"""

    def __init__(self, output_dir: Optional[str] = None):
        self._output_dir = output_dir or os.path.join(PROJECT_ROOT, "output")
        self._last_command: list[str] = []
        os.makedirs(self._output_dir, exist_ok=True)

    def export_manuscript(
        self,
        markdown_path: str,
        bibliography: Optional[str] = None,
        csl: Optional[str] = None,
        journal: Optional[str] = None,
        all_authors: bool = False,
        output_path: Optional[str] = None,
        pandoc_path: Optional[str] = None,
    ) -> Optional[str]:
        """Compile DOCX through the existing journal/Pandoc interfaces."""
        try:
            if not os.path.exists(markdown_path):
                return None
            sys.path.insert(0, os.path.join(PROJECT_ROOT, "converters"))
            from journal_compiler import (
                JournalResolver, JournalStyleManager, PandocCommandBuilder,
            )

            resolved_csl = csl
            style_manager = JournalStyleManager()
            if journal and not resolved_csl:
                journal_config = JournalResolver.resolve(journal)
                resolved_csl = style_manager.get_or_download_csl(
                    journal_config.csl_name
                )
                if not resolved_csl:
                    raise RuntimeError(
                        f"CSL unavailable for journal: {journal_config.name}"
                    )
            if resolved_csl:
                resolved_csl = style_manager.modify_csl(
                    resolved_csl,
                    author_style="full" if all_authors else "default",
                )
            elif all_authors:
                raise ValueError("all_authors requires a CSL or journal")

            final_path = output_path or os.path.join(
                self._output_dir, "Final_Manuscript.docx"
            )
            os.makedirs(os.path.dirname(os.path.abspath(final_path)), exist_ok=True)
            builder = PandocCommandBuilder(pandoc_path=pandoc_path)
            builder.set_input(markdown_path).set_output(final_path)
            if bibliography:
                builder.set_bibliography(bibliography)
            if resolved_csl:
                builder.set_csl(resolved_csl)
            self._last_command = builder.build()
            success, detail = builder.execute()
            if not success:
                raise RuntimeError(detail or "Pandoc compilation failed")
            return final_path
        except Exception as e:
            print(f"DOCX export failed: {e}")
            return None

    def collect_reports(self, report_paths: dict[str, str]) -> list[str]:
        """Copy report files to output/ directory

        Args:
            report_paths: {name: path} dict of reports to collect
        Returns:
            list of copied paths
        """
        copied = []
        for name, path in report_paths.items():
            if os.path.exists(path):
                dest = os.path.join(self._output_dir, os.path.basename(path))
                shutil.copy2(path, dest)
                copied.append(dest)
        return copied

    def generate_export_summary(
        self, manuscript_path: Optional[str],
        reports: dict[str, str],
    ) -> str:
        """Generate export summary report"""
        lines = [
            "# CiteMatch Export Summary",
            "",
            "## Output Files",
            "",
        ]
        if manuscript_path and os.path.exists(manuscript_path):
            lines.append(f"- Final_Manuscript.docx")
        for name in reports:
            lines.append(f"- {os.path.basename(reports[name])}")

        lines.extend([
            "",
            "## Export Directory",
            f"`{self._output_dir}`",
        ])
        return "\n".join(lines)

    @property
    def output_dir(self) -> str:
        return self._output_dir

    @property
    def last_command(self) -> list[str]:
        return list(self._last_command)


def main():
    import argparse
    p = argparse.ArgumentParser(description="CiteMatch DOCX Exporter")
    p.add_argument("manuscript", nargs="?", help="Path to .md manuscript")
    p.add_argument("--bib", help="Path to .bib file")
    p.add_argument("--output", help="Output directory")
    args = p.parse_args()

    exporter = DocxExporter(args.output)
    if args.manuscript:
        result = exporter.export_manuscript(args.manuscript, args.bib)
        if result:
            print(f"Exported: {result}")
        else:
            print("Export failed — Pandoc may not be installed.")


if __name__ == "__main__":
    main()
