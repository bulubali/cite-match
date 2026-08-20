"""
Phase 6: CSL Validator

Validates:
- CSL file existence and valid XML
- Citation collapse attribute applied
- Et-al modification (if user requested all authors)
"""
import os, sys, re
import xml.etree.ElementTree as ET

ENGINE_DIR = os.path.join(os.path.dirname(__file__), os.pardir, os.pardir, os.pardir, "engine")
if ENGINE_DIR not in sys.path:
    sys.path.insert(0, ENGINE_DIR)

from validators.citation_validator import ValidationFinding

CSL_NS = "http://purl.org/net/xbiblio/csl"


class CslValidator:
    """Validate CSL modification and integrity"""

    def __init__(self, csl_path: str, all_authors_requested: bool = False):
        self._csl_path = csl_path
        self._all_authors = all_authors_requested
        self._findings: list[ValidationFinding] = []

    def validate(self) -> list[ValidationFinding]:
        self._findings = []
        if not os.path.exists(self._csl_path):
            self._findings.append(ValidationFinding(
                phase="6", check="CSL File", severity="FAIL",
                detail=f"CSL file not found: {self._csl_path}",
                file=self._csl_path, function="CslValidator.validate"))
            return self._findings

        try:
            self._tree = ET.parse(self._csl_path)
            self._root = self._tree.getroot()
        except ET.ParseError as e:
            self._findings.append(ValidationFinding(
                phase="6", check="CSL XML", severity="FAIL",
                detail=f"CSL XML parse error: {e}",
                root_cause="Corrupted or malformed CSL file",
                suggestion="Re-download CSL from official repository",
                file=self._csl_path, function="CslValidator.validate"))
            return self._findings

        self._check_collapse()
        if self._all_authors:
            self._check_et_al_removal()
        return self._findings

    def _check_collapse(self):
        """Verify citation-number collapse is enabled"""
        for cit in self._root.iter(f'{{{CSL_NS}}}citation'):
            collapse = cit.get('collapse')
            if collapse == 'citation-number':
                self._findings.append(ValidationFinding(
                    phase="6", check="CSL Collapse", severity="PASS",
                    detail='collapse="citation-number" applied',
                    function="CslValidator._check_collapse"))
                return
        self._findings.append(ValidationFinding(
            phase="6", check="CSL Collapse", severity="FAIL",
            detail="collapse='citation-number' NOT found in <citation>",
            root_cause="CSL modifier did not add collapse attribute",
            suggestion="Modify CSL: add collapse='citation-number' to <citation> tag",
            file=self._csl_path, function="CslValidator._check_collapse"))

    def _check_et_al_removal(self):
        """Verify et-al attributes removed (all authors shown)"""
        et_al_attrs = []
        for tag_name in ['citation', 'bibliography']:
            for elem in self._root.iter(f'{{{CSL_NS}}}{tag_name}'):
                for attr in ['et-al-min', 'et-al-use-first', 'et-al-subsequent-min']:
                    val = elem.get(attr)
                    if val and val != '999':
                        et_al_attrs.append(f"<{tag_name}> {attr}={val}")

        if et_al_attrs:
            self._findings.append(ValidationFinding(
                phase="6", check="CSL All Authors", severity="WARNING",
                detail=f"Et-al limits still present: {et_al_attrs}",
                root_cause="CSL modifier did not fully remove et-al constraints",
                suggestion="Delete et-al-min, et-al-use-first, et-al-subsequent-min from CSL",
                file=self._csl_path, function="CslValidator._check_et_al_removal"))
        else:
            self._findings.append(ValidationFinding(
                phase="6", check="CSL All Authors", severity="PASS",
                detail="All authors mode: et-al limits properly removed",
                function="CslValidator._check_et_al_removal"))


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(description="CSL Validator (Phase 6)")
    p.add_argument("--csl", required=True, help="Path to CSL file")
    p.add_argument("--all-authors", action="store_true", help="Check et-al removal")
    args = p.parse_args()
    v = CslValidator(args.csl, args.all_authors)
    for f in v.validate():
        print(f"[{f.severity}] Phase {f.phase}: {f.check} — {f.detail}")
