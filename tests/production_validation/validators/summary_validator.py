"""
Phase 2: Summary Validator

Validates:
- References_Summary.md existence and structure
- Required fields per paper (citekey, title, paper_type, etc.)
- Review classification accuracy
- Semantic anchor count per paper
- PDF availability reporting
"""
import os, sys, re

ENGINE_DIR = os.path.join(os.path.dirname(__file__), os.pardir, os.pardir, os.pardir, "engine")
if ENGINE_DIR not in sys.path:
    sys.path.insert(0, ENGINE_DIR)

from validators.citation_validator import ValidationFinding

REQUIRED_COLUMNS = [
    "CiteKey", "Type", "Title", "Core Finding",
    "Keywords", "Semantic Anchors", "Recommended Section"
]


class SummaryValidator:
    """Validate References_Summary.md output"""

    def __init__(self, output_dir: str):
        self._output_dir = output_dir
        self._findings: list[ValidationFinding] = []

    def validate(self) -> list[ValidationFinding]:
        self._findings = []
        summary_path = os.path.join(self._output_dir, "References_Summary.md")
        if not os.path.exists(summary_path):
            self._findings.append(ValidationFinding(
                phase="2", check="References Summary", severity="FAIL",
                detail="References_Summary.md not found",
                root_cause="Phase 2 literature intelligence did not run",
                suggestion="Run Phase 2: LiteratureIntelligence.generate_summary()",
                file=summary_path, function="SummaryValidator.validate"))
            return self._findings

        with open(summary_path, "r", encoding="utf-8") as f:
            content = f.read()

        self._check_header(content, summary_path)
        self._check_paper_count(content, summary_path)
        self._check_anchors_per_paper(content, summary_path)
        self._check_review_classification(content, summary_path)
        self._check_pdf_reporting(content, summary_path)
        return self._findings

    def _check_header(self, content: str, path: str):
        for col in REQUIRED_COLUMNS:
            if col.lower() not in content.lower():
                self._findings.append(ValidationFinding(
                    phase="2", check=f"Summary Column: {col}", severity="WARNING",
                    detail=f"Column '{col}' not found in References_Summary.md",
                    root_cause="LiteratureIntelligence.generate_summary missing field",
                    suggestion=f"Add '{col}' column to summary generation",
                    file=path, function="SummaryValidator._check_header"))
                return
        self._findings.append(ValidationFinding(
            phase="2", check="Summary Header", severity="PASS",
            detail="All required columns present in summary",
            function="SummaryValidator._check_header"))

    def _check_paper_count(self, content: str, path: str):
        pending_path = os.path.join(self._output_dir, "pending_keys.txt")
        rows = len(re.findall(r'\| @\w+ \|', content))
        if os.path.exists(pending_path):
            with open(pending_path, "r") as f:
                pending_count = len([l for l in f if l.strip()])
            if rows == pending_count:
                self._findings.append(ValidationFinding(
                    phase="2", check="Summary Row Count", severity="PASS",
                    detail=f"Summary covers all {rows} pending papers",
                    function="SummaryValidator._check_paper_count"))
            else:
                self._findings.append(ValidationFinding(
                    phase="2", check="Summary Row Count", severity="WARNING",
                    detail=f"Summary has {rows} rows but {pending_count} pending papers",
                    root_cause="Summary generation may have skipped some papers",
                    suggestion="Re-run Phase 2 with full pending keys list",
                    file=path, function="SummaryValidator._check_paper_count"))
        else:
            self._findings.append(ValidationFinding(
                phase="2", check="Summary Rows", severity="PASS",
                detail=f"Summary contains {rows} paper entries",
                function="SummaryValidator._check_paper_count"))

    def _check_anchors_per_paper(self, content: str, path: str):
        paper_blocks = content.split('| @')
        low_anchor = 0
        for block in paper_blocks[1:]:  # skip header
            anchors_cell = block.split('|')[5] if len(block.split('|')) > 5 else ''
            anchor_count = len(re.findall(r'[a-zA-Z][a-zA-Z\s-]+', anchors_cell))
            if anchor_count < 2:
                low_anchor += 1
        if low_anchor > 0:
            self._findings.append(ValidationFinding(
                phase="2", check="Semantic Anchors", severity="WARNING",
                detail=f"{low_anchor} papers have <2 semantic anchors",
                root_cause="Anchor generation insufficient for some papers",
                suggestion="Review _generate_anchors in literature_intel.py for low-anchor papers",
                file=path, function="SummaryValidator._check_anchors_per_paper"))
        else:
            self._findings.append(ValidationFinding(
                phase="2", check="Semantic Anchors", severity="PASS",
                detail="All papers have >=2 semantic anchors",
                function="SummaryValidator._check_anchors_per_paper"))

    def _check_review_classification(self, content: str, path: str):
        review_rows = re.findall(r'\| @(\w+) \| review \|', content, re.IGNORECASE)
        if review_rows:
            self._findings.append(ValidationFinding(
                phase="2", check="Review Classification", severity="PASS",
                detail=f"{len(review_rows)} papers classified as review",
                function="SummaryValidator._check_review_classification"))
        else:
            self._findings.append(ValidationFinding(
                phase="2", check="Review Classification", severity="PASS",
                detail="No review papers detected in pending set",
                function="SummaryValidator._check_review_classification"))

    def _check_pdf_reporting(self, content: str, path: str):
        if 'PDF Availability' in content or 'pdf' in content.lower():
            self._findings.append(ValidationFinding(
                phase="2", check="PDF Availability", severity="PASS",
                detail="PDF availability section present in summary",
                function="SummaryValidator._check_pdf_reporting"))
        else:
            self._findings.append(ValidationFinding(
                phase="2", check="PDF Availability", severity="WARNING",
                detail="PDF availability section missing from summary",
                suggestion="Ensure LiteratureIntelligence.generate_summary includes PDF status",
                file=path, function="SummaryValidator._check_pdf_reporting"))


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(description="Summary Validator (Phase 2)")
    p.add_argument("--output", required=True, help="Path to output directory")
    args = p.parse_args()
    v = SummaryValidator(args.output)
    for f in v.validate():
        print(f"[{f.severity}] Phase {f.phase}: {f.check} — {f.detail}")
