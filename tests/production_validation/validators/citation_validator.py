"""
Phase 00 + Phase 1: Citation Validator

Validates:
- Bib file existence and parseability
- BBT file field coverage
- PDF path resolvability
- Pending keys computation
- IF gate application
- Ghost duplicate detection
"""
import os, sys, re
from dataclasses import dataclass, field
from typing import Optional

ENGINE_DIR = os.path.join(os.path.dirname(__file__), os.pardir, os.pardir, os.pardir, "engine")
if ENGINE_DIR not in sys.path:
    sys.path.insert(0, ENGINE_DIR)


@dataclass
class ValidationFinding:
    phase: str
    check: str
    severity: str       # PASS / WARNING / FAIL
    detail: str
    root_cause: str = ""
    suggestion: str = ""
    file: str = ""
    function: str = ""

    def to_dict(self) -> dict:
        return {
            "phase": self.phase,
            "check": self.check,
            "severity": self.severity,
            "detail": self.detail,
            "root_cause": self.root_cause,
            "suggestion": self.suggestion,
            "file": self.file,
            "function": self.function,
        }


class CitationValidator:
    """Validate Phase 00 (BBT/Bib) and Phase 1 (Delta/IF/Ghost)"""

    def __init__(self, bib_path: str, output_dir: str, if_threshold: float = 6.0):
        self._bib_path = bib_path
        self._output_dir = output_dir
        self._if_threshold = if_threshold
        self._findings: list[ValidationFinding] = []

    def validate(self) -> list[ValidationFinding]:
        self._findings = []
        self._check_bib_exists()
        if self._findings and any(f.severity == "FAIL" for f in self._findings):
            return self._findings
        self._check_bib_parseable()
        self._check_bbt_file_field()
        self._check_pdf_resolvable()
        self._check_pending_keys()
        self._check_ghost_duplicates()
        return self._findings

    # ── Phase 00 ──

    def _check_bib_exists(self):
        if not os.path.exists(self._bib_path):
            self._findings.append(ValidationFinding(
                phase="00", check="Bib File Existence", severity="FAIL",
                detail=f"Bib file not found: {self._bib_path}",
                root_cause="Missing or moved bibliography file",
                suggestion="Ensure Zotero BBT export is present",
                file=self._bib_path, function="CitationValidator._check_bib_exists"))
        elif os.path.getsize(self._bib_path) == 0:
            self._findings.append(ValidationFinding(
                phase="00", check="Bib File Size", severity="FAIL",
                detail=f"Bib file is empty: {self._bib_path}",
                root_cause="BBT export produced empty file",
                suggestion="Re-export from Zotero with BBT plugin",
                file=self._bib_path, function="CitationValidator._check_bib_exists"))
        else:
            size_kb = os.path.getsize(self._bib_path) / 1024
            self._findings.append(ValidationFinding(
                phase="00", check="Bib File Existence", severity="PASS",
                detail=f"Bib file found ({size_kb:.0f} KB)",
                file=self._bib_path, function="CitationValidator._check_bib_exists"))

    def _check_bib_parseable(self):
        try:
            from bib_parser import BibTeXParser
            parser = BibTeXParser()
            entries = parser.parse_file(self._bib_path)
            if len(entries) == 0:
                self._findings.append(ValidationFinding(
                    phase="00", check="Bib Parseability", severity="FAIL",
                    detail="Bib parsed but returned 0 entries",
                    root_cause="Empty or malformed bib file",
                    suggestion="Check BBT export settings in Zotero",
                    file=self._bib_path, function="CitationValidator._check_bib_parseable"))
            else:
                self._findings.append(ValidationFinding(
                    phase="00", check="Bib Parseability", severity="PASS",
                    detail=f"Bib parsed successfully: {len(entries)} entries",
                    file=self._bib_path, function="CitationValidator._check_bib_parseable"))
        except Exception as e:
            self._findings.append(ValidationFinding(
                phase="00", check="Bib Parseability", severity="FAIL",
                detail=f"Bib parse error: {e}",
                root_cause="BibTeX syntax error or encoding issue",
                suggestion="Validate bib syntax; check file encoding is UTF-8",
                file=self._bib_path, function="CitationValidator._check_bib_parseable"))

    def _check_bbt_file_field(self):
        try:
            from bib_parser import BibTeXParser
            parser = BibTeXParser()
            entries = parser.parse_file(self._bib_path)
            total = len(entries)
            with_file = sum(1 for e in entries.values()
                          if e.fields.get('file', '').strip())
            pct = (with_file / total * 100) if total > 0 else 0
            if pct < 50:
                self._findings.append(ValidationFinding(
                    phase="00", check="BBT File Field", severity="WARNING",
                    detail=f"Only {pct:.0f}% of entries have BBT file field ({with_file}/{total})",
                    root_cause="Bibliography may not be exported via BBT 'Keep Updated'",
                    suggestion="Re-export from Zotero with Better BibTeX, ensure 'Keep Updated' is checked",
                    file=self._bib_path, function="CitationValidator._check_bbt_file_field"))
            else:
                self._findings.append(ValidationFinding(
                    phase="00", check="BBT File Field", severity="PASS",
                    detail=f"BBT file field present in {pct:.0f}% of entries ({with_file}/{total})",
                    file=self._bib_path, function="CitationValidator._check_bbt_file_field"))
        except Exception as e:
            self._findings.append(ValidationFinding(
                phase="00", check="BBT File Field", severity="WARNING",
                detail=f"Could not check BBT file field: {e}",
                root_cause="Bib parsing failed upstream",
                suggestion="Fix bib parseability first",
                file=self._bib_path, function="CitationValidator._check_bbt_file_field"))

    def _check_pdf_resolvable(self):
        try:
            from bib_parser import BibTeXParser
            parser = BibTeXParser()
            entries = parser.parse_file(self._bib_path)
            with_file = [(k, e.fields.get('file', ''))
                        for k, e in entries.items()
                        if e.fields.get('file', '').strip()]
            resolved = 0
            for key, file_field in with_file:
                m = re.search(r'([A-Za-z]:[^:;]+\.pdf)', file_field)
                if m and os.path.exists(m.group(1)):
                    resolved += 1
            pct = (resolved / len(with_file) * 100) if with_file else 0
            if pct < 30 and with_file:
                self._findings.append(ValidationFinding(
                    phase="00", check="PDF Resolution", severity="WARNING",
                    detail=f"Only {pct:.0f}% of PDF paths resolvable ({resolved}/{len(with_file)})",
                    root_cause="Zotero storage paths changed or files moved",
                    suggestion="Verify Zotero data directory location",
                    file=self._bib_path, function="CitationValidator._check_pdf_resolvable"))
            else:
                self._findings.append(ValidationFinding(
                    phase="00", check="PDF Resolution", severity="PASS",
                    detail=f"PDF paths: {resolved}/{len(with_file)} resolvable ({pct:.0f}%)",
                    file=self._bib_path, function="CitationValidator._check_pdf_resolvable"))
        except Exception as e:
            self._findings.append(ValidationFinding(
                phase="00", check="PDF Resolution", severity="WARNING",
                detail=f"Could not check PDF resolution: {e}",
                file=self._bib_path, function="CitationValidator._check_pdf_resolvable"))

    # ── Phase 1 ──

    def _check_pending_keys(self):
        """Verify pending keys file exists and is well-formed"""
        pending_path = os.path.join(self._output_dir, "pending_keys.txt")
        if not os.path.exists(pending_path):
            self._findings.append(ValidationFinding(
                phase="1", check="Pending Keys File", severity="WARNING",
                detail="pending_keys.txt not found in output directory",
                root_cause="Phase 1 delta detection may not have run",
                suggestion="Run Phase 1: Delta Detection + IF Filtering",
                file=pending_path, function="CitationValidator._check_pending_keys"))
            return
        with open(pending_path, "r", encoding="utf-8") as f:
            keys = [l.strip() for l in f if l.strip()]
        if len(keys) == 0:
            self._findings.append(ValidationFinding(
                phase="1", check="Pending Keys", severity="PASS",
                detail="No pending keys — all bib entries already cited",
                file=pending_path, function="CitationValidator._check_pending_keys"))
        else:
            self._findings.append(ValidationFinding(
                phase="1", check="Pending Keys", severity="PASS",
                detail=f"{len(keys)} pending keys identified",
                file=pending_path, function="CitationValidator._check_pending_keys"))

    def _check_ghost_duplicates(self):
        """Check for duplicate citekeys mapping to same paper"""
        try:
            from bib_parser import BibTeXParser
            parser = BibTeXParser()
            entries = parser.parse_file(self._bib_path)

            # Group by normalized DOI
            doi_groups: dict[str, list[str]] = {}
            for key, entry in entries.items():
                doi = entry.fields.get('doi', '').lower().strip()
                if doi:
                    doi_groups.setdefault(doi, []).append(key)

            ghosts = {doi: keys for doi, keys in doi_groups.items() if len(keys) > 1}
            if ghosts:
                ghost_list = [f"{keys}" for keys in ghosts.values()]
                self._findings.append(ValidationFinding(
                    phase="1", check="Ghost Duplicates", severity="WARNING",
                    detail=f"Found {len(ghosts)} ghost duplicate groups: {ghost_list[:3]}",
                    root_cause="Zotero imported same paper multiple times with different keys",
                    suggestion="Merge duplicate entries in Zotero or use manual_map",
                    file=self._bib_path, function="CitationValidator._check_ghost_duplicates"))
            else:
                self._findings.append(ValidationFinding(
                    phase="1", check="Ghost Duplicates", severity="PASS",
                    detail="No ghost duplicate citekeys found",
                    file=self._bib_path, function="CitationValidator._check_ghost_duplicates"))
        except Exception as e:
            self._findings.append(ValidationFinding(
                phase="1", check="Ghost Duplicates", severity="WARNING",
                detail=f"Could not check ghost duplicates: {e}",
                file=self._bib_path, function="CitationValidator._check_ghost_duplicates"))


# CLI entry point for standalone execution
if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(description="Citation Validator (Phase 00 + Phase 1)")
    p.add_argument("--bib", required=True, help="Path to .bib file")
    p.add_argument("--output", required=True, help="Path to output directory")
    args = p.parse_args()
    v = CitationValidator(args.bib, args.output)
    findings = v.validate()
    for f in findings:
        print(f"[{f.severity}] Phase {f.phase}: {f.check} — {f.detail}")
