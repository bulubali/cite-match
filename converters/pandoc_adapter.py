#!/usr/bin/env python3
"""CiteMatch v2.4.2 — Pandoc Adapter

Unified interface for Pandoc document conversion.
Wraps pandoc CLI commands. No logic duplication.
"""
import os
import subprocess
import shutil
from typing import Optional


class PandocError(Exception):
    """Pandoc conversion error"""
    pass


class PandocAdapter:
    """Wrap Pandoc CLI for document conversion"""

    def __init__(self, pandoc_path: Optional[str] = None):
        self._pandoc_path = (
            os.path.abspath(pandoc_path)
            if pandoc_path and os.path.isfile(pandoc_path)
            else None if pandoc_path else shutil.which("pandoc")
        )

    @property
    def is_available(self) -> bool:
        return self._pandoc_path is not None

    def _run(self, args: list[str], timeout: int = 60) -> subprocess.CompletedProcess:
        """Run pandoc with error handling"""
        if not self.is_available:
            raise PandocError(
                "Pandoc not found. Install from https://pandoc.org/installing.html"
            )
        try:
            return subprocess.run(
                [self._pandoc_path] + args,
                capture_output=True, text=True, timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            raise PandocError("Pandoc conversion timed out")
        except Exception as e:
            raise PandocError(f"Pandoc error: {e}")

    def convert_docx_to_markdown(
        self, input_path: str, output_path: Optional[str] = None
    ) -> str:
        """Convert .docx to Markdown

        Args:
            input_path: Path to .docx file
            output_path: Optional output .md path. If None, returns text.

        Returns:
            Markdown text if no output_path, else output_path.
        """
        if not os.path.exists(input_path):
            raise PandocError(f"Input file not found: {input_path}")

        args = [input_path, "-f", "docx", "-t", "markdown", "--wrap=none"]

        if output_path:
            media_root = os.path.dirname(os.path.abspath(output_path)).replace(
                os.sep, "/"
            )
            args.append(f"--extract-media={media_root}")
            args.extend(["-o", output_path])
            result = self._run(args)
            if result.returncode != 0:
                raise PandocError(f"DOCX→MD conversion failed: {result.stderr}")
            return output_path
        else:
            args.extend(["-t", "markdown"])
            result = self._run(args)
            if result.returncode != 0:
                raise PandocError(f"DOCX→MD conversion failed: {result.stderr}")
            return result.stdout

    def convert_markdown_to_docx(
        self, input_path: str, output_path: str,
        bibliography: Optional[str] = None,
        csl: Optional[str] = None,
    ) -> str:
        """Convert Markdown to .docx with optional citation processing

        Args:
            input_path: Path to .md file
            output_path: Output .docx path
            bibliography: Optional .bib file for --citeproc
            csl: Optional CSL style file

        Returns:
            output_path on success
        """
        if not os.path.exists(input_path):
            raise PandocError(f"Input file not found: {input_path}")

        args = [input_path, "-f", "markdown", "-t", "docx", "-o", output_path]

        if bibliography:
            args.extend(["--bibliography", bibliography, "--citeproc"])
        if csl:
            args.extend(["--csl", csl])

        result = self._run(args)
        if result.returncode != 0:
            raise PandocError(f"MD→DOCX conversion failed: {result.stderr}")
        return output_path

    def get_version(self) -> Optional[str]:
        """Get Pandoc version string"""
        if not self.is_available:
            return None
        try:
            result = self._run(["--version"])
            return result.stdout.split("\n")[0] if result.stdout else None
        except PandocError:
            return None


def main():
    import argparse
    p = argparse.ArgumentParser(description="CiteMatch Pandoc Adapter")
    p.add_argument("action", choices=["to-md", "to-docx", "version"])
    p.add_argument("input", nargs="?", help="Input file path")
    p.add_argument("--output", "-o", help="Output file path")
    p.add_argument("--bib", help="Bibliography file for --citeproc")
    args = p.parse_args()

    adapter = PandocAdapter()

    if args.action == "version":
        ver = adapter.get_version()
        print(ver or "Pandoc not found")
    elif args.action == "to-md":
        result = adapter.convert_docx_to_markdown(args.input, args.output)
        if not args.output:
            print(result[:500])
    elif args.action == "to-docx":
        adapter.convert_markdown_to_docx(args.input, args.output, args.bib)
        print(f"Written: {args.output}")


if __name__ == "__main__":
    main()
