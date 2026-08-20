"""
CiteMatch v2.3 — Citation Density Controller

Enforces per-sentence and per-paragraph citation limits
from the active policy profile.

Replaces hardcoded MAX_PAPERS_PER_SENTENCE / MAX_PARAGRAPH_PAPERS.
"""
from typing import Optional
from policy_manager import get_policy


class DensityController:
    """Enforce citation density limits from policy profile

    Usage:
        dc = DensityController()
        ok, reason = dc.check_sentence(sentence_citations, paper_type="research")
        if not ok:
            # reject overflow
    """

    def __init__(self):
        self._pm = get_policy()

    def check_sentence(
        self, current_count: int, paper_type: str = "research"
    ) -> tuple[bool, str]:
        """Check if adding one more citation exceeds sentence limit

        Returns:
            (allowed, reason)
        """
        limit = self._pm.sentence_max_citations
        if current_count >= limit:
            return False, (
                f"Sentence density limit reached ({current_count}/{limit})"
            )
        return True, ""

    def check_paragraph(
        self, current_count: int, paper_type: str = "research"
    ) -> tuple[bool, str]:
        """Check if paragraph exceeds citation limit"""
        if paper_type == "review":
            limit = self._pm.paragraph_review_max
        else:
            limit = self._pm.paragraph_normal_max

        if current_count >= limit:
            return False, (
                f"Paragraph density limit reached ({current_count}/{limit})"
            )
        return True, ""

    def get_sentence_limit(self) -> int:
        return self._pm.sentence_max_citations

    def get_paragraph_limit(self, paper_type: str = "research") -> int:
        if paper_type == "review":
            return self._pm.paragraph_review_max
        return self._pm.paragraph_normal_max
