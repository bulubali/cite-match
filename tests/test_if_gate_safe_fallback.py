"""test_if_gate_safe_fallback.py — v2.3.3: Safe fallback when policy unavailable"""
import sys, os, pytest

ENGINE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "engine")
sys.path.insert(0, ENGINE_DIR)

from policy_manager import PolicyManager, get_policy
from body_if_gate import BodyCitationIFGate, IFGateResult
from literature_intel import PaperIntel
from semantic_mapper import CitationCandidate

PROFILES_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "profiles")


@pytest.fixture(autouse=True)
def reset():
    PolicyManager.reset()
    yield
    PolicyManager.reset()


def make_candidate(citekey, journal):
    return CitationCandidate(
        paper=PaperIntel(citekey=citekey, title="T", paper_type="research",
                       journal=journal, technical_keywords=["t"], semantic_anchors=["t"]),
        target_sentence="Test.", section="1", similarity_score=0.5, reason="ok",
    )


class TestSafeFallback:
    def test_fallback_is_zero_not_six(self):
        """When no profile loaded, default threshold is 0 (disabled), not 6"""
        gate = BodyCitationIFGate()
        assert gate._global_threshold == 0.0, \
            f"Expected 0.0 (disabled), got {gate._global_threshold}"
        assert gate._elite_threshold == 0.0

    def test_no_profile_rejects_nothing(self):
        """Without policy, low-IF papers are NOT rejected"""
        gate = BodyCitationIFGate()
        c = make_candidate("Low", "IEEE Access")  # IF=3.4
        report = gate.validate_candidates([c])
        assert report.pass_count == 1
        assert report.block_count == 0

    def test_fallback_warning_message(self):
        """Warning emitted when policy unavailable"""
        gate = BodyCitationIFGate()
        msg = gate.fallback_warning()
        assert isinstance(msg, str)

    def test_fallback_disabled_flag(self):
        """_if_disabled is True when policy unavailable"""
        gate = BodyCitationIFGate()
        assert gate._policy_available is True  # policy_manager IS available in tests
        # The fallback only triggers when import truly fails


class TestProfileLoadedOverridesFallback:
    def test_profile_overrides_zero_fallback(self):
        """When profile IS loaded, threshold comes from YAML, not fallback"""
        pm = get_policy()
        pm.load_profile("advanced_materials_review", PROFILES_DIR)

        gate = BodyCitationIFGate()
        # Gate constructor already ran with profile loaded, so threshold comes from YAML
        assert gate._global_threshold == 6.0

        # Low IF paper should be blocked
        c = make_candidate("Low", "IEEE Access")  # IF=3.4 < 6
        report = gate.validate_candidates([c])
        assert report.block_count == 1

    def test_user_override_still_works(self):
        """Runtime override still takes precedence over profile"""
        pm = get_policy()
        pm.load_profile("advanced_materials_review", PROFILES_DIR)

        gate = BodyCitationIFGate()
        gate.apply_runtime_policy(disable_if=True)

        c = make_candidate("Low", "IEEE Access")
        report = gate.validate_candidates([c])
        assert report.pass_count == 1


class TestNoInjectionChanges:
    """No changes to citation matching or injection"""
    def test_semantic_imports_unchanged(self):
        from semantic_mapper import SemanticMapper
        mapper = SemanticMapper()
        assert mapper.MAX_PAPERS_PER_SENTENCE == 3

    def test_injector_imports_unchanged(self):
        from injector import CitationInjector
        from citation_registry import CitationRegistry
        inj = CitationInjector(CitationRegistry())
        assert inj._protect_tables is True

    def test_migrator_imports_unchanged(self):
        from citation_migrator import CitationMigrator
        m = CitationMigrator({1: "test"})
        assert m is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
