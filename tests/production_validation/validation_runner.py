#!/usr/bin/env python3
"""
CiteMatch v2.5.x -- Production Validation Runner

One command to validate the entire CiteMatch lifecycle:
    python validation_runner.py

Pipeline:
    Environment Check -> Golden Regression -> Production Validation
    -> Output Comparison -> Statistics -> MD Report -> JSON Report
"""
import os, sys, json

# Ensure we can import engine modules and validators
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ENGINE_DIR = os.path.join(PROJECT_ROOT, "engine")
TESTS_DIR = os.path.dirname(os.path.abspath(__file__))

for d in [ENGINE_DIR, TESTS_DIR]:
    if d not in sys.path:
        sys.path.insert(0, d)

from validators.citation_validator import CitationValidator, ValidationFinding
from validators.injection_validator import InjectionValidator
from validators.density_validator import DensityValidator
from validators.table_validator import TableValidator
from validators.figure_validator import FigureValidator
from validators.floating_validator import FloatingValidator
from validators.mapping_validator import MappingValidator
from validators.pandoc_validator import PandocValidator
from validators.csl_validator import CslValidator
from validators.summary_validator import SummaryValidator
from statistics import ValidationStatistics
from validation_report import ValidationReport
from compare_outputs import OutputComparator


class ValidationRunner:
    """Orchestrate the full production validation pipeline"""

    def __init__(self, output_dir: str, bib_path: str,
                 manuscript_path: str, golden_dir: str,
                 csl_path: str = None, all_authors: bool = False):
        self._output_dir = output_dir
        self._bib_path = bib_path
        self._manuscript_path = manuscript_path
        self._golden_dir = golden_dir
        self._csl_path = csl_path
        self._all_authors = all_authors
        self._findings: list[ValidationFinding] = []
        self._reports_dir = os.path.join(os.path.dirname(__file__), "reports")

    def run(self) -> dict:
        print("=" * 60)
        print("CiteMatch v2.5.x -- Production Validation Runner")
        print("=" * 60)

        # 1. Environment Check
        print("\n[1/6] Environment Check...")
        self._run_pandoc()

        # 2. Golden Dataset Regression
        print("\n[2/6] Golden Dataset Regression...")
        self._run_golden()

        # 3. Production Validation
        print("\n[3/6] Production Validation...")
        self._run_citation()
        self._run_summary()
        self._run_injection()
        self._run_density()
        self._run_table()
        self._run_figure()
        self._run_floating()
        self._run_mapping()
        self._run_csl()

        # 4. Statistics
        print("\n[4/6] Computing Statistics...")
        stats = self._run_statistics()

        # 5. Output Comparison
        print("\n[5/6] Output Comparison...")
        self._run_comparison()

        # 6. Reports
        print("\n[6/6] Generating Reports...")
        md_path, json_path = self._generate_reports(stats)

        # Summary
        passes = sum(1 for f in self._findings if f.severity == "PASS")
        warnings = sum(1 for f in self._findings if f.severity == "WARNING")
        fails = sum(1 for f in self._findings if f.severity == "FAIL")
        total = len(self._findings)
        score = round(passes / max(total, 1) * 100, 1) if total > 0 else 0

        print("\n" + "=" * 60)
        print(f"VALIDATION COMPLETE")
        print(f"  Score: {score}%")
        print(f"  PASS: {passes}  WARNING: {warnings}  FAIL: {fails}")
        print(f"  Report: {md_path}")
        print(f"  JSON:   {json_path}")
        print("=" * 60)

        return {
            "score": score,
            "pass": passes, "warning": warnings, "fail": fails,
            "report_md": md_path, "report_json": json_path,
            "total_checks": total,
        }

    def _add(self, findings):
        if isinstance(findings, list):
            self._findings.extend(findings)
        else:
            self._findings.append(findings)

    def _status(self, name: str, findings: list):
        fails = sum(1 for f in findings if f.severity == "FAIL")
        warns = sum(1 for f in findings if f.severity == "WARNING")
        passes = sum(1 for f in findings if f.severity == "PASS")
        icon = "FAIL" if fails else "PASS"
        print(f"  {icon} {name}: {passes}P {warns}W {fails}F")

    # ── Validators ──

    def _run_pandoc(self):
        v = PandocValidator(self._output_dir)
        f = v.validate()
        self._add(f)
        self._status("Pandoc", f)

    def _run_citation(self):
        v = CitationValidator(self._bib_path, self._output_dir)
        f = v.validate()
        self._add(f)
        self._status("Citation", f)

    def _run_summary(self):
        v = SummaryValidator(self._output_dir)
        f = v.validate()
        self._add(f)
        self._status("Summary", f)

    def _run_injection(self):
        v = InjectionValidator(self._manuscript_path)
        f = v.validate()
        self._add(f)
        self._status("Injection", f)

    def _run_density(self):
        v = DensityValidator(self._manuscript_path)
        f = v.validate()
        self._add(f)
        self._status("Density", f)

    def _run_table(self):
        v = TableValidator(self._manuscript_path)
        f = v.validate()
        self._add(f)
        self._status("Table", f)

    def _run_figure(self):
        v = FigureValidator(self._manuscript_path)
        f = v.validate()
        self._add(f)
        self._status("Figure", f)

    def _run_floating(self):
        v = FloatingValidator(self._output_dir)
        f = v.validate()
        self._add(f)
        self._status("Floating", f)

    def _run_mapping(self):
        v = MappingValidator(self._output_dir, self._manuscript_path)
        f = v.validate()
        self._add(f)
        self._status("Mapping", f)

    def _run_csl(self):
        if self._csl_path and os.path.exists(self._csl_path):
            v = CslValidator(self._csl_path, self._all_authors)
            f = v.validate()
            self._add(f)
            self._status("CSL", f)
        else:
            print("  ⏭️  CSL: skipped (no CSL file)")

    def _run_statistics(self) -> dict:
        vs = ValidationStatistics(self._output_dir, self._bib_path,
                                  self._manuscript_path)
        stats = vs.compute()
        return stats

    def _run_golden(self):
        """Run golden dataset verification"""
        golden_verify = os.path.join(self._golden_dir, "verify_golden_dataset.py")
        if os.path.exists(golden_verify):
            import subprocess
            try:
                result = subprocess.run(
                    ["python", golden_verify],
                    capture_output=True, text=True, timeout=30,
                    cwd=PROJECT_ROOT)
                if result.returncode == 0:
                    print("  [PASS] Golden Dataset: PASS")
                    self._add(ValidationFinding(
                        phase="GOLDEN", check="Golden Dataset", severity="PASS",
                        detail="Golden dataset verification passed",
                        function="ValidationRunner._run_golden"))
                else:
                    print("  [FAIL] Golden Dataset: FAIL")
                    self._add(ValidationFinding(
                        phase="GOLDEN", check="Golden Dataset", severity="FAIL",
                        detail=f"Golden verification failed: {result.stderr[:200]}",
                        root_cause="Golden dataset integrity check failed",
                        suggestion="Run verify_golden_dataset.py manually to diagnose",
                        function="ValidationRunner._run_golden"))
            except Exception as e:
                print(f"  [WARN]  Golden check error: {e}")
                self._add(ValidationFinding(
                    phase="GOLDEN", check="Golden Dataset", severity="WARNING",
                    detail=f"Could not run golden verification: {e}",
                    function="ValidationRunner._run_golden"))
        else:
            print("  [WARN]  Golden verify script not found")

    def _run_comparison(self):
        comparator = OutputComparator(self._output_dir, self._golden_dir)
        results = comparator.compare_all()
        report_path = os.path.join(self._reports_dir, "comparison_report.md")
        comparator.generate_report(report_path)
        risks = [r for r in results if r.status == "REGRESSION RISK"]
        if risks:
            for r in risks:
                self._add(ValidationFinding(
                    phase="COMPARE", check=f"Regression: {r.target}",
                    severity="FAIL",
                    detail=f"{r.target}: {r.difference_pct}% difference exceeds threshold",
                    root_cause=f"Current output differs from golden {r.target}",
                    suggestion="Verify intended changes; update golden dataset if intentional",
                    function="ValidationRunner._run_comparison"))
            print(f"  [FAIL] Comparison: {len(risks)} regression risks")
        else:
            print(f"  [PASS] Comparison: no regression risks")
            self._add(ValidationFinding(
                phase="COMPARE", check="Output Comparison", severity="PASS",
                detail="All outputs within regression threshold",
                function="ValidationRunner._run_comparison"))

    def _generate_reports(self, stats: dict) -> tuple[str, str]:
        os.makedirs(self._reports_dir, exist_ok=True)
        # Save stats first
        stats_path = os.path.join(self._reports_dir, "validation_statistics.json")
        with open(stats_path, "w", encoding="utf-8") as f:
            json.dump(stats, f, indent=2, ensure_ascii=False)
        # Generate report
        report = ValidationReport(self._findings, stats, self._reports_dir)
        return report.generate_all()


