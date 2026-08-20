"""
Phase 0 + Phase 6: Pandoc Validator

Validates:
- Pandoc installation and version
- pandoc-crossref availability
- DOCX compilation success
- Output file size sanity
"""
import os, sys, re, subprocess

ENGINE_DIR = os.path.join(os.path.dirname(__file__), os.pardir, os.pardir, os.pardir, "engine")
if ENGINE_DIR not in sys.path:
    sys.path.insert(0, ENGINE_DIR)

from validators.citation_validator import ValidationFinding


class PandocValidator:
    """Validate pandoc toolchain and DOCX output"""

    MIN_VERSION = (3, 0)
    MIN_DOCX_SIZE_KB = 100

    def __init__(self, output_dir: str):
        self._output_dir = output_dir
        self._findings: list[ValidationFinding] = []

    def validate(self) -> list[ValidationFinding]:
        self._findings = []
        self._check_pandoc_version()
        self._check_pandoc_crossref()
        self._check_docx_output()
        return self._findings

    def _check_pandoc_version(self):
        try:
            result = subprocess.run(["pandoc", "--version"], capture_output=True, text=True, timeout=10)
            if result.returncode != 0:
                self._findings.append(ValidationFinding(
                    phase="0", check="Pandoc Available", severity="FAIL",
                    detail="Pandoc returned non-zero exit code",
                    root_cause="Pandoc installation is broken",
                    suggestion="Reinstall pandoc: winget install --id JohnMacFarlane.Pandoc -e",
                    function="PandocValidator._check_pandoc_version"))
                return
            m = re.search(r'pandoc(?:\.exe)?\s+(\d+)\.(\d+)', result.stdout)
            if m:
                major, minor = int(m.group(1)), int(m.group(2))
                if (major, minor) >= self.MIN_VERSION:
                    self._findings.append(ValidationFinding(
                        phase="0", check="Pandoc Version", severity="PASS",
                        detail=f"Pandoc {major}.{minor} >= {self.MIN_VERSION[0]}.{self.MIN_VERSION[1]}",
                        function="PandocValidator._check_pandoc_version"))
                else:
                    self._findings.append(ValidationFinding(
                        phase="0", check="Pandoc Version", severity="FAIL",
                        detail=f"Pandoc {major}.{minor} < required {self.MIN_VERSION[0]}.{self.MIN_VERSION[1]}",
                        root_cause="Outdated pandoc installation",
                        suggestion="Upgrade pandoc to latest version",
                        function="PandocValidator._check_pandoc_version"))
            else:
                self._findings.append(ValidationFinding(
                    phase="0", check="Pandoc Version", severity="WARNING",
                    detail="Could not determine pandoc version",
                    function="PandocValidator._check_pandoc_version"))
        except FileNotFoundError:
            self._findings.append(ValidationFinding(
                phase="0", check="Pandoc Available", severity="FAIL",
                detail="Pandoc not found in PATH",
                root_cause="Pandoc not installed",
                suggestion="Install pandoc: winget install --id JohnMacFarlane.Pandoc -e",
                function="PandocValidator._check_pandoc_version"))
        except Exception as e:
            self._findings.append(ValidationFinding(
                phase="0", check="Pandoc Available", severity="FAIL",
                detail=f"Pandoc check failed: {e}",
                function="PandocValidator._check_pandoc_version"))

    def _check_pandoc_crossref(self):
        try:
            result = subprocess.run(["pandoc-crossref", "--version"], capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                self._findings.append(ValidationFinding(
                    phase="0", check="pandoc-crossref", severity="PASS",
                    detail="pandoc-crossref available",
                    function="PandocValidator._check_pandoc_crossref"))
            else:
                self._findings.append(ValidationFinding(
                    phase="0", check="pandoc-crossref", severity="WARNING",
                    detail="pandoc-crossref returned non-zero",
                    suggestion="Reinstall pandoc-crossref",
                    function="PandocValidator._check_pandoc_crossref"))
        except FileNotFoundError:
            self._findings.append(ValidationFinding(
                phase="0", check="pandoc-crossref", severity="WARNING",
                detail="pandoc-crossref not found (optional for figures/tables)",
                suggestion="Install from https://github.com/lierdakil/pandoc-crossref/releases",
                function="PandocValidator._check_pandoc_crossref"))

    def _check_docx_output(self):
        docx_path = os.path.join(self._output_dir, "Final_Manuscript.docx")
        if not os.path.exists(docx_path):
            self._findings.append(ValidationFinding(
                phase="6", check="DOCX Output", severity="FAIL",
                detail="Final_Manuscript.docx not found",
                root_cause="Pandoc compilation did not produce output",
                suggestion="Check pandoc command and bibliography path",
                file=docx_path, function="PandocValidator._check_docx_output"))
            return

        size_kb = os.path.getsize(docx_path) / 1024
        if size_kb < self.MIN_DOCX_SIZE_KB:
            self._findings.append(ValidationFinding(
                phase="6", check="DOCX Size", severity="WARNING",
                detail=f"DOCX size {size_kb:.0f} KB < expected {self.MIN_DOCX_SIZE_KB} KB",
                root_cause="Pandoc output may be incomplete or missing content",
                suggestion="Check pandoc compilation warnings; verify --citeproc and --bibliography flags",
                file=docx_path, function="PandocValidator._check_docx_output"))
        else:
            self._findings.append(ValidationFinding(
                phase="6", check="DOCX Output", severity="PASS",
                detail=f"Final_Manuscript.docx generated ({size_kb:.0f} KB)",
                file=docx_path, function="PandocValidator._check_docx_output"))


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(description="Pandoc Validator (Phase 0 + Phase 6)")
    p.add_argument("--output", required=True, help="Path to output directory")
    args = p.parse_args()
    v = PandocValidator(args.output)
    for f in v.validate():
        print(f"[{f.severity}] Phase {f.phase}: {f.check} — {f.detail}")
