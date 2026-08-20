"""
Phase 3: Density Validator

Validates:
- Max citations per sentence (≤5)
- Max citations per paragraph (≤12, ≤18 for review)
- Warn at 80% threshold
"""
import os, sys, re
from dataclasses import dataclass, field

ENGINE_DIR = os.path.join(os.path.dirname(__file__), os.pardir, os.pardir, os.pardir, "engine")
if ENGINE_DIR not in sys.path:
    sys.path.insert(0, ENGINE_DIR)

from validators.citation_validator import ValidationFinding


class DensityValidator:
    """Validate citation density constraints"""

    MAX_PER_SENTENCE = 5
    MAX_PER_PARAGRAPH = 12
    MAX_REVIEW_PARAGRAPH = 18
    WARN_PCT = 0.80

    def __init__(self, manuscript_path: str):
        self._manuscript_path = manuscript_path
        self._findings: list[ValidationFinding] = []

    def validate(self) -> list[ValidationFinding]:
        self._findings = []
        if not os.path.exists(self._manuscript_path):
            self._findings.append(ValidationFinding(
                phase="3", check="Density Manuscript", severity="FAIL",
                detail=f"Manuscript not found: {self._manuscript_path}",
                file=self._manuscript_path, function="DensityValidator.validate"))
            return self._findings

        with open(self._manuscript_path, "r", encoding="utf-8") as f:
            text = f.read()

        self._check_sentence_density(text)
        self._check_paragraph_density(text)
        return self._findings

    def _check_sentence_density(self, text: str):
        sentences = re.split(r'(?<=[.!?。！？])\s+', text)
        violations = []
        max_found = 0
        for i, sent in enumerate(sentences):
            cites = len(re.findall(r'\[@[^\]]+\]', sent))
            if cites > max_found:
                max_found = cites
            if cites > self.MAX_PER_SENTENCE:
                violations.append((i, cites, sent[:80]))
            elif cites >= int(self.MAX_PER_SENTENCE * self.WARN_PCT):
                violations.append((i, cites, sent[:80]))

        over_max = [v for v in violations if v[1] > self.MAX_PER_SENTENCE]
        if over_max:
            self._findings.append(ValidationFinding(
                phase="3", check="Sentence Density", severity="FAIL",
                detail=f"{len(over_max)} sentences exceed max density {self.MAX_PER_SENTENCE} (max found: {max_found})",
                root_cause="Too many papers matched to same sentence; overflow limit not enforced",
                suggestion="Check MAX_PAPERS_PER_SENTENCE in semantic_mapper.py",
                file=self._manuscript_path, function="DensityValidator._check_sentence_density"))
        elif max_found >= int(self.MAX_PER_SENTENCE * self.WARN_PCT):
            self._findings.append(ValidationFinding(
                phase="3", check="Sentence Density", severity="WARNING",
                detail=f"Max sentence density {max_found}/{self.MAX_PER_SENTENCE} (above {self.WARN_PCT:.0%} warn threshold)",
                root_cause="Some sentences approaching density limit",
                suggestion="Monitor for potential overflow as paper count grows",
                file=self._manuscript_path, function="DensityValidator._check_sentence_density"))
        else:
            self._findings.append(ValidationFinding(
                phase="3", check="Sentence Density", severity="PASS",
                detail=f"Max sentence density: {max_found}/{self.MAX_PER_SENTENCE}",
                function="DensityValidator._check_sentence_density"))

    def _check_paragraph_density(self, text: str):
        paragraphs = re.split(r'\n\s*\n', text)
        violations = []
        max_found = 0
        for i, para in enumerate(paragraphs):
            if len(para.strip()) < 20:
                continue
            cites = len(re.findall(r'\[@[^\]]+\]', para))
            if cites > max_found:
                max_found = cites
            threshold = self.MAX_REVIEW_PARAGRAPH if self._is_review_paragraph(para) else self.MAX_PER_PARAGRAPH
            if cites > threshold:
                violations.append((i, cites, para[:80], threshold))

        over_max = [v for v in violations if v[1] > self.MAX_PER_PARAGRAPH]
        if over_max:
            self._findings.append(ValidationFinding(
                phase="3", check="Paragraph Density", severity="FAIL",
                detail=f"{len(over_max)} paragraphs exceed max density (max: {max_found})",
                root_cause="Density controller not limiting paragraph-level injection",
                suggestion="Check density_controller.py paragraph limits",
                file=self._manuscript_path, function="DensityValidator._check_paragraph_density"))
        elif max_found >= int(self.MAX_PER_PARAGRAPH * self.WARN_PCT):
            self._findings.append(ValidationFinding(
                phase="3", check="Paragraph Density", severity="WARNING",
                detail=f"Max paragraph density {max_found}/{self.MAX_PER_PARAGRAPH}",
                root_cause="Some paragraphs approaching density limit",
                suggestion="Monitor paragraph density growth",
                file=self._manuscript_path, function="DensityValidator._check_paragraph_density"))
        else:
            self._findings.append(ValidationFinding(
                phase="3", check="Paragraph Density", severity="PASS",
                detail=f"Max paragraph density: {max_found}/{self.MAX_PER_PARAGRAPH}",
                function="DensityValidator._check_paragraph_density"))

    def _is_review_paragraph(self, para: str) -> bool:
        return bool(re.search(r'intro|background|review|survey|related work',
                    para[:200], re.IGNORECASE))


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(description="Density Validator (Phase 3)")
    p.add_argument("--manuscript", required=True, help="Path to injected manuscript")
    args = p.parse_args()
    v = DensityValidator(args.manuscript)
    for f in v.validate():
        print(f"[{f.severity}] Phase {f.phase}: {f.check} — {f.detail}")
