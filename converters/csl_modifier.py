"""
CiteMatch v2.5 — CSL Modifier (Phase 6)

XML-based CSL modification using xml.etree.ElementTree.
Never uses regex or string replacement on XML.
"""
import os
import xml.etree.ElementTree as ET
from typing import Optional


class CSLModifier:
    """Safe CSL XML modification via ElementTree only."""

    # CSL namespace
    CSL_NS = "http://purl.org/net/xbiblio/csl"

    def __init__(self, csl_path: str):
        self._path = csl_path
        # Register namespace for clean output
        ET.register_namespace("", self.CSL_NS)
        self._tree = ET.parse(csl_path)
        self._root = self._tree.getroot()

    def ensure_collapse(self) -> bool:
        """Ensure citation node has collapse='citation-number'.

        Returns True if modification was made.
        """
        modified = False
        for citation in self._root.iter(f"{{{self.CSL_NS}}}citation"):
            if citation.get("collapse") != "citation-number":
                citation.set("collapse", "citation-number")
                modified = True
        return modified

    def ensure_bibliography_numbering(self) -> bool:
        """Render citation numbers in bibliographies of numeric CSL styles.

        Numeric styles can sort the bibliography by ``citation-number`` while
        omitting that variable from the bibliography layout.  Citeproc then
        orders the entries correctly but has no visible number to emit.  Add a
        plain ``1. ``-style prefix only when the style is numeric and the
        bibliography does not already render a citation number.

        Returns True if modification was made.
        """
        text_tag = f"{{{self.CSL_NS}}}text"
        key_tag = f"{{{self.CSL_NS}}}key"
        citation_tag = f"{{{self.CSL_NS}}}citation"
        bibliography_tag = f"{{{self.CSL_NS}}}bibliography"
        layout_tag = f"{{{self.CSL_NS}}}layout"

        citation_uses_numbers = any(
            elem.tag == text_tag and elem.get("variable") == "citation-number"
            for citation in self._root.iter(citation_tag)
            for elem in citation.iter()
        )

        modified = False
        for bibliography in self._root.iter(bibliography_tag):
            bibliography_sorts_by_number = any(
                elem.tag == key_tag and elem.get("variable") == "citation-number"
                for elem in bibliography.iter()
            )
            if not (citation_uses_numbers or bibliography_sorts_by_number):
                continue

            already_visible = any(
                elem.tag == text_tag and elem.get("variable") == "citation-number"
                for elem in bibliography.iter()
            )
            if already_visible:
                continue

            layout = bibliography.find(layout_tag)
            if layout is None:
                continue
            number = ET.Element(
                text_tag,
                {"variable": "citation-number", "suffix": ". "},
            )
            layout.insert(0, number)
            modified = True

        return modified

    def set_full_author_display(self) -> bool:
        """Set et-al-min and et-al-use-first to show all authors.

        Returns True if modification was made.
        """
        modified = False
        for citation in self._root.iter(f"{{{self.CSL_NS}}}citation"):
            layout = citation.find(f"{{{self.CSL_NS}}}layout")
            if layout is not None:
                if layout.get("et-al-min") != "999":
                    layout.set("et-al-min", "999")
                    modified = True
                if layout.get("et-al-use-first") != "999":
                    layout.set("et-al-use-first", "999")
                    modified = True

        for bibliography in self._root.iter(f"{{{self.CSL_NS}}}bibliography"):
            layout = bibliography.find(f"{{{self.CSL_NS}}}layout")
            if layout is not None:
                if layout.get("et-al-min") != "999":
                    layout.set("et-al-min", "999")
                    modified = True
                if layout.get("et-al-use-first") != "999":
                    layout.set("et-al-use-first", "999")
                    modified = True

        return modified

    def set_default_author_display(self) -> bool:
        """Remove et-al overrides to use journal defaults."""
        modified = False
        for parent_tag in ("citation", "bibliography"):
            for elem in self._root.iter(f"{{{self.CSL_NS}}}{parent_tag}"):
                layout = elem.find(f"{{{self.CSL_NS}}}layout")
                if layout is not None:
                    for attr in ("et-al-min", "et-al-use-first"):
                        if attr in layout.attrib:
                            del layout.attrib[attr]
                            modified = True
        return modified

    def save(self, output_path: Optional[str] = None) -> str:
        """Save modified CSL to disk. Never overwrites original.

        Returns output path.
        """
        if output_path is None:
            base = os.path.splitext(self._path)[0]
            output_path = f"{base}_modified.csl"

        self._tree.write(output_path, encoding="utf-8", xml_declaration=True)
        return output_path

    @staticmethod
    def is_csl_valid(path: str) -> bool:
        """Check if file is valid CSL XML"""
        try:
            tree = ET.parse(path)
            root = tree.getroot()
            return root.tag == f"{{{CSLModifier.CSL_NS}}}style" or root.tag == "style"
        except Exception:
            return False
