#!/usr/bin/env python3
"""CiteMatch v2.4.2 — Environment Checker

Detects required tools. Does NOT auto-install.
Provides clear instructions when tools are missing.
"""
import sys
import os
import shutil
import subprocess
from typing import Optional


class EnvironmentChecker:
    """Detect and report on required tool availability"""

    def __init__(self):
        self._results: dict[str, dict] = {}

    def check_all(
        self,
        bib_path: Optional[str] = None,
        pandoc_path: Optional[str] = None,
    ) -> dict:
        """Run all checks. Returns results dict."""
        self._results = {
            "python": self._check_python(),
            "pandoc": self._check_pandoc(pandoc_path),
            "zotero_bib": self._check_zotero_bib(bib_path),
        }
        return self._results

    def report(self, bib_path: Optional[str] = None) -> str:
        """Generate human-readable report"""
        results = self.check_all(bib_path)
        lines = [
            "CiteMatch Environment Check",
            "=" * 30,
            "",
        ]
        for name, result in results.items():
            status = "OK" if result["available"] else "NOT FOUND"
            marker = "+" if result["available"] else "X"
            lines.append(f"  [{marker}] {name}: {status}")
            if result.get("detail"):
                lines.append(f"      {result['detail']}")

        # Suggestions
        missing = [k for k, v in results.items() if not v["available"]]
        if missing:
            lines.append("")
            lines.append("Suggested actions:")
            for name in missing:
                suggestion = results[name].get("suggestion", "")
                if suggestion:
                    lines.append(f"  - {suggestion}")

        return "\n".join(lines)

    @staticmethod
    def _check_python() -> dict:
        version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
        return {
            "available": True,
            "version": version,
            "detail": f"Python {version}",
        }

    @staticmethod
    def _check_pandoc(explicit_path: Optional[str] = None) -> dict:
        if explicit_path:
            path = os.path.abspath(explicit_path)
            if not os.path.isfile(path):
                return {
                    "available": False,
                    "path": path,
                    "suggestion": "Provide an existing Pandoc executable path.",
                }
            try:
                result = subprocess.run(
                    [path, "--version"], capture_output=True, text=True,
                    timeout=10,
                )
                if result.returncode != 0:
                    raise RuntimeError(result.stderr.strip() or "--version failed")
                version_line = (
                    result.stdout.split("\n")[0] if result.stdout else "unknown"
                )
                if "pandoc" not in version_line.lower():
                    raise RuntimeError("--version did not identify Pandoc")
                checked = {
                    "available": True,
                    "path": path,
                    "version": version_line,
                    "detail": version_line,
                    "explicit": True,
                }
                checked["pandoc_crossref"] = EnvironmentChecker._check_crossref(
                    os.path.dirname(path)
                )
                return checked
            except Exception as exc:
                return {
                    "available": False,
                    "path": path,
                    "explicit": True,
                    "detail": f"Unable to execute Pandoc: {exc}",
                    "suggestion": "Provide an executable Pandoc path.",
                }

        path = shutil.which("pandoc")
        if path:
            try:
                result = subprocess.run(
                    ["pandoc", "--version"], capture_output=True, text=True, timeout=10
                )
                version_line = result.stdout.split("\n")[0] if result.stdout else "unknown"
                return {
                    "available": True,
                    "path": path,
                    "version": version_line,
                    "detail": version_line,
                }
            except Exception:
                pass
        return {
            "available": False,
            "suggestion": "Install Pandoc from https://pandoc.org/installing.html",
        }

    @staticmethod
    def _check_crossref(pandoc_directory: str) -> dict:
        """Prefer the explicit Pandoc tool directory, then preserve PATH lookup."""
        sibling = os.path.join(pandoc_directory, "pandoc-crossref.exe")
        path = sibling if os.path.isfile(sibling) else shutil.which("pandoc-crossref")
        if not path:
            return {"available": False}
        try:
            result = subprocess.run(
                [path, "--version"], capture_output=True, text=True, timeout=10
            )
            if result.returncode != 0:
                return {"available": False, "path": path}
            version_line = result.stdout.split("\n")[0] if result.stdout else "unknown"
            if "pandoc-crossref" not in version_line.lower():
                return {"available": False, "path": path}
            return {
                "available": True,
                "path": path,
                "detail": version_line,
            }
        except Exception:
            return {"available": False, "path": path}

    @staticmethod
    def _check_zotero_bib(bib_path: Optional[str] = None) -> dict:
        if bib_path and os.path.exists(bib_path):
            try:
                with open(bib_path, "r", encoding="utf-8") as f:
                    content = f.read()
                import re
                entries = len(re.findall(r"@\w+\{", content))
                return {
                    "available": True,
                    "path": bib_path,
                    "entries": entries,
                    "detail": f"{entries} references detected in {os.path.basename(bib_path)}",
                }
            except Exception:
                pass
        return {
            "available": False,
            "detail": "No .bib file provided",
            "suggestion": (
                "Export your Zotero collection as Better BibTeX .bib file.\n"
                "  In Zotero: right-click collection → Export Collection → "
                "Format: Better BibTeX → check 'Keep updated'"
            ),
        }


def main():
    import argparse
    p = argparse.ArgumentParser(description="CiteMatch Environment Checker")
    p.add_argument("--bib", help="Path to .bib file")
    args = p.parse_args()

    checker = EnvironmentChecker()
    print(checker.report(args.bib))


if __name__ == "__main__":
    main()