def main():
    import argparse
    p = argparse.ArgumentParser(
        description="CiteMatch Production Validation Runner")
    p.add_argument("--output", default=None,
                   help="Engine output directory (default: ../../output)")
    p.add_argument("--bib", default=None,
                   help="BibTeX file path")
    p.add_argument("--manuscript", default=None,
                   help="Injected manuscript path")
    p.add_argument("--golden", default=None,
                   help="Golden dataset directory")
    p.add_argument("--csl", default=None,
                   help="CSL file path")
    p.add_argument("--all-authors", action="store_true",
                   help="Check CSL et-al removal")
    args = p.parse_args()

    # Defaults
    base = os.path.dirname(os.path.abspath(__file__))
    output_dir = args.output or os.path.join(base, os.pardir, os.pardir, "output")
    bib_path = args.bib or os.path.join(output_dir, "references.bib")
    manuscript_path = args.manuscript or os.path.join(output_dir, "injected.md")
    golden_dir = args.golden or os.path.join(base, os.pardir, "golden_dataset")
    csl_path = args.csl or os.path.join(output_dir, "acs_modified.csl")

    runner = ValidationRunner(
        output_dir=output_dir, bib_path=bib_path,
        manuscript_path=manuscript_path, golden_dir=golden_dir,
        csl_path=csl_path, all_authors=args.all_authors,
    )
    result = runner.run()

    # Exit code
    if result["fail"] > 0:
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
