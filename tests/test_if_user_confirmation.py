"""test_if_user_confirmation.py — v2.3.2: Interactive IF gate confirmation"""
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


class TestConfirmationPrompt:
    def test_prompt_shows_profile_name(self):
        pm = get_policy()
        pm.load_profile("advanced_materials_review", PROFILES_DIR)
        gate = BodyCitationIFGate()
        prompt = gate.confirmation_prompt()
        assert "advanced_materials_review" in prompt

    def test_prompt_shows_thresholds(self):
        pm = get_policy()
        pm.load_profile("advanced_materials_review", PROFILES_DIR)
        gate = BodyCitationIFGate()
        prompt = gate.confirmation_prompt()
        assert "IF > 6" in prompt
        assert "IF > 10" in prompt

    def test_prompt_shows_options(self):
        pm = get_policy()
        pm.load_profile("advanced_materials_review", PROFILES_DIR)
        gate = BodyCitationIFGate()
        prompt = gate.confirmation_prompt()
        assert "accept" in prompt
        assert "body=" in prompt
        assert "table=" in prompt
        assert "disable" in prompt


class TestAcceptDefaults:
    def test_accept_defaults_uses_profile_values(self):
        pm = get_policy()
        pm.load_profile("advanced_materials_review", PROFILES_DIR)
        gate = BodyCitationIFGate()
        gate.apply_runtime_policy()  # accept defaults

        c_high = make_candidate("High", "Nature")        # IF=50.5 >= 6
        c_low  = make_candidate("Low", "IEEE Sensors J.") # IF=4.5 < 6

        report = gate.validate_candidates([c_high, c_low])
        assert report.pass_count == 1
        passed = {d.citekey for d in report.passed}
        assert "High" in passed
        assert "Low" not in passed


class TestCustomizeBodyThreshold:
    def test_custom_body_threshold(self):
        pm = get_policy()
        pm.load_profile("advanced_materials_review", PROFILES_DIR)
        gate = BodyCitationIFGate()
        gate.apply_runtime_policy(body_threshold=15.0)

        # Nature IF=50.5 >= 15 → pass. ACS Sens IF=8.5 < 15 → blocked
        c1 = make_candidate("Nature", "Nature")
        c2 = make_candidate("Mid", "ACS Sens.")
        report = gate.validate_candidates([c1, c2])
        passed = {d.citekey for d in report.passed}
        assert "Nature" in passed
        assert "Mid" not in passed

    def test_custom_table_threshold(self):
        pm = get_policy()
        pm.load_profile("advanced_materials_review", PROFILES_DIR)
        gate = BodyCitationIFGate()
        gate.apply_runtime_policy(table_threshold=20.0)

        # Create table candidate
        c = CitationCandidate(
            paper=PaperIntel(citekey="NatMat", title="T", paper_type="research",
                           journal="ACS Nano", technical_keywords=["t"], semantic_anchors=["t"]),
            target_sentence="| Material | Ref |\n| PDMS | [1] |",
            section="3", similarity_score=0.5, reason="ok",
        )
        report = gate.validate_candidates([c])
        # ACS Nano IF=15.8 < 20 → BELOW_ELITE
        assert report.decisions[0].result == IFGateResult.BELOW_THRESHOLD


class TestDisableIF:
    def test_disable_if_filtering(self):
        pm = get_policy()
        pm.load_profile("advanced_materials_review", PROFILES_DIR)
        gate = BodyCitationIFGate()
        gate.apply_runtime_policy(disable_if=True)

        c = make_candidate("Low", "IEEE Sensors J.")  # IF=4.5 normally blocked
        report = gate.validate_candidates([c])
        assert report.pass_count == 1
        assert report.decisions[0].result == IFGateResult.GLOBAL_PASS

    def test_disable_passes_all(self):
        pm = get_policy()
        pm.load_profile("advanced_materials_review", PROFILES_DIR)
        gate = BodyCitationIFGate()
        gate.apply_runtime_policy(disable_if=True)

        candidates = [
            make_candidate("A", "Nature"),
            make_candidate("B", "IEEE Sensors J."),
            make_candidate("C", "Unknown J."),
        ]
        report = gate.validate_candidates(candidates)
        assert report.pass_count == 3
        assert report.block_count == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
