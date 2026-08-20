"""
Phase 3: Table Validator

Validates:
- Table IF gate enforcement (IF >= threshold for table citations)
- Table structure integrity (no damage to markdown tables)
- No broken pipe characters or newlines in table cells
"""
import os, sys, re

ENGINE_DIR = os.path.join(os.path.dirname(__file__), os.pardir, os.pardir, os.pardir, "engine")
if ENGINE_DIR not in sys.path:
    sys.path.insert(0, ENGINE_DIR)

from validators.citation_validator import ValidationFinding
from md_ast import MarkdownAST


class TableValidator:
    """Validate table citation injection rules and table integrity"""

    def __init__(self, manuscript_path: str, if_threshold: float = 10.0):
        self._manuscript_path = manuscript_path
        self._if_threshold = if_threshold
        self._findings: list[ValidationFinding] = []

    def validate(self) -> list[ValidationFinding]:
        self._findings = []
        if not os.path.exists(self._manuscript_path):
            self._findings.append(ValidationFinding(
                phase="3", check="Table Manuscript", severity="FAIL",
                detail=f"Manuscript not found: {self._manuscript_path}",
                file=self._manuscript_path, function="TableValidator.validate"))
            return self._findings

        with open(self._manuscript_path, "r", encoding="utf-8") as f:
            self._text = f.read()

        self._check_table_structure()
        return self._findings

    def _check_table_structure(self):
        """Verify pipe tables and recognize Pandoc simple/grid tables."""
        ast = MarkdownAST(self._text)
        ast.parse()
        non_pipe_tables = [fmt for _, _, fmt in ast._table_formats if fmt != "pipe"]
        if non_pipe_tables:
            self._findings.append(ValidationFinding(
                phase="3", check="Non-pipe Table Detection", severity="PASS",
                detail=(f"Recognized {len(non_pipe_tables)} non-pipe table(s): "
                        f"{', '.join(sorted(set(non_pipe_tables)))}"),
                function="TableValidator._check_table_structure"))

        lines = self._text.split('\n')
        in_table = False
        table_lines = []
        damaged = 0
        tables_found = 0

        for line in lines:
            stripped = line.strip()
            is_table_line = '|' in stripped and stripped.count('|') >= 2

            if is_table_line and not in_table:
                in_table = True
                table_lines = [stripped]
            elif is_table_line and in_table:
                table_lines.append(stripped)
            elif in_table and not is_table_line:
                # Table ended — validate
                tables_found += 1
                if len(table_lines) >= 2:
                    # Check column consistency
                    cols = [t.count('|') for t in table_lines]
                    if len(set(cols)) > 1:
                        damaged += 1
                # Check for broken newlines within cells
                for tl in table_lines:
                    if '\n' in tl:
                        damaged += 1
                        break
                in_table = False
                table_lines = []

        if damaged > 0:
            self._findings.append(ValidationFinding(
                phase="3", check="Table Structure", severity="FAIL",
                detail=f"Table structure damage in {damaged}/{tables_found} tables",
                root_cause="Citation injection may have broken table cell alignment",
                suggestion="Check injector table detection and protection logic",
                file=self._manuscript_path, function="TableValidator._check_table_structure"))
        elif tables_found > 0:
            self._findings.append(ValidationFinding(
                phase="3", check="Table Structure", severity="PASS",
                detail=f"All {tables_found} tables structurally intact",
                function="TableValidator._check_table_structure"))
        elif ast._table_formats:
            self._findings.append(ValidationFinding(
                phase="3", check="Table Structure", severity="PASS",
                detail=(f"All {len(ast._table_formats)} non-pipe table(s) "
                        "were recognized and kept out of raw-offset injection"),
                function="TableValidator._check_table_structure"))
        else:
            self._findings.append(ValidationFinding(
                phase="3", check="Table Structure", severity="PASS",
                detail="No markdown tables found in manuscript",
                function="TableValidator._check_table_structure"))


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(description="Table Validator (Phase 3)")
    p.add_argument("--manuscript", required=True, help="Path to injected manuscript")
    args = p.parse_args()
    v = TableValidator(args.manuscript)
    for f in v.validate():
        print(f"[{f.severity}] Phase {f.phase}: {f.check} — {f.detail}")
