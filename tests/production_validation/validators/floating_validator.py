"""
Phase 4: Floating Validator

Validates:
- Floating references count
- AI expansion markers present
- Floating pct <= 20% of pending
"""
import os, sys, re

ENGINE_DIR = os.path.join(os.path.dirname(__file__), os.pardir, os.pardir, os.pardir, "engine")
if ENGINE_DIR not in sys.path:
    sys.path.insert(0, ENGINE_DIR)

from validators.citation_validator import ValidationFinding


class FloatingValidator:
    """Validate floating reference handling"""

    MAX_FLOATING_PCT = 20.0

    def __init__(self, output_dir: str):
        self._output_dir = output_dir
        self._findings: list[ValidationFinding] = []

    def validate(self) -> list[ValidationFinding]:
        self._findings = []

        # Check Candidate Table for floating entries
        candidate_path = os.path.join(self._output_dir, "Citation_Candidate_Table.md")
        if not os.path.exists(candidate_path):
            self._findings.append(ValidationFinding(
                phase="4", check="Candidate Table", severity="WARNING",
                detail="Citation_Candidate_Table.md not found",
                suggestion="Run Phase 3 to generate candidate table",
                function="FloatingValidator.validate"))
            return self._findings

        with open(candidate_path, "r", encoding="utf-8") as f:
            table = f.read()

        # Count rejected/floating entries
        floating = len(re.findall(r'ROUTING', table))
        all_rejected = len(re.findall(r'❌', table))
        accepted = len(re.findall(r'✅', table))

        total = accepted + all_rejected
        float_pct = (floating / total * 100) if total > 0 else 0

        if float_pct > self.MAX_FLOATING_PCT:
            self._findings.append(ValidationFinding(
                phase="4", check="Floating Ratio", severity="FAIL",
                detail=f"Floating ratio {float_pct:.0f}% exceeds max {self.MAX_FLOATING_PCT}% ({floating}/{total})",
                root_cause="Too many papers could not be matched to manuscript sentences",
                suggestion="Improve semantic anchors or lower similarity threshold; consider manual placement",
                file=candidate_path, function="FloatingValidator.validate"))
        elif floating > 0:
            self._findings.append(ValidationFinding(
                phase="4", check="Floating Ratio", severity="PASS",
                detail=f"Floating: {floating}/{total} ({float_pct:.0f}%) within acceptable range",
                function="FloatingValidator.validate"))
        else:
            self._findings.append(ValidationFinding(
                phase="4", check="Floating Ratio", severity="PASS",
                detail=f"All {accepted} candidates accepted, no floating references",
                function="FloatingValidator.validate"))

        # Check AI expansion markers in floating report
        floating_report = os.path.join(self._output_dir, "Floating_Reference_Report.md")
        if os.path.exists(floating_report):
            with open(floating_report, "r", encoding="utf-8") as f:
                report = f.read()
            has_markers = 'AI扩写区' in report or '【AI' in report
            if not has_markers and floating > 0:
                self._findings.append(ValidationFinding(
                    phase="4", check="AI Expansion Markers", severity="WARNING",
                    detail="Floating references exist but no AI expansion markers found",
                    root_cause="floating_refs.py did not add expansion markers",
                    suggestion="Ensure floating_refs handler adds 【AI扩写区】 markers",
                    function="FloatingValidator.validate"))
            else:
                self._findings.append(ValidationFinding(
                    phase="4", check="AI Expansion Markers", severity="PASS",
                    detail="AI expansion markers present for floating references",
                    function="FloatingValidator.validate"))

        return self._findings


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(description="Floating Validator (Phase 4)")
    p.add_argument("--output", required=True, help="Path to output directory")
    args = p.parse_args()
    v = FloatingValidator(args.output)
    for f in v.validate():
        print(f"[{f.severity}] Phase {f.phase}: {f.check} — {f.detail}")
