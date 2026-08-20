"""
Phase 3: Figure Validator

Validates:
- No new injection into figure captions (![...])
- Existing figure citations preserved (migration OK)
- Figure markdown syntax intact
"""
import os, sys, re

ENGINE_DIR = os.path.join(os.path.dirname(__file__), os.pardir, os.pardir, os.pardir, "engine")
if ENGINE_DIR not in sys.path:
    sys.path.insert(0, ENGINE_DIR)

from validators.citation_validator import ValidationFinding


class FigureValidator:
    """Validate figure caption protection rules"""

    def __init__(self, manuscript_path: str):
        self._manuscript_path = manuscript_path
        self._findings: list[ValidationFinding] = []

    def validate(self) -> list[ValidationFinding]:
        self._findings = []
        if not os.path.exists(self._manuscript_path):
            self._findings.append(ValidationFinding(
                phase="3", check="Figure Manuscript", severity="FAIL",
                detail=f"Manuscript not found: {self._manuscript_path}",
                file=self._manuscript_path, function="FigureValidator.validate"))
            return self._findings

        with open(self._manuscript_path, "r", encoding="utf-8") as f:
            text = f.read()

        self._check_figure_syntax(text)
        self._check_figure_caption_citations(text)
        return self._findings

    def _check_figure_syntax(self, text: str):
        """Verify all image references have correct markdown syntax"""
        images = re.findall(r'!\[([^\]]*)\]\(([^)]+)\)', text)
        broken = []
        for alt, path in images:
            if not path or not path.strip():
                broken.append(alt[:40])
        if broken:
            self._findings.append(ValidationFinding(
                phase="3", check="Figure Syntax", severity="FAIL",
                detail=f"Broken image references: {len(broken)}",
                root_cause="Citation injection corrupted image markdown syntax",
                suggestion="Check injector AST-aware injection logic",
                file=self._manuscript_path, function="FigureValidator._check_figure_syntax"))
        else:
            self._findings.append(ValidationFinding(
                phase="3", check="Figure Syntax", severity="PASS",
                detail=f"All {len(images)} image references intact",
                function="FigureValidator._check_figure_syntax"))

    def _check_figure_caption_citations(self, text: str):
        """Detect citations inside figure captions"""
        fig_cites = []
        for m in re.finditer(r'!\[([^\]]*)\]\(', text):
            caption = m.group(1)
            cites = re.findall(r'\[@[^\]]+\]', caption)
            if cites:
                fig_cites.append((caption[:60], cites))

        if fig_cites:
            # Existing figure citations (from migration) are OK
            # New injections into figures are not
            self._findings.append(ValidationFinding(
                phase="3", check="Figure Caption Citations", severity="WARNING",
                detail=f"Citations found in {len(fig_cites)} figure captions — verify they are from migration, not new injection",
                root_cause="Citations in figure captions may be from Mode C migration (allowed) or new injection (forbidden)",
                suggestion="Cross-reference with used_keys: if key was already in original draft, it's migration-safe",
                file=self._manuscript_path, function="FigureValidator._check_figure_caption_citations"))
        else:
            self._findings.append(ValidationFinding(
                phase="3", check="Figure Caption Citations", severity="PASS",
                detail="No citations in figure captions",
                function="FigureValidator._check_figure_caption_citations"))


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(description="Figure Validator (Phase 3)")
    p.add_argument("--manuscript", required=True, help="Path to injected manuscript")
    args = p.parse_args()
    v = FigureValidator(args.manuscript)
    for f in v.validate():
        print(f"[{f.severity}] Phase {f.phase}: {f.check} — {f.detail}")
