"""test_review_if_routing.py — v2.2.3: Review paper IF + routing rules"""
import sys, os, pytest

ENGINE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "engine")
sys.path.insert(0, ENGINE_DIR)

from body_if_gate import BodyCitationIFGate, IFGateResult
from literature_intel import PaperIntel
from semantic_mapper import CitationCandidate, SemanticMapper


@pytest.fixture
def gate():
    return BodyCitationIFGate()


MANUSCRIPT_WITH_INTRO = """# Introduction

Blood pressure monitoring is essential for cardiovascular health.
Flexible sensors have revolutionized wearable monitoring.
Recent advances include piezoelectric and piezoresistive approaches.

## Results

The sensor achieved sensitivity of 85 kPa^-1 with a response time of 10 ms.
Our proposed design outperforms existing solutions by 40%.
"""


class TestReviewIFRouting:
    def test_review_paper_in_intro_passes(self, gate):
        """Review paper in Introduction → passes IF gate"""
        c = CitationCandidate(
            paper=PaperIntel(citekey="Review1", title="Review of BP Sensors",
                           paper_type="review", journal="Nat. Rev. Cardiol.",
                           technical_keywords=["review"], semantic_anchors=["review"]),
            target_sentence="Blood pressure monitoring is essential.",
            section="Introduction", similarity_score=0.7, reason="matched",
        )
        gate.set_user_threshold(6.0)
        report = gate.validate_candidates([c])
        assert report.decisions[0].result == IFGateResult.GLOBAL_PASS

    def test_review_paper_in_results_still_checked(self, gate):
        """Review paper in Results section — IF gate still applied"""
        c = CitationCandidate(
            paper=PaperIntel(citekey="Review2", title="Review Paper",
                           paper_type="review", journal="IEEE Access",
                           technical_keywords=["review"], semantic_anchors=["review"]),
            target_sentence="The sensor achieved sensitivity of 85 kPa^-1.",
            section="Results", similarity_score=0.5, reason="matched",
        )
        gate.set_user_threshold(6.0)
        report = gate.validate_candidates([c])
        # IEEE Access IF=3.4 < 6 → blocked
        assert report.decisions[0].result == IFGateResult.BELOW_THRESHOLD
        assert report.decisions[0].gate_type == 'review'

    def test_review_high_if_passes(self, gate):
        """Review in high-IF journal → passes even in body"""
        c = CitationCandidate(
            paper=PaperIntel(citekey="Review3", title="High IF Review",
                           paper_type="review", journal="Nat. Rev. Cardiol.",
                           technical_keywords=["review"], semantic_anchors=["review"]),
            target_sentence="Flexible sensors have revolutionized monitoring.",
            section="Introduction", similarity_score=0.8, reason="matched",
        )
        gate.set_user_threshold(10.0)
        report = gate.validate_candidates([c])
        # Nat Rev Cardiol IF=18.0 >= 10 → passes
        assert report.decisions[0].result == IFGateResult.GLOBAL_PASS


class TestReviewSemanticRouting:
    def test_review_blocked_from_quantitative_sentence(self):
        """Semantic mapper blocks review from quantitative claims"""
        paper = PaperIntel(
            citekey="Review4", title="Review Paper",
            paper_type="review", journal="Nature",
            technical_keywords=["review"], semantic_anchors=["review", "sensor", "advances"],
            recommended_section="1",
        )
        mapper = SemanticMapper()
        candidates = mapper.map_papers_to_manuscript([paper], MANUSCRIPT_WITH_INTRO)
        accepted = [c for c in candidates if not c.is_rejected]
        for c in accepted:
            # Should not match "sensitivity of 85 kPa^-1" (quantitative)
            assert '85 kPa' not in c.target_sentence

    def test_review_allowed_in_intro(self):
        """Review paper allowed in Introduction"""
        paper = PaperIntel(
            citekey="Review5", title="Review of Wearable BP",
            paper_type="review", journal="Nat. Rev. Cardiol.",
            technical_keywords=["review", "wearable"],
            semantic_anchors=["review", "wearable", "flexible", "sensors", "advances"],
            recommended_section="1",
        )
        mapper = SemanticMapper()
        candidates = mapper.map_papers_to_manuscript([paper], MANUSCRIPT_WITH_INTRO)
        accepted = [c for c in candidates if not c.is_rejected]
        assert len(accepted) >= 1, "Review should find a match in Introduction"
        for c in accepted:
            assert 'Introduction' in c.section or 'intro' in c.section.lower()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
