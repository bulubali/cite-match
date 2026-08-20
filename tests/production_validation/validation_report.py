"""
Production Validation — Report Generator

Generates:
- Production_Validation_Report.md
- validation_statistics.json

From findings collected by all validators.
"""
import os, sys, json
from datetime import datetime
from collections import Counter

ENGINE_DIR = os.path.join(os.path.dirname(__file__), os.pardir, os.pardir, "engine")
if ENGINE_DIR not in sys.path:
    sys.path.insert(0, ENGINE_DIR)


class ValidationReport:
    """Generate production validation reports"""

    def __init__(self, findings: list, statistics: dict, output_dir: str):
        self._findings = findings
        self._statistics = statistics
        self._output_dir = output_dir

    def generate_all(self) -> tuple[str, str]:
        md_path = self._generate_markdown()
        json_path = self._generate_json()
        return md_path, json_path

    def _summarize(self) -> dict:
        severities = Counter(f.severity for f in self._findings)
        phases = Counter(f.phase for f in self._findings)
        total = len(self._findings)
        score = round(
            (severities.get("PASS", 0) / max(total, 1)) * 100, 1
        ) if total > 0 else 0
        return {
            "total_checks": total,
            "pass_count": severities.get("PASS", 0),
            "warning_count": severities.get("WARNING", 0),
            "fail_count": severities.get("FAIL", 0),
            "overall_score": score,
            "phases_covered": sorted(phases.keys()),
        }

    def _generate_markdown(self) -> str:
        summary = self._summarize()
        lines = []
        lines.append("# CiteMatch v2.5.x — Production Validation Report")
        lines.append("")
        lines.append(f"> Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append(f"> Overall Score: **{summary['overall_score']}%**")
        lines.append("")

        # Summary
        lines.append("## Summary")
        lines.append("")
        lines.append(f"| Metric | Value |")
        lines.append(f"|--------|-------|")
        lines.append(f"| Total Checks | {summary['total_checks']} |")
        lines.append(f"| ✅ PASS | {summary['pass_count']} |")
        lines.append(f"| ⚠️ WARNING | {summary['warning_count']} |")
        lines.append(f"| ❌ FAIL | {summary['fail_count']} |")
        lines.append(f"| Overall Score | **{summary['overall_score']}%** |")
        lines.append("")

        # Statistics
        if self._statistics:
            lines.append("## Statistics")
            lines.append("")
            for key, val in sorted(self._statistics.items()):
                lines.append(f"- **{key}**: {val}")
            lines.append("")

        # FAIL items (must fix)
        fails = [f for f in self._findings if f.severity == "FAIL"]
        if fails:
            lines.append("## ❌ FAIL — Must Fix Before Proceeding")
            lines.append("")
            for f in fails:
                lines.append(f"### Phase {f.phase}: {f.check}")
                lines.append(f"- **Detail**: {f.detail}")
                if f.root_cause:
                    lines.append(f"- **Root Cause**: {f.root_cause}")
                if f.suggestion:
                    lines.append(f"- **Suggestion**: {f.suggestion}")
                if f.file:
                    lines.append(f"- **File**: `{f.file}`")
                if f.function:
                    lines.append(f"- **Function**: `{f.function}`")
                lines.append("")

        # WARNING items (review and triage)
        warnings = [f for f in self._findings if f.severity == "WARNING"]
        if warnings:
            lines.append("## ⚠️ WARNING — Review and Triage")
            lines.append("")
            for w in warnings:
                lines.append(f"### Phase {w.phase}: {w.check}")
                lines.append(f"- **Detail**: {w.detail}")
                if w.root_cause:
                    lines.append(f"- **Root Cause**: {w.root_cause}")
                if w.suggestion:
                    lines.append(f"- **Suggestion**: {w.suggestion}")
                lines.append("")

        # PASS items (summary only)
        passes = [f for f in self._findings if f.severity == "PASS"]
        lines.append("## ✅ PASS — All Checks Passed")
        lines.append("")
        lines.append(f"| # | Phase | Check | Detail |")
        lines.append(f"|---|-------|-------|--------|")
        for i, p in enumerate(passes, 1):
            lines.append(f"| {i} | {p.phase} | {p.check} | {p.detail[:80]} |")
        lines.append("")

        # Phase coverage
        phases = Counter(f.phase for f in self._findings)
        lines.append("## Phase Coverage")
        lines.append("")
        for phase in sorted(phases.keys()):
            total = phases[phase]
            phase_passes = sum(1 for f in self._findings
                             if f.phase == phase and f.severity == "PASS")
            lines.append(f"- Phase {phase}: {phase_passes}/{total} PASS")
        lines.append("")

        report_path = os.path.join(self._output_dir, "Production_Validation_Report.md")
        content = '\n'.join(lines)
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(content)
        return report_path

    def _generate_json(self) -> str:
        summary = self._summarize()
        data = {
            "report_metadata": {
                "generated": datetime.now().isoformat(),
                "overall_score": summary["overall_score"],
                "total_checks": summary["total_checks"],
                "pass": summary["pass_count"],
                "warning": summary["warning_count"],
                "fail": summary["fail_count"],
            },
            "statistics": self._statistics,
            "findings": [f.to_dict() for f in self._findings],
        }
        json_path = os.path.join(self._output_dir, "validation_statistics.json")
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return json_path


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(description="Validation Report Generator")
    p.add_argument("--findings-json", help="Path to findings JSON (optional)")
    p.add_argument("--stats-json", required=True, help="Path to statistics JSON")
    p.add_argument("--output-dir", required=True, help="Reports output directory")
    args = p.parse_args()

    with open(args.stats_json, "r") as f:
        stats = json.load(f)
    report = ValidationReport([], stats, args.output_dir)
    md_path, json_path = report.generate_all()
    print(f"Report: {md_path}")
    print(f"JSON:   {json_path}")
