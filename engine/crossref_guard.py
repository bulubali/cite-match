"""
CiteMatch v2.5 — Cross-Reference Protection

Protects Pandoc-crossref labels (fig:, tbl:, eq:) from citation merge.
"""
import re


# Known cross-reference prefixes
CROSSREF_PREFIXES = ("fig:", "tbl:", "eq:", "#fig:", "#tbl:", "#eq:")


def is_crossref(label: str) -> bool:
    """Check if a label is a Pandoc-crossref identifier.

    Args:
        label: text inside [@...] brackets

    Returns:
        True if this is a cross-reference, not a citation
    """
    stripped = label.strip().lstrip("@")
    for prefix in CROSSREF_PREFIXES:
        if stripped.lower().startswith(prefix.lower()):
            return True
    return False


def filter_crossrefs(citation_text: str) -> tuple[list[str], list[str]]:
    """Split [@a; @b; @fig:1] into citations and crossrefs.

    Returns:
        (citations, crossrefs) — both lists of strings
    """
    inner_match = re.search(r"\[@([^\]]+)\]", citation_text)
    if not inner_match:
        return ([], [])

    inner = inner_match.group(1)
    inner_clean = inner.replace("{", "").replace("}", "")
    parts = re.split(r"[;\s]+", inner_clean)

    citations = []
    crossrefs = []
    for part in parts:
        part = part.strip().lstrip("@")
        if not part:
            continue
        if is_crossref(part):
            crossrefs.append(part)
        else:
            citations.append(part)

    return citations, crossrefs


def merge_adjacent_citations(text: str) -> str:
    """Post-injection pass: merge adjacent [@a] [@b] → [@a; @b].

    Does NOT merge if either bracket contains crossref prefixes.
    """
    # Pattern: [@citation] followed by optional whitespace then [@citation]
    pattern = re.compile(r"\[@([^:\]]+)\]\s*\[@([^:\]]+)\]")

    def replacer(match):
        a = match.group(1).strip()
        b = match.group(2).strip()
        # Check crossref protection
        if is_crossref(a) or is_crossref(b):
            return match.group(0)  # don't merge
        return f"[@{a}; @{b}]"

    # Iterate until no more merges
    prev = None
    while prev != text:
        prev = text
        text = pattern.sub(replacer, text)

    return text
