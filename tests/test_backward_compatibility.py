"""test_backward_compatibility.py — v2.3: No behavior change under advanced_materials_review"""
import sys, os, pytest

ENGINE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "engine")
sys.path.insert(0, ENGINE_DIR)

from policy_manager import PolicyManager, get_policy

PROFILES_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "profiles")


@pytest.fixture(autouse=True)
def reset():
    PolicyManager.reset()
    yield
    PolicyManager.reset()


class TestDensityControllerBackwardCompat:
    def test_sentence_limit_matches_old(self):
        """Density controller uses policy profile value"""
        pm = get_policy()
        pm.load_profile("advanced_materials_review", PROFILES_DIR)

        from density_controller import DensityController
        dc = DensityController()
        assert dc.get_sentence_limit() == 5

    def test_paragraph_limit_matches_old(self):
        pm = get_policy()
        pm.load_profile("advanced_materials_review", PROFILES_DIR)

        from density_controller import DensityController
        dc = DensityController()
        assert dc.get_paragraph_limit("research") == 12
        assert dc.get_paragraph_limit("review") == 18

    def test_sentence_check_at_limit(self):
        pm = get_policy()
        pm.load_profile("advanced_materials_review", PROFILES_DIR)

        from density_controller import DensityController
        dc = DensityController()
        ok, reason = dc.check_sentence(5, "research")
        assert not ok  # At limit (5) → blocked
        ok2, _ = dc.check_sentence(4, "research")
        assert ok2  # Below limit → allowed


class TestSemanticMapperBackwardCompat:
    def test_constants_unchanged(self):
        """Semantic mapper constants still have correct defaults"""
        from semantic_mapper import (
            IF_THRESHOLD_ELITE, IF_THRESHOLD_GLOBAL,
            INTRODUCTION_KEYWORDS,
        )
        assert IF_THRESHOLD_ELITE == 10
        assert IF_THRESHOLD_GLOBAL == 6
        assert "introduction" in INTRODUCTION_KEYWORDS

    def test_mapper_works_with_profile(self):
        """Semantic mapper works when profile is loaded"""
        pm = get_policy()
        pm.load_profile("advanced_materials_review", PROFILES_DIR)

        from semantic_mapper import SemanticMapper
        mapper = SemanticMapper()
        assert mapper.MAX_PAPERS_PER_SENTENCE == 3
        assert mapper.MIN_SIMILARITY_THRESHOLD == 0.15


class TestBodyIFGateBackwardCompat:
    def test_default_thresholds_safe_fallback(self):
        """v2.3.3: IF gate defaults to 0 (disabled) without profile"""
        from body_if_gate import BodyCitationIFGate
        gate = BodyCitationIFGate()
        assert gate._global_threshold == 0.0
        assert gate._elite_threshold == 0.0

    def test_validate_still_works(self):
        """IF gate validate still works"""
        from body_if_gate import BodyCitationIFGate
        from literature_intel import PaperIntel
        from semantic_mapper import CitationCandidate

        pm = get_policy()
        pm.load_profile("advanced_materials_review", PROFILES_DIR)

        gate = BodyCitationIFGate()
        gate.set_user_threshold(6.0)

        c = CitationCandidate(
            paper=PaperIntel(citekey="T1", title="T", paper_type="research",
                           journal="Nature", technical_keywords=["t"], semantic_anchors=["t"]),
            target_sentence="Test.", section="1", similarity_score=0.5, reason="ok",
        )
        report = gate.validate_candidates([c])
        assert report.pass_count == 1


class TestProfileSingleton:
    def test_get_policy_returns_same_instance(self):
        a = get_policy()
        b = get_policy()
        assert a is b

    def test_singleton_survives_reset(self):
        PolicyManager.reset()
        pm1 = get_policy()
        PolicyManager.reset()
        pm2 = get_policy()
        assert pm1 is not pm2  # Different instances after reset


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
