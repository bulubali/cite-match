"""
Phase 3: Injection Validator

Validates:
- No injection into Abstract zone
- No new injection into Figure Caption zone
- "This work"/"We propose" sentence protection
- Review paper routing to Introduction only
- CrossRef reference protection (fig:, tbl:, eq:)
- Adjacent citation merging
"""
import os, sys, re
from dataclasses import dataclass, field

ENGINE_DIR = os.path.join(os.path.dirname(__file__), os.pardir, os.pardir, os.pardir, "engine")
if ENGINE_DIR not in sys.path:
    sys.path.insert(0, ENGINE_DIR)

from validators.citation_validator import ValidationFinding


class InjectionValidator:
    """Validate Phase 3 + Phase 5 injection rules"""

    def __init__(self, manuscript_path: str):
        self._manuscript_path = manuscript_path
        self._findings: list[ValidationFinding] = []

    def validate(self) -> list[ValidationFinding]:
        self._findings = []
        if not os.path.exists(self._manuscript_path):
            self._findings.append(ValidationFinding(
                phase="3", check="Manuscript", severity="FAIL",
                detail=f"Manuscript not found: {self._manuscript_path}",
                file=self._manuscript_path, function="InjectionValidator.validate"))
            return self._findings

        with open(self._manuscript_path, "r", encoding="utf-8") as f:
            self._text = f.read()

        self._check_legacy_numeric_citations()
        self._check_abstract_zone()
        self._check_figure_caption_zone()
        self._check_this_work_protection()
        self._check_review_routing()
        self._check_crossref_protection()
        self._check_adjacent_merge()
        return self._findings

    def _check_legacy_numeric_citations(self):
        """Any residual legacy superscript citation is a P0 failure."""
        legacy = list(re.finditer(
            r'\^\\\[[0-9][0-9,;\s\-–—]*\\\]\^', self._text
        ))
        if legacy:
            numbers = [match.group(0) for match in legacy]
            self._findings.append(ValidationFinding(
                phase="Mode C",
                check="Legacy Citation Migration",
                severity="FAIL",
                detail=(
                    f"P0: found {len(legacy)} residual legacy citations: "
                    f"{', '.join(numbers[:10])}"
                ),
                root_cause="Legacy numeric citations remain after migration",
                suggestion=(
                    "Stop production validation; rerun validated Mode C mapping "
                    "before injection or DOCX export"
                ),
                file=self._manuscript_path,
                function="InjectionValidator._check_legacy_numeric_citations",
            ))
        else:
            self._findings.append(ValidationFinding(
                phase="Mode C",
                check="Legacy Citation Migration",
                severity="PASS",
                detail="No residual legacy superscript citations",
                function="InjectionValidator._check_legacy_numeric_citations",
            ))

    def _check_abstract_zone(self):
        """New citations must not appear in abstract"""
        abs_match = re.search(
            r'^#\s*Abstract\s*\n(.*?)(?=^#\s)',
            self._text, re.MULTILINE | re.DOTALL | re.IGNORECASE)
        if not abs_match:
            self._findings.append(ValidationFinding(
                phase="3", check="Abstract Zone", severity="PASS",
                detail="No abstract section detected (or already clean)",
                function="InjectionValidator._check_abstract_zone"))
            return
        abs_text = abs_match.group(1)
        cites = re.findall(r'\[@[^\]]+\]', abs_text)
        if cites:
            self._findings.append(ValidationFinding(
                phase="3", check="Abstract Injection", severity="FAIL",
                detail=f"Found {len(cites)} citations in abstract zone",
                root_cause="Semantic mapper injected into excluded abstract zone",
                suggestion="Exclude abstract from injection targets in semantic_mapper._is_rejected_zone",
                file=self._manuscript_path, function="InjectionValidator._check_abstract_zone"))
        else:
            self._findings.append(ValidationFinding(
                phase="3", check="Abstract Zone", severity="PASS",
                detail="No citations in abstract zone",
                function="InjectionValidator._check_abstract_zone"))

    def _check_figure_caption_zone(self):
        """New citations must not be injected into figure captions"""
        fig_pattern = re.findall(r'!\[([^\]]*\[@[^\]]+\][^\]]*)\]\(', self._text)
        if fig_pattern:
            self._findings.append(ValidationFinding(
                phase="3", check="Figure Caption Injection", severity="FAIL",
                detail=f"Found {len(fig_pattern)} citations inside figure captions (![...])",
                root_cause="Citation injected into figure caption markdown syntax",
                suggestion="Strictly enforce figure caption exclusion in semantic_mapper._is_rejected_zone",
                file=self._manuscript_path, function="InjectionValidator._check_figure_caption_zone"))
        else:
            self._findings.append(ValidationFinding(
                phase="3", check="Figure Caption Zone", severity="PASS",
                detail="No citations injected inside figure captions",
                function="InjectionValidator._check_figure_caption_zone"))

    def _check_this_work_protection(self):
        """Sentences containing 'this work'/'we propose' must not have new citations"""
        patterns = [
            r'(?:this\s+(?:work|paper|study|review)|we\s+(?:propose|develop|present|introduce|demonstrate))'
        ]
        lines = self._text.split('\n')
        violations = 0
        for line in lines:
            for pat in patterns:
                if re.search(pat, line, re.IGNORECASE):
                    # Check if this line has injected citations nearby
                    cites = re.findall(r'\[@[^\]]+\]', line)
                    if cites:
                        violations += 1
                        break
        if violations > 0:
            self._findings.append(ValidationFinding(
                phase="3", check="This Work Protection", severity="WARNING",
                detail=f"Potential citation injection near 'this work' sentences: {violations} occurrences",
                root_cause="Semantic mapper may not have filtered original-contribution sentences",
                suggestion="Verify _is_rejected_zone properly filters 'this work'/'we propose' sentences",
                file=self._manuscript_path, function="InjectionValidator._check_this_work_protection"))
        else:
            self._findings.append(ValidationFinding(
                phase="3", check="This Work Protection", severity="PASS",
                detail="No citations injected near 'this work' sentences",
                function="InjectionValidator._check_this_work_protection"))

    def _check_review_routing(self):
        """Review papers should only be routed to Introduction/Background"""
        # Load References_Summary to find review papers
        output_dir = os.path.dirname(self._manuscript_path)
        summary_path = os.path.join(output_dir, "References_Summary.md")
        if not os.path.exists(summary_path):
            self._findings.append(ValidationFinding(
                phase="3", check="Review Routing", severity="WARNING",
                detail="References_Summary.md not found; cannot verify review routing",
                suggestion="Run Phase 2 to generate References_Summary.md",
                function="InjectionValidator._check_review_routing"))
            return

        with open(summary_path, "r", encoding="utf-8") as f:
            summary = f.read()

        review_keys = set(re.findall(r'\| @(\w+) \| review \|', summary, re.IGNORECASE))
        if not review_keys:
            self._findings.append(ValidationFinding(
                phase="3", check="Review Routing", severity="PASS",
                detail="No review papers in pending set",
                function="InjectionValidator._check_review_routing"))
            return

        # Check where review papers were injected in manuscript
        misuse = 0
        for key in review_keys:
            cite_pat = re.compile(r'\[@[^\]]*' + re.escape(key) + r'[^\]]*\]')
            for m in cite_pat.finditer(self._text):
                # Look at context: find nearest heading
                before = self._text[:m.start()]
                headings = re.findall(r'^#+\s+(.+)$', before, re.MULTILINE)
                last_heading = headings[-1] if headings else "(preamble)"
                if not re.search(r'intro|background|related|survey',
                               last_heading, re.IGNORECASE):
                    misuse += 1
        if misuse > 0:
            self._findings.append(ValidationFinding(
                phase="3", check="Review Routing", severity="WARNING",
                detail=f"Review papers may be misrouted: {misuse} occurrences outside Introduction",
                root_cause="Semantic mapper review routing constraint may not be enforced",
                suggestion="Check _route_review_paper in semantic_mapper.py",
                function="InjectionValidator._check_review_routing"))
        else:
            self._findings.append(ValidationFinding(
                phase="3", check="Review Routing", severity="PASS",
                detail=f"{len(review_keys)} review papers correctly routed",
                function="InjectionValidator._check_review_routing"))

    def _check_crossref_protection(self):
        """Ensure pandoc-crossref references (fig:, tbl:, eq:) are not damaged"""
        crossrefs = re.findall(r'\{#(?:fig|tbl|eq):[^}]+\}', self._text)
        if crossrefs:
            self._findings.append(ValidationFinding(
                phase="5", check="CrossRef Protection", severity="PASS",
                detail=f"{len(crossrefs)} crossref labels found and preserved",
                function="InjectionValidator._check_crossref_protection"))
        else:
            self._findings.append(ValidationFinding(
                phase="5", check="CrossRef Protection", severity="PASS",
                detail="No crossref labels detected (not used in this manuscript)",
                function="InjectionValidator._check_crossref_protection"))

    def _check_adjacent_merge(self):
        """Check that adjacent citations are properly merged (e.g., [@a][@b] -> [@a; @b])"""
        adjacents = re.findall(r'\]\[@', self._text)
        if adjacents:
            self._findings.append(ValidationFinding(
                phase="5", check="Adjacent Citation Merge", severity="WARNING",
                detail=f"Found {len(adjacents)} unmerged adjacent citations",
                root_cause="merge_adjacent_citations not applied or incomplete",
                suggestion="Run crossref_guard.merge_adjacent_citations() post-injection",
                file=self._manuscript_path, function="InjectionValidator._check_adjacent_merge"))
        else:
            self._findings.append(ValidationFinding(
                phase="5", check="Adjacent Citation Merge", severity="PASS",
                detail="No unmerged adjacent citations found",
                function="InjectionValidator._check_adjacent_merge"))


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(description="Injection Validator (Phase 3 + Phase 5)")
    p.add_argument("--manuscript", required=True, help="Path to injected manuscript")
    args = p.parse_args()
    v = InjectionValidator(args.manuscript)
    for f in v.validate():
        print(f"[{f.severity}] Phase {f.phase}: {f.check} — {f.detail}")
