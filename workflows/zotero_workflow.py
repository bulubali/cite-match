#!/usr/bin/env python3
"""CiteMatch v2.4.2 — Zotero Workflow

Guides user through providing a Zotero-exported .bib file.
Validates file existence, parsing, and reference count.
"""
import os
import re
from typing import Optional


class ZoteroWorkflow:
    """Validate and load Zotero Better BibTeX exports"""

    def __init__(self, bib_path: Optional[str] = None):
        self._bib_path: Optional[str] = None
        self._entry_count: int = 0
        self._valid: bool = False
        self._errors: list[str] = []

        if bib_path:
            self.load(bib_path)

    def load(self, bib_path: str) -> bool:
        """Load and validate a .bib file"""
        self._bib_path = bib_path
        self._errors = []

        if not os.path.exists(bib_path):
            self._errors.append(f"File not found: {bib_path}")
            self._valid = False
            return False

        try:
            with open(bib_path, "r", encoding="utf-8") as f:
                content = f.read()

            entries = re.findall(r"@\w+\{(\w+),", content)
            self._entry_count = len(entries)

            if self._entry_count == 0:
                self._errors.append("No BibTeX entries found in file")
                self._valid = False
                return False

            self._valid = True
            return True

        except Exception as e:
            self._errors.append(f"Error reading file: {e}")
            self._valid = False
            return False

    def report(self) -> str:
        """Generate validation report"""
        if not self._bib_path:
            return "No .bib file provided."

        lines = [
            "Zotero BibTeX Validation",
            "=" * 30,
            f"File: {self._bib_path}",
            f"Status: {'LOADED' if self._valid else 'FAILED'}",
        ]
        if self._valid:
            lines.append(f"References detected: {self._entry_count}")
        for err in self._errors:
            lines.append(f"  ERROR: {err}")
        return "\n".join(lines)

    @property
    def is_valid(self) -> bool:
        return self._valid

    @property
    def entry_count(self) -> int:
        return self._entry_count

    @property
    def bib_path(self) -> Optional[str]:
        return self._bib_path


def main():
    import argparse
    p = argparse.ArgumentParser(description="CiteMatch Zotero Workflow")
    p.add_argument("bib", help="Path to .bib file")
    args = p.parse_args()

    wf = ZoteroWorkflow(args.bib)
    print(wf.report())


if __name__ == "__main__":
    main()
