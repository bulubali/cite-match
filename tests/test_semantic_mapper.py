"""test_semantic_mapper.py — Phase 3: Semantic Mapping Layer"""
import sys, os, pytest

ENGINE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "engine")
sys.path.insert(0, ENGINE_DIR)

from literature_intel import PaperIntel, LiteratureIntelligence
from semantic_mapper import SemanticMapper, CitationCandidate
from sample_data import SAMPLE_BIB, SAMPLE_DRAFT_EN


@pytest.fixture
def mapper():
    return SemanticMapper()


@pytest.fixture
def sample_papers():
    intel = LiteratureIntelligence()
    # Create papers manually for testing
    return [
        PaperIntel(
            citekey="PiezoSensor2024",
            title="Flexible Piezoelectric Sensor for Blood Pressure",
            paper_type="research",
            core_finding="Achieves sensitivity of 85 kPa^-1",
            technical_keywords=["piezoelectric", "blood pressure", "sensitivity"],
            semantic_anchors=["piezoelectric", "blood pressure", "flexible sensor",
                            "sensitivity", "pulse wave"],
            recommended_section="§3.1.1 Piezoelectric Materials",
        ),
        PaperIntel(
            citekey="DeepLearnBP2023",
            title="Deep Learning for Cuffless BP Estimation",
            paper_type="research",
            core_finding="CNN achieves MAE < 3 mmHg",
            technical_keywords=["deep learning", "cuffless", "cnn"],
            semantic_anchors=["deep learning", "machine learning", "neural network",
                            "blood pressure estimation", "pulse wave analysis"],
            recommended_section="§2.1.1 PWA + ML/DL",
        ),
    ]


class TestSemanticMapper:
    def test_parse_manuscript(self, mapper):
        mapper._parse_manuscript(SAMPLE_DRAFT_EN)
        assert len(mapper._sentences) > 0

    def test_map_papers_finds_matches(self, mapper, sample_papers):
        candidates = mapper.map_papers_to_manuscript(sample_papers, SAMPLE_DRAFT_EN)
        assert len(candidates) == 2

    def test_candidate_has_fields(self, mapper, sample_papers):
        candidates = mapper.map_papers_to_manuscript(sample_papers, SAMPLE_DRAFT_EN)
        for c in candidates:
            assert c.paper is not None
            assert isinstance(c.similarity_score, float)
            assert isinstance(c.reason, str)

    def test_generate_candidate_table(self, mapper, sample_papers):
        candidates = mapper.map_papers_to_manuscript(sample_papers, SAMPLE_DRAFT_EN)
        table = mapper.generate_candidate_table(candidates)
        assert "Citation Candidate" in table
        for p in sample_papers:
            assert p.citekey in table

    def test_abstract_rejected(self, mapper):
        p = PaperIntel(
            citekey="Test2024",
            title="Test Paper",
            semantic_anchors=["test", "paper"],
            technical_keywords=["test"],
            recommended_section="Abstract",
        )
        text = "## Abstract\n\nThis is the abstract.\n\n## Introduction\n\nBlood pressure monitoring.\n"
        candidates = mapper.map_papers_to_manuscript([p], text)
        # Either rejected (no match in abstract) or matched in intro
        # Abstract should be rejected zone
        assert all(not mapper._is_rejected_zone(c.section, c.target_sentence)
                   for c in candidates if not c.is_rejected)

    def test_this_work_rejected(self, mapper):
        p = PaperIntel(
            citekey="Test2024",
            title="Test Paper",
            semantic_anchors=["novel", "propose", "demonstrate"],
            technical_keywords=["test"],
            recommended_section="§1",
        )
        text = "## Introduction\n\nIn this work, we propose a novel sensor.\n"
        candidates = mapper.map_papers_to_manuscript([p], text)
        # "In this work" sentences should be rejected
        for c in candidates:
            if not c.is_rejected:
                assert 'this work' not in c.target_sentence.lower()

    def test_max_papers_per_sentence(self, mapper):
        papers = [
            PaperIntel(citekey=f"Paper{i}", title=f"Paper {i}",
                       semantic_anchors=["sensor", "flexible", "pressure"],
                       technical_keywords=["sensor"])
            for i in range(5)
        ]
        text = "Flexible pressure sensors are important for blood pressure monitoring.\n"
        candidates = mapper.map_papers_to_manuscript(papers, text)
        accepted = [c for c in candidates if not c.is_rejected]
        assert len(accepted) <= mapper.MAX_PAPERS_PER_SENTENCE

    def test_min_similarity_threshold(self, mapper):
        p = PaperIntel(
            citekey="NoMatch2024",
            title="Quantum Computing for Galactic Exploration",
            semantic_anchors=["quantum", "galactic", "space", "universe", "star"],
            technical_keywords=["quantum"],
        )
        text = "Blood pressure monitoring using flexible sensors.\n"
        candidates = mapper.map_papers_to_manuscript([p], text)
        assert len(candidates) == 1
        # Should be rejected or have very low score
        if not candidates[0].is_rejected:
            assert candidates[0].similarity_score >= mapper.MIN_SIMILARITY_THRESHOLD


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
