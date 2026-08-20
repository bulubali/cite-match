"""
Production Validation — Output Comparison Tool

Compares current engine output vs Golden Dataset expected output.

Comparison targets:
- Summary (References_Summary.md)
- Mapping CSV (CiteMatch_Mapping_Report.csv)
- DOCX (file existence + size)
- Statistics (validation_statistics.json)

If difference > 5%, marks as Regression Risk.
"""
import os, sys, re, json, csv
from dataclasses import dataclass


@dataclass
class ComparisonResult:
    target: str
    current_value: str
    expected_value: str
    difference_pct: float
    status: str    # MATCH / DIFFER / MISSING / REGRESSION RISK


class OutputComparator:
    """Compare current output with Golden Dataset expected output"""

    REGRESSION_THRESHOLD = 5.0  # percentage

    def __init__(self, output_dir: str, golden_dir: str):
        self._output_dir = output_dir
        self._golden_dir = golden_dir
        self._results: list[ComparisonResult] = []

    def compare_all(self) -> list[ComparisonResult]:
        self._results = []
        self._compare_summary()
        self._compare_csv()
        self._compare_docx()
        self._compare_statistics()
        return self._results

    def _compare_summary(self):
        current = os.path.join(self._output_dir, "References_Summary.md")
        expected = os.path.join(self._golden_dir, "expected_summary.md")

        if not os.path.exists(current):
            self._results.append(ComparisonResult(
                "Summary", "MISSING", "exists", 100, "MISSING"))
            return
        if not os.path.exists(expected):
            self._results.append(ComparisonResult(
                "Summary", "exists", "MISSING", 100, "DIFFER"))
            return

        with open(current, "r", encoding="utf-8") as f:
            cur = f.read()
        with open(expected, "r", encoding="utf-8") as f:
            exp = f.read()

        # Compare paper counts
        cur_papers = len(re.findall(r'\| @\w+ \|', cur))
        exp_papers = len(re.findall(r'\| @\w+ \|', exp))
        if exp_papers > 0:
            diff = abs(cur_papers - exp_papers) / exp_papers * 100
        else:
            diff = 100 if cur_papers > 0 else 0

        status = "MATCH" if diff < 1 else (
            "REGRESSION RISK" if diff > self.REGRESSION_THRESHOLD else "DIFFER")
        self._results.append(ComparisonResult(
            "Summary", f"{cur_papers} papers", f"{exp_papers} papers",
            round(diff, 1), status))

    def _compare_csv(self):
        current = os.path.join(self._output_dir, "CiteMatch_Mapping_Report.csv")
        expected = os.path.join(self._golden_dir, "expected_mapping.csv")

        if not os.path.exists(current):
            self._results.append(ComparisonResult(
                "Mapping CSV", "MISSING", "exists", 100, "MISSING"))
            return
        if not os.path.exists(expected):
            self._results.append(ComparisonResult(
                "Mapping CSV", "exists", "MISSING", 100, "DIFFER"))
            return

        try:
            with open(current, "r", encoding="utf-8-sig") as f:
                cur_rows = list(csv.reader(f))
            with open(expected, "r", encoding="utf-8-sig") as f:
                exp_rows = list(csv.reader(f))
        except Exception:
            self._results.append(ComparisonResult(
                "Mapping CSV", "PARSE ERROR", "valid", 100, "MISSING"))
            return

        cur_count = len(cur_rows)
        exp_count = len(exp_rows)
        if exp_count > 0:
            diff = abs(cur_count - exp_count) / exp_count * 100
        else:
            diff = 100 if cur_count > 0 else 0

        status = "MATCH" if diff < 1 else (
            "REGRESSION RISK" if diff > self.REGRESSION_THRESHOLD else "DIFFER")
        self._results.append(ComparisonResult(
            "Mapping CSV", f"{cur_count} rows", f"{exp_count} rows",
            round(diff, 1), status))

    def _compare_docx(self):
        current = os.path.join(self._output_dir, "Final_Manuscript.docx")
        expected = os.path.join(self._golden_dir, "acceptance_output",
                               "Final_Manuscript.docx")

        cur_exists = os.path.exists(current)
        exp_exists = os.path.exists(expected)

        if not cur_exists:
            self._results.append(ComparisonResult(
                "DOCX", "MISSING", "exists" if exp_exists else "N/A",
                100, "MISSING"))
            return

        cur_size = os.path.getsize(current)
        if exp_exists:
            exp_size = os.path.getsize(expected)
            diff = abs(cur_size - exp_size) / exp_size * 100 if exp_size > 0 else 0
        else:
            exp_size = 0
            diff = 0

        status = "MATCH" if diff < 10 else (
            "REGRESSION RISK" if diff > 30 else "DIFFER")
        self._results.append(ComparisonResult(
            "DOCX", f"{cur_size/1024:.0f} KB",
            f"{exp_size/1024:.0f} KB" if exp_exists else "N/A",
            round(diff, 1), status))

    def _compare_statistics(self):
        current = os.path.join(self._output_dir, "validation_statistics.json")
        expected = os.path.join(self._golden_dir, "expected_statistics.json")

        if not os.path.exists(current):
            self._results.append(ComparisonResult(
                "Statistics", "MISSING", "exists", 100, "MISSING"))
            return
        if not os.path.exists(expected):
            self._results.append(ComparisonResult(
                "Statistics", "exists", "MISSING", 0, "DIFFER"))
            return

        with open(current, "r", encoding="utf-8") as f:
            cur = json.load(f)
        with open(expected, "r", encoding="utf-8") as f:
            exp = json.load(f)

        # Compare key numeric fields
        cur_stats = cur.get("statistics", cur)
        exp_stats = exp if isinstance(exp, dict) else {}
        mismatches = 0
        total = 0
        for key in ["original_references", "used_references"]:
            total += 1
            if cur_stats.get(key) != exp_stats.get(key):
                mismatches += 1

        diff = (mismatches / total * 100) if total > 0 else 0
        status = "MATCH" if diff < 5 else "REGRESSION RISK"
        self._results.append(ComparisonResult(
            "Statistics", f"{mismatches} mismatches",
            f"{total} fields compared", round(diff, 1), status))

    def generate_report(self, output_path: str) -> str:
        lines = []
        lines.append("# Output Comparison Report")
        lines.append("")
        lines.append(f"> Regression threshold: {self.REGRESSION_THRESHOLD}%")
        lines.append("")
        lines.append("| Target | Current | Expected | Diff % | Status |")
        lines.append("|--------|---------|----------|--------|--------|")
        for r in self._results:
            lines.append(
                f"| {r.target} | {r.current_value} | {r.expected_value} | "
                f"{r.difference_pct}% | {r.status} |")
        lines.append("")

        regressions = [r for r in self._results if r.status == "REGRESSION RISK"]
        if regressions:
            lines.append("## ⚠️ Regression Risks")
            lines.append("")
            for r in regressions:
                lines.append(f"- **{r.target}**: {r.difference_pct}% difference (threshold {self.REGRESSION_THRESHOLD}%)")
            lines.append("")

        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        content = '\n'.join(lines)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(content)
        return output_path


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(description="Output Comparison Tool")
    p.add_argument("--output", required=True, help="Current output directory")
    p.add_argument("--golden", required=True, help="Golden dataset directory")
    p.add_argument("--report", help="Comparison report output path")
    args = p.parse_args()

    comparator = OutputComparator(args.output, args.golden)
    results = comparator.compare_all()
    for r in results:
        print(f"[{r.status}] {r.target}: {r.current_value} vs {r.expected_value} ({r.difference_pct}%)")

    if args.report:
        path = comparator.generate_report(args.report)
        print(f"\nReport: {path}")
