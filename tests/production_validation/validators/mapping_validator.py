"""
Phase 7: Mapping Validator

Validates:
- CiteMatch_Mapping_Report.md existence and structure
- CiteMatch_Mapping_Report.csv existence and UTF-8 BOM
- SequenceMatcher similarity scores present
- No missing citekeys in mapping
"""
import os, sys, re, csv

ENGINE_DIR = os.path.join(os.path.dirname(__file__), os.pardir, os.pardir, os.pardir, "engine")
if ENGINE_DIR not in sys.path:
    sys.path.insert(0, ENGINE_DIR)

from validators.citation_validator import ValidationFinding


class MappingValidator:
    """Validate Phase 7 mapping report outputs"""

    def __init__(self, output_dir: str, manuscript_path: str):
        self._output_dir = output_dir
        self._manuscript_path = manuscript_path
        self._findings: list[ValidationFinding] = []

    def validate(self) -> list[ValidationFinding]:
        self._findings = []
        self._check_mapping_md()
        self._check_mapping_csv()
        self._check_missing_citekeys()
        return self._findings

    def _check_mapping_md(self):
        mapping_md = os.path.join(self._output_dir, "CiteMatch_Mapping_Report.md")
        if not os.path.exists(mapping_md):
            self._findings.append(ValidationFinding(
                phase="7", check="Mapping Report MD", severity="WARNING",
                detail="CiteMatch_Mapping_Report.md not found",
                suggestion="Run Phase 7 to generate mapping report",
                function="MappingValidator._check_mapping_md"))
            return

        with open(mapping_md, "r", encoding="utf-8") as f:
            content = f.read()

        # Check similarity scores present
        sim_scores = re.findall(r'similarity[=:]?\s*([\d.]+)', content, re.IGNORECASE)
        if sim_scores:
            self._findings.append(ValidationFinding(
                phase="7", check="Similarity Scores", severity="PASS",
                detail=f"Similarity scores found in mapping report ({len(sim_scores)} entries)",
                function="MappingValidator._check_mapping_md"))
        else:
            self._findings.append(ValidationFinding(
                phase="7", check="Similarity Scores", severity="WARNING",
                detail="No similarity scores found in mapping report",
                root_cause="SequenceMatcher scores not computed",
                suggestion="Verify mapping_report.py generates similarity scores",
                function="MappingValidator._check_mapping_md"))

    def _check_mapping_csv(self):
        csv_path = os.path.join(self._output_dir, "CiteMatch_Mapping_Report.csv")
        if not os.path.exists(csv_path):
            self._findings.append(ValidationFinding(
                phase="7", check="Mapping Report CSV", severity="WARNING",
                detail="CiteMatch_Mapping_Report.csv not found",
                suggestion="Run Phase 7 to generate CSV mapping report",
                function="MappingValidator._check_mapping_csv"))
            return

        # Check UTF-8 BOM
        with open(csv_path, "r", encoding="utf-8") as f:
            first_char = f.read(1)
        if first_char == chr(0xFEFF):
            self._findings.append(ValidationFinding(
                phase="7", check="CSV UTF-8 BOM", severity="PASS",
                detail="CSV has UTF-8 BOM",
                function="MappingValidator._check_mapping_csv"))
        else:
            self._findings.append(ValidationFinding(
                phase="7", check="CSV UTF-8 BOM", severity="FAIL",
                detail="CSV missing UTF-8 BOM",
                root_cause="mapping_report.py did not write BOM",
                suggestion="Open CSV with utf-8-sig encoding when writing",
                file=csv_path, function="MappingValidator._check_mapping_csv"))

        # Check CSV structure
        try:
            with open(csv_path, "r", encoding="utf-8-sig") as f:
                reader = csv.reader(f)
                rows = list(reader)
            if len(rows) < 2:
                self._findings.append(ValidationFinding(
                    phase="7", check="CSV Content", severity="WARNING",
                    detail=f"CSV has only {len(rows)} rows",
                    suggestion="Verify mapping report generation",
                    file=csv_path, function="MappingValidator._check_mapping_csv"))
            else:
                self._findings.append(ValidationFinding(
                    phase="7", check="CSV Content", severity="PASS",
                    detail=f"CSV has {len(rows)} rows with headers: {rows[0]}",
                    function="MappingValidator._check_mapping_csv"))
        except Exception as e:
            self._findings.append(ValidationFinding(
                phase="7", check="CSV Parse", severity="FAIL",
                detail=f"CSV parse error: {e}",
                file=csv_path, function="MappingValidator._check_mapping_csv"))

    def _check_missing_citekeys(self):
        """Verify all citekeys in manuscript exist in mapping"""
        if not os.path.exists(self._manuscript_path):
            return
        with open(self._manuscript_path, "r", encoding="utf-8") as f:
            text = f.read()
        cited = set(re.findall(r'@([A-Za-z0-9_-]+)', text))

        csv_path = os.path.join(self._output_dir, "CiteMatch_Mapping_Report.csv")
        mapped = set()
        if os.path.exists(csv_path):
            with open(csv_path, "r", encoding="utf-8-sig") as f:
                for row in csv.reader(f):
                    if row:
                        for cell in row:
                            for key in re.findall(r'@([A-Za-z0-9_-]+)', cell):
                                mapped.add(key)

        missing = cited - mapped
        if missing and mapped:
            self._findings.append(ValidationFinding(
                phase="7", check="Missing Citekeys", severity="FAIL",
                detail=f"{len(missing)} cited keys not in mapping: {sorted(list(missing))[:5]}",
                root_cause="Injection completed but mapping report not updated",
                suggestion="Re-run Phase 7 mapping report after injection",
                file=csv_path, function="MappingValidator._check_missing_citekeys"))
        elif mapped:
            self._findings.append(ValidationFinding(
                phase="7", check="Missing Citekeys", severity="PASS",
                detail=f"All {len(cited)} cited keys present in mapping",
                function="MappingValidator._check_missing_citekeys"))


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(description="Mapping Validator (Phase 7)")
    p.add_argument("--output", required=True, help="Path to output directory")
    p.add_argument("--manuscript", required=True, help="Path to injected manuscript")
    args = p.parse_args()
    v = MappingValidator(args.output, args.manuscript)
    for f in v.validate():
        print(f"[{f.severity}] Phase {f.phase}: {f.check} — {f.detail}")
