"""test_runtime_policy_override.py — v2.3.2: Runtime policy override without YAML change"""
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


def make_candidate(citekey, journal, sentence="Test."):
    return CitationCandidate(
        paper=PaperIntel(citekey=citekey, title="T", paper_type="research",
                       journal=journal, technical_keywords=["t"], semantic_anchors=["t"]),
        target_sentence=sentence, section="1", similarity_score=0.5, reason="ok",
    )


class TestRuntimeOverrideDoesNotModifyYAML:
    def test_yaml_profile_unchanged_after_override(self):
        """Runtime override changes gate behavior, not the YAML file"""
        pm = get_policy()
        pm.load_profile("advanced_materials_review", PROFILES_DIR)

        # Record original profile value
        original = pm.body_if_threshold

        # Apply runtime override
        gate = BodyCitationIFGate()
        gate.apply_runtime_policy(body_threshold=99.0)

        # Profile YAML value unchanged
        assert pm.body_if_threshold == original

        # But gate uses overridden value
        c = make_candidate("T1", "ACS Nano")  # IF=15.8 < 99
        report = gate.validate_candidates([c])
        assert report.decisions[0].result == IFGateResult.BELOW_THRESHOLD


class TestOverridePersistence:
    def test_override_only_affects_gate_instance(self):
        """Override on one gate instance doesn't affect another"""
        pm = get_policy()
        pm.load_profile("advanced_materials_review", PROFILES_DIR)

        gate1 = BodyCitationIFGate()
        gate1.apply_runtime_policy(body_threshold=99.0)

        gate2 = BodyCitationIFGate()
        # gate2 uses profile defaults

        c = make_candidate("T1", "ACS Nano")  # IF=15.8
        r1 = gate1.validate_candidates([c])
        r2 = gate2.validate_candidates([c])

        # gate1 blocked (99 > 15.8), gate2 passed (6 < 15.8)
        assert r1.decisions[0].result == IFGateResult.BELOW_THRESHOLD
        assert r2.decisions[0].result == IFGateResult.GLOBAL_PASS


class TestProfileSwitchingWithOverride:
    def test_override_survives_profile_reload(self):
        """Gate override persists regardless of profile changes"""
        pm = get_policy()
        pm.load_profile("advanced_materials_review", PROFILES_DIR)

        gate = BodyCitationIFGate()
        gate.apply_runtime_policy(body_threshold=12.0)

        # Switch profile
        pm.load_profile("nature_review", PROFILES_DIR)

        # Gate still uses its override (12.0), not nature's default (15.0)
        c = make_candidate("T1", "ACS Sens.")  # IF=8.5
        report = gate.validate_candidates([c])
        # 8.5 < 12 → blocked by gate's override
        assert report.decisions[0].result == IFGateResult.BELOW_THRESHOLD


class TestBackwardCompatibility:
    def test_set_user_threshold_still_works(self):
        """Legacy set_user_threshold API still functional"""
        pm = get_policy()
        pm.load_profile("advanced_materials_review", PROFILES_DIR)

        gate = BodyCitationIFGate()
        gate.set_user_threshold(8.0)  # legacy API

        c = make_candidate("T1", "ACS Sens.")  # IF=8.5 >= 8
        report = gate.validate_candidates([c])
        assert report.decisions[0].result == IFGateResult.GLOBAL_PASS

    def test_legacy_api_sets_confirmed(self):
        gate = BodyCitationIFGate()
        gate.set_user_threshold(6.0)
        assert gate.is_confirmed


class TestFullOverrideFlow:
    def test_accept_defaults_flow(self):
        """Complete flow: load profile → accept defaults → validate"""
        pm = get_policy()
        pm.load_profile("advanced_materials_review", PROFILES_DIR)

        gate = BodyCitationIFGate()
        prompt = gate.confirmation_prompt()
        assert "advanced_materials_review" in prompt

        # User accepts defaults
        gate.apply_runtime_policy()

        candidates = [
            make_candidate("Nat", "Nature"),              # IF=50.5 → pass
            make_candidate("Mid", "npj Flexible Electron."), # IF=9.2 → pass
            make_candidate("Low", "IEEE Access"),          # IF=3.4 → blocked
        ]
        report = gate.validate_candidates(candidates)
        assert report.pass_count == 2
        assert report.block_count == 1

    def test_customize_flow(self):
        """Complete flow: load → customize thresholds → validate"""
        pm = get_policy()
        pm.load_profile("advanced_materials_review", PROFILES_DIR)

        gate = BodyCitationIFGate()
        gate.apply_runtime_policy(body_threshold=12.0, table_threshold=25.0)

        # Body: only Nature (50.5) ≥ 12 passes
        c_body = make_candidate("Nat", "Nature")
        c_body2 = make_candidate("Mid", "ACS Sens.")  # 8.5 < 12

        report = gate.validate_candidates([c_body, c_body2])
        assert report.pass_count == 1

    def test_disable_flow(self):
        """Complete flow: load → disable → validate (all pass)"""
        pm = get_policy()
        pm.load_profile("advanced_materials_review", PROFILES_DIR)

        gate = BodyCitationIFGate()
        gate.apply_runtime_policy(disable_if=True)

        candidates = [
            make_candidate("A", "Nature"),
            make_candidate("B", "IEEE Access"),
            make_candidate("C", "Unknown"),
        ]
        report = gate.validate_candidates(candidates)
        assert report.pass_count == 3
        assert report.block_count == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
